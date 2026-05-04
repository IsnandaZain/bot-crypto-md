# strategy/signal_engine_bb.py
# Hanya tambahkan parameter tf_name untuk identifikasi

import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt

from datetime import datetime
import os

class SignalEngineBB:
    def __init__(self, df, tf_name='base'):
        self.df = df
        self.tf_name = tf_name  # NEW: 'higher', 'base', atau 'lower'
        self.last = df.iloc[-1]
        self.prev = df.iloc[-2]

        self.tolerance = 0.005 # 0.5% untuk deteksi S/R proximity
    
    def analyze(self):
        """Analisis teknikal BB untuk satu timeframe — Confluence-based, bukan scoring arbitrer"""
        if self.df.empty:
            return "NEUTRAL", 0, []

        row = self.df.iloc[-1]       # forming candle (belum close)
        prev = self.df.iloc[-2]      # closed candle (sudah close) ← SINYAL UTAMA
        prev2 = self.df.iloc[-3]     # previous closed candle untuk MACD change
        reasons = []
        confluence_points = 0
        max_possible_points = 4.5 # 1(BB+SR) + 1(RSI) + 1(MACD) + 0.5(Volume)

        # ──────────────────────────────────────────────
        # 1. TREND BIAS (BB Mid) — Filter Utama
        # ──────────────────────────────────────────────
        trend_bullish = prev['close'] > prev['bb_mid']
        trend_bearish = prev['close'] < prev['bb_mid']

        if not trend_bullish and not trend_bearish:
            return "NEUTRAL", 0, [f"{self.tf_name}: VETO — Price at BB Mid, unclear bias"]
        
        direction = 1 if trend_bullish else -1
        bias_text = "Above" if trend_bullish else "Below"
        reasons.append(f"{self.tf_name}: Price {bias_text} BB Mid (closed)")

        # ──────────────────────────────────────────────
        # 2. BB TOUCH + S/R CONFIRMATION 
        # ──────────────────────────────────────────────
        long_bb = prev['low'] <= prev['bb_lower']    # Closed candle pernah sentuh bb_lower
        short_bb = prev['high'] >= prev['bb_upper']  # Closed candle pernah sentuh bb_upper
        long_sr = prev.get('is_sup', 0) or abs(prev['close'] - prev['low'])/prev['close'] < self.tolerance
        short_sr = prev.get('is_res', 0) or abs(prev['close'] - prev['high'])/prev['close'] < self.tolerance

        if (trend_bullish and long_bb and long_sr) or (trend_bearish and short_bb and short_sr):
            confluence_points += 1
            reasons.append(f"{self.tf_name}: BB Extreme + S/R Confirmed")
        elif long_bb or short_bb:
            reasons.append(f"{self.tf_name}: BB Touched (No S/R Confirm)")
        else:
            reasons.append(f"{self.tf_name}: No BB Extreme Touch")

        # ──────────────────────────────────────────────
        # 3. RSI MOMENTUM — Harus SEARAH dengan bias
        # ──────────────────────────────────────────────
        rsi_val = prev['rsi']
        rsi_ok = (trend_bullish and 45 < rsi_val < 70) or (trend_bearish and 30 < rsi_val < 55)
        
        if rsi_ok:
            confluence_points += 1
            reasons.append(f"{self.tf_name}: RSI Agrees ({rsi_val:.0f})")
        elif rsi_val >= 70:
            reasons.append(f"{self.tf_name}: RSI Overbought ({rsi_val:.0f}) — Reversal Risk")
        elif rsi_val <= 30:
            reasons.append(f"{self.tf_name}: RSI Oversold ({rsi_val:.0f}) — Reversal Risk")
        else:
            reasons.append(f"{self.tf_name}: RSI Neutral ({rsi_val:.0f})")

        # ──────────────────────────────────────────────
        # 4. MACD HISTOGRAM — Momentum Confirmation
        # ──────────────────────────────────────────────
        macd_inc = prev['macd_hist'] > prev2['macd_hist']
        macd_ok = (trend_bullish and macd_inc) or (trend_bearish and not macd_inc)
        
        if macd_ok:
            confluence_points += 1
            reasons.append(f"{self.tf_name}: MACD Momentum Agrees")
        else:
            reasons.append(f"{self.tf_name}: MACD Diverges")

        # ──────────────────────────────────────────────
        # 5. VOLUME — Confirmation
        # ──────────────────────────────────────────────
        vol_ratio = prev['volume'] / prev['vol_ma']
        if vol_ratio > 1.2:
            confluence_points += 0.5
            reasons.append(f"{self.tf_name}: Volume Strong ({vol_ratio:.1f}x)")
        else:
            reasons.append(f"{self.tf_name}: Volume Weak ({vol_ratio:.1f}x)")

        # ──────────────────────────────────────────────
        # 5b. FORMING CANDLE CONFIRMATION (Real-time)
        # ──────────────────────────────────────────────
        if confluence_points > 0:
            forming_long = row['low'] <= row['bb_lower']
            forming_short = row['high'] >= row['bb_upper']
            if (trend_bullish and forming_long) or (trend_bearish and forming_short):
                reasons.append(f"{self.tf_name}: Forming candle confirms continuation")

        # ──────────────────────────────────────────────
        # KEPUTUSAN: Confluence Rate
        # ──────────────────────────────────────────────
        if rsi_val > 75 or rsi_val < 25:
            return "NEUTRAL", 0, reasons + [f"{self.tf_name}: VETO — RSI Extreme ({rsi_val:.0f})"]

        confluence_rate = confluence_points / max_possible_points  # 0.0 s/d 1.0
        score = confluence_rate * 3 * direction  # Normalized to -3.0 s/d +3.0

        # Threshold: rate >= 0.4 → score >= 1.2 (compatible dengan parent function)
        if confluence_rate >= 0.4:
            signal = "BULLISH" if trend_bullish else "BEARISH"
            reasons.append(f"{self.tf_name}: Confluence OK ({confluence_rate:.0%})")
        else:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: Confluence rendah ({confluence_rate:.0%}, butuh ≥40%)")

        return signal, round(score, 2), reasons

    
    def analyze_reversal(self):
        """Analisis teknikal BB untuk sinyal REVERSAL — Mean Reversion & Exhaustion"""
        if self.df.empty:
            return "NEUTRAL", 0, []

        row = self.df.iloc[-1]       # forming candle
        prev = self.df.iloc[-2]      # closed candle ← SINYAL UTAMA
        prev2 = self.df.iloc[-3]     # previous closed candle
        reasons = []
        confluence_points = 0
        max_possible_points = 4.5    # 1(BB+SR) + 1(RSI) + 1(MACD) + 0.5(Volume)

        # ──────────────────────────────────────────────
        # 🛡️ ADX FILTER (Opsional tapi Direkomendasikan)
        # ──────────────────────────────────────────────
        adx_val = prev['adx']
        
        if adx_val > 35:
            return "NEUTRAL", 0, [
                f"{self.tf_name}: VETO — ADX {adx_val:.0f} > {35}, strong trend"
            ]
        
        if adx_val < 15:
            reasons.append(f"{self.tf_name}: ADX low ({adx_val:.0f}), ranging market ✅")
        elif adx_val < 25:
            reasons.append(f"{self.tf_name}: ADX moderate ({adx_val:.0f}), cautious ✅")
        else:
            reasons.append(f"{self.tf_name}: ADX elevated ({adx_val:.0f}), higher risk ⚠️")

        # ──────────────────────────────────────────────
        # 1. TRIGGER: BB EXTREME TOUCH
        # ──────────────────────────────────────────────
        at_upper = prev['high'] >= prev['bb_upper']
        at_lower = prev['low'] <= prev['bb_lower']

        if not (at_upper or at_lower):
            return "NEUTRAL", 0, [f"{self.tf_name}: VETO — Price inside BB, no reversal trigger"]

        direction = -1 if at_upper else 1
        bias_text = "Upper Band (Short Bias)" if at_upper else "Lower Band (Long Bias)"
        reasons.append(f"{self.tf_name}: Price at {bias_text}")

        # ──────────────────────────────────────────────
        # 2. LOCATION: S/R ALIGNMENT
        # ──────────────────────────────────────────────
        sr_hit = False
        if at_upper:
            sr_hit = prev.get('is_res', 0) or abs(prev['close'] - prev['high'])/prev['close'] < self.tolerance
        else:
            sr_hit = prev.get('is_sup', 0) or abs(prev['close'] - prev['low'])/prev['close'] < self.tolerance

        if sr_hit:
            confluence_points += 1.0
            reasons.append(f"{self.tf_name}: S/R Confirmed at Extreme")
        else:
            reasons.append(f"{self.tf_name}: No S/R Alignment (Lower Probability)")

        # ──────────────────────────────────────────────
        # 3. MOMENTUM EXHAUSTION: RSI TURNING
        # ──────────────────────────────────────────────
        rsi_val = prev['rsi']
        rsi_extreme = (at_upper and rsi_val > 70) or (at_lower and rsi_val < 30)
        # RSI harus sudah mulai berbalik (rolling back), bukan masih mendorong ekstrem
        rsi_rolling = (at_upper and rsi_val < prev2['rsi']) or (at_lower and rsi_val > prev2['rsi'])

        if rsi_extreme and rsi_rolling:
            confluence_points += 1.0
            reasons.append(f"{self.tf_name}: RSI Exhausted & Rolling Back ({rsi_val:.0f})")
        elif rsi_extreme:
            reasons.append(f"{self.tf_name}: RSI Extreme but Still Pushing (Risk)")
        else:
            reasons.append(f"{self.tf_name}: RSI Not Extreme ({rsi_val:.0f})")

        # ──────────────────────────────────────────────
        # 4. MOMENTUM FADE: MACD HISTOGRAM
        # ──────────────────────────────────────────────
        # Reversal membutuhkan pelemahan momentum searah ekstrem
        macd_fading = (at_upper and prev['macd_hist'] < prev2['macd_hist']) or \
                      (at_lower and prev['macd_hist'] > prev2['macd_hist'])

        if macd_fading:
            confluence_points += 1.0
            reasons.append(f"{self.tf_name}: MACD Momentum Fading")
        else:
            reasons.append(f"{self.tf_name}: MACD Still Expanding (Trend May Continue)")

        # ──────────────────────────────────────────────
        # 5. PARTICIPATION: VOLUME CLIMAX
        # ──────────────────────────────────────────────
        vol_ratio = prev['volume'] / prev['vol_ma']
        # Volume tinggi di ekstrem sering menandakan climax/exhaustion, bukan kelanjutan
        if vol_ratio > 1.3:
            confluence_points += 0.5
            reasons.append(f"{self.tf_name}: Volume Climax ({vol_ratio:.1f}x)")
        else:
            reasons.append(f"{self.tf_name}: Volume Normal ({vol_ratio:.1f}x)")

        # ──────────────────────────────────────────────
        # 5b. PRICE ACTION: FORMING CANDLE REJECTION
        # ──────────────────────────────────────────────
        if confluence_points > 0:
            body = abs(row['close'] - row['open'])
            rng = row['high'] - row['low']
            if rng > 0:
                upper_wick_pct = (row['high'] - max(row['open'], row['close'])) / rng
                lower_wick_pct = (min(row['open'], row['close']) - row['low']) / rng
            else:
                upper_wick_pct = lower_wick_pct = 0

            rejection = (at_upper and upper_wick_pct > 0.4) or (at_lower and lower_wick_pct > 0.4)
            if rejection:
                reasons.append(f"{self.tf_name}: Forming candle shows strong rejection wick")

        # ──────────────────────────────────────────────
        # VETO & DECISION
        # ──────────────────────────────────────────────
        # Hindari setup parabolic/news spike yang bisa menghancurkan reversal
        if rsi_val > 85 or rsi_val < 15:
            return "NEUTRAL", 0, reasons + [f"{self.tf_name}: VETO — RSI Parabolic ({rsi_val:.0f})"]

        confluence_rate = confluence_points / max_possible_points
        score = confluence_rate * 3 * direction  # +3 untuk LONG, -3 untuk SHORT

        if confluence_rate >= 0.4:
            signal = "SHORT" if direction == -1 else "LONG"
            reasons.append(f"{self.tf_name}: Reversal Confluence OK ({confluence_rate:.0%})")
        else:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: Confluence rendah ({confluence_rate:.0%})")

        return signal, round(score, 2), reasons
    

    def resolve_signals(self):
        """Menggabungkan output trend-following & reversal menjadi 1 keputusan final"""
        trend_signal, trend_score, trend_reasons = self.analyze()
        rev_signal, rev_score, rev_reasons = self.analyze_reversal()

        print(f"📄 Result Trend Signal : {trend_signal}")
        print(f"📄 Result Reversal Signal : {rev_signal}")
        
        # 1. Jika keduanya NEUTRAL → Langsung keluar
        if trend_signal == "NEUTRAL" and rev_signal == "NEUTRAL":
            return "NEUTRAL", 0, trend_reasons + rev_reasons + ["Market: Waiting for trigger"]
        
        # 2. Jika SEARAH (Confluence) → Upgrade signal
        if trend_signal != "NEUTRAL" and rev_signal != "NEUTRAL" and trend_signal == rev_signal:
            final_score = round((abs(trend_score) + abs(rev_score)) / 2, 2)
            direction = 1 if "LONG" in trend_signal else -1
            final_score *= direction
            reasons = trend_reasons + rev_reasons + ["🔥 CONFLUENCE: Trend + Reversal aligned"]
            return trend_signal, final_score, reasons
        
        # 3. Jika hanya TREND-FOLLOWING aktif → Prioritas utama (win rate lebih stabil)
        if trend_signal != "NEUTRAL":
            return trend_signal, trend_score, trend_reasons + ["📈 Mode: Trend-Following"]
        
        # 4. Jika hanya REVERSAL aktif → Perlu filter tambahan (ADX / Higher TF)
        if rev_signal != "NEUTRAL":
            # Optional: Cek ADX sebelum mengizinkan counter-trend
            adx = self.df.iloc[-2].get('adx', 0)
            if adx > 30:
                return "NEUTRAL", 0, rev_reasons + [f"⛔ VETO: ADX {adx:.0f} too strong for reversal"]
            return rev_signal, rev_score, rev_reasons + ["🔄 Mode: Counter-Trend (High RR)"]
        
        return "NEUTRAL", 0, ["Unexpected state"]

    def get_data(self):
        """Ambil data penting dari timeframe ini"""
        return {
            'tf': self.tf_name,
            'price': self.last['close'],
            'atr': self.last['atr'],
            'rsi': self.last['rsi'],
            'adx': self.last['adx'],
        }
    
    def plot_and_save_last_n(self, n_candles: int = 30, save_dir: str = "./data", symbol: str = "Unknown"):
        """Analisis visual & simpan chart terakhir sebagai gambar dengan nama unik"""
        if self.df.empty:
            print("DataFrame kosong.")
            return None

        # Buat folder jika belum ada
        os.makedirs(save_dir, exist_ok=True)

        df = self.df.copy().tail(n_candles)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Validasi kolom (sama seperti sebelumnya)
        required = ['open', 'high', 'low', 'close', 'volume',
                    'bb_upper', 'bb_mid', 'bb_lower', 'rsi', 'macd_hist', 'vol_ma']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Kolom wajib belum ada: {missing}")

        # Setup overlay plot
        tf_name = getattr(self, "tf_name", "Chart")
        apds = [
            mpf.make_addplot(df['bb_upper'], color='blue', width=0.8),
            mpf.make_addplot(df['bb_mid'],  color='gray', width=0.8, linestyle='--'),
            mpf.make_addplot(df['bb_lower'], color='blue', width=0.8),
            mpf.make_addplot(df['rsi'], panel=1, color='purple', ylabel='RSI'),
            mpf.make_addplot(pd.DataFrame({'30': [30]*len(df), '70': [70]*len(df)}, index=df.index),
                             panel=1, color='black', linestyle=':', width=0.8),
            mpf.make_addplot(df['macd_hist'], type='bar', panel=2,
                             color=['green' if v >= 0 else 'red' for v in df['macd_hist']],
                             ylabel='MACD Hist'),
            mpf.make_addplot(df['volume'], panel=3, color='orange', width=1.5, ylabel='Volume')
        ]

        # 🔹 Generate filename unik dengan Symbol + Timeframe + Timestamp
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = os.path.join(save_dir, f"{safe_symbol}_bb_{tf_name}.png")

        # 🔹 Plot & Simpan langsung
        mpf.plot(
            df,
            type='candle',
            style='charles',
            title=f'\n{symbol} ({tf_name}) - Last {n_candles} Candles',
            ylabel='Price',
            volume=True,
            addplot=apds,
            figratio=(16, 9),
            figscale=1.1,
            tight_layout=True,
            savefig=filename  # <-- Kunci penggantian show() ke save
        )

        # 🔹 Bersihkan memori (penting jika dijalankan dalam loop/batch)
        plt.close('all')
        print(f"✅ Chart berhasil disimpan: {filename}")
        return filename

    def plot_and_save_to_signal_folder(self, signal_folder: str, n_candles: int = 30, symbol: str = "Unknown"):
        """
        Plot dan simpan chart ke dalam folder sinyal yang sudah ditentukan.
        
        Args:
            signal_folder: Path ke folder sinyal (contoh: signals/2026-04-28/SOLUSDT_LONG_150823)
            n_candles: Jumlah candle yang ditampilkan
            symbol: Nama pair/symbol
        
        Returns:
            Path ke file chart yang disimpan
        """
        if self.df.empty:
            print("DataFrame kosong.")
            return None

        # Buat folder sinyal jika belum ada
        os.makedirs(signal_folder, exist_ok=True)

        df = self.df.copy().tail(n_candles)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Validasi kolom
        required = ['open', 'high', 'low', 'close', 'volume',
                    'bb_upper', 'bb_mid', 'bb_lower', 'rsi', 'macd_hist', 'vol_ma']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Kolom wajib belum ada: {missing}")

        # Setup overlay plot
        tf_name = getattr(self, "tf_name", "Chart")
        apds = [
            mpf.make_addplot(df['bb_upper'], color='blue', width=0.8),
            mpf.make_addplot(df['bb_mid'],  color='gray', width=0.8, linestyle='--'),
            mpf.make_addplot(df['bb_lower'], color='blue', width=0.8),
            mpf.make_addplot(df['rsi'], panel=1, color='purple', ylabel='RSI'),
            mpf.make_addplot(pd.DataFrame({'30': [30]*len(df), '70': [70]*len(df)}, index=df.index),
                             panel=1, color='black', linestyle=':', width=0.8),
            mpf.make_addplot(df['macd_hist'], type='bar', panel=2,
                             color=['green' if v >= 0 else 'red' for v in df['macd_hist']],
                             ylabel='MACD Hist'),
            mpf.make_addplot(df['volume'], panel=3, color='orange', width=1.5, ylabel='Volume')
        ]

        # 🔹 Generate filename: chart.png (simple, konsisten)
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        filename = os.path.join(signal_folder, f"{safe_symbol}_bb_{tf_name}_chart.png")

        # 🔹 Plot & Simpan langsung
        mpf.plot(
            df,
            type='candle',
            style='charles',
            title=f'\n{symbol} ({tf_name}) - Last {n_candles} Candles',
            ylabel='Price',
            volume=True,
            addplot=apds,
            figratio=(16, 9),
            figscale=1.1,
            tight_layout=True,
            savefig=filename
        )

        # 🔹 Bersihkan memori
        plt.close('all')
        print(f"✅ Chart sinyal disimpan: {filename}")
        return filename
