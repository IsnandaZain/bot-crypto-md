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
        if self.df.empty or len(self.df) < 5:
            return "NEUTRAL", 0, [f"{self.tf_name}: Not enough data"]

        row   = self.df.iloc[-1]     # forming candle (belum close)
        prev  = self.df.iloc[-2]     # closed candle (sudah close) ← SINYAL UTAMA
        prev2 = self.df.iloc[-3]     # previous closed candle untuk MACD/RSI change
        prev3 = self.df.iloc[-4]     # 3 candle lalu untuk konfirmasi trend bias
        reasons = []
        confluence_points = 0
        max_possible_points = 4.5 # 1(BB+SR) + 1(RSI) + 1(MACD) + 0.5(Volume)

        # ──────────────────────────────────────────────
        # 1. TREND BIAS (BB Mid) — Filter Utama
        # Minimal 2 dari 3 closed candle harus di sisi yang sama
        # ──────────────────────────────────────────────
        above_mid_count = sum([
            prev['close']  > prev['bb_mid'],
            prev2['close'] > prev2['bb_mid'],
            prev3['close'] > prev3['bb_mid'],
        ])
        trend_bullish = above_mid_count >= 2
        trend_bearish = not trend_bullish

        direction = 1 if trend_bullish else -1
        confirmed_count = above_mid_count if trend_bullish else (3 - above_mid_count)
        bias_text = "Above" if trend_bullish else "Below"
        reasons.append(f"{self.tf_name}: Price {bias_text} BB Mid ({confirmed_count}/3 candles)")

        # ──────────────────────────────────────────────
        # 1b. PRIOR MOMENTUM CONTEXT (Lookback 5 Candles)
        # Deteksi apakah sinyal saat ini genuine trend atau hanya pullback sesaat.
        # Kasus: harga baru saja rally kuat (5 candle lalu mayoritas bullish),
        # lalu turun ke bawah BB Mid → ini PULLBACK, bukan downtrend sejati.
        # VETO hanya aktif jika bias lemah (2/3) + ada counter-swing signifikan (>1.5%).
        # Jika bias kuat (3/3), hanya tambahkan catatan peringatan.
        # ──────────────────────────────────────────────
        if len(self.df) >= 10:
            prior = self.df.iloc[-9:-4]  # 5 candle sebelum window bias (prev4 s/d prev8)
            prior_above_count = int(sum(prior['close'] > prior['bb_mid']))
            prior_below_count = 5 - prior_above_count

            # Konflik: tren sekarang bearish tapi sebelumnya bullish, atau sebaliknya
            prior_conflict = (trend_bearish and prior_above_count >= 3) or \
                             (trend_bullish and prior_below_count >= 3)

            if prior_conflict:
                swing_high = prior['high'].max()
                swing_low  = prior['low'].min()
                price_swing = (swing_high - swing_low) / swing_low if swing_low > 0 else 0
                swing_dir   = "Bullish Rally" if trend_bearish else "Bearish Drop"
                prior_opp   = prior_above_count if trend_bearish else prior_below_count

                if confirmed_count == 2 and price_swing > 0.015:
                    # Bias lemah + ada counter-swing >1.5% → kemungkinan besar hanya pullback
                    reasons.append(
                        f"{self.tf_name}: ⚠️ PULLBACK VETO — Prior {swing_dir} {price_swing:.1%} "
                        f"({prior_opp}/5 candles sebelumnya berlawanan), bias terlalu lemah (2/3)"
                    )
                    return "NEUTRAL", 0, reasons
                else:
                    reasons.append(
                        f"{self.tf_name}: Prior {swing_dir} noted ({price_swing:.1%}), "
                        f"bias kuat (3/3) — lanjut analisis"
                    )

        # ──────────────────────────────────────────────
        # 2. BB TOUCH + S/R CONFIRMATION 
        # ──────────────────────────────────────────────
        long_bb = prev['low'] <= prev['bb_lower']    # Closed candle pernah sentuh bb_lower
        short_bb = prev['high'] >= prev['bb_upper']  # Closed candle pernah sentuh bb_upper
        nearest_sup = prev.get('nearest_support', float('nan'))
        nearest_res = prev.get('nearest_resistance', float('nan'))

        if not pd.isna(nearest_sup):
            long_sr = abs(prev['close'] - nearest_sup) / prev['close'] < self.tolerance
        else:
            long_sr = bool(prev.get('is_sup', 0)) or abs(prev['close'] - prev['low']) / prev['close'] < self.tolerance

        if not pd.isna(nearest_res):
            short_sr = abs(prev['close'] - nearest_res) / prev['close'] < self.tolerance
        else:
            short_sr = bool(prev.get('is_res', 0)) or abs(prev['close'] - prev['high']) / prev['close'] < self.tolerance

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
        rsi_val     = prev['rsi']
        rsi_rising  = prev['rsi'] > prev2['rsi']
        rsi_falling = prev['rsi'] < prev2['rsi']
        rsi_ok = (trend_bullish and 45 < rsi_val < 70 and rsi_rising) or \
                 (trend_bearish and 30 < rsi_val < 55 and rsi_falling)

        if rsi_ok:
            confluence_points += 1
            dir_txt = "rising" if trend_bullish else "falling"
            reasons.append(f"{self.tf_name}: RSI Agrees ({rsi_val:.0f}, {dir_txt})")
        elif rsi_val >= 70:
            reasons.append(f"{self.tf_name}: RSI Overbought ({rsi_val:.0f}) — Reversal Risk")
        elif rsi_val <= 30:
            reasons.append(f"{self.tf_name}: RSI Oversold ({rsi_val:.0f}) — Reversal Risk")
        elif not (rsi_rising if trend_bullish else rsi_falling):
            reasons.append(f"{self.tf_name}: RSI Wrong Direction ({rsi_val:.0f})")
        else:
            reasons.append(f"{self.tf_name}: RSI Neutral ({rsi_val:.0f})")

        # ──────────────────────────────────────────────
        # 4. MACD HISTOGRAM — Momentum Confirmation
        # ──────────────────────────────────────────────
        macd_positive = prev['macd_hist'] > 0
        macd_inc      = prev['macd_hist'] > prev2['macd_hist']
        macd_ok = (trend_bullish and macd_positive and macd_inc) or \
                  (trend_bearish and not macd_positive and not macd_inc)

        if macd_ok:
            confluence_points += 1
            reasons.append(f"{self.tf_name}: MACD Momentum Agrees ({prev['macd_hist']:.4f})")
        elif (trend_bullish and macd_inc) or (trend_bearish and not macd_inc):
            reasons.append(f"{self.tf_name}: MACD Direction OK but Wrong Side of Zero ({prev['macd_hist']:.4f})")
        else:
            reasons.append(f"{self.tf_name}: MACD Diverges ({prev['macd_hist']:.4f})")

        # ──────────────────────────────────────────────
        # 5. VOLUME — Confirmation
        # ──────────────────────────────────────────────
        vol_ratio = prev['volume'] / prev['vol_ma']
        if vol_ratio >= 1.5:
            confluence_points += 0.5
            reasons.append(f"{self.tf_name}: Volume Strong ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.0:
            confluence_points += 0.25
            reasons.append(f"{self.tf_name}: Volume Moderate ({vol_ratio:.1f}x)")
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
        if self.df.empty or len(self.df) < 5:
            return "NEUTRAL", 0, [f"{self.tf_name}: Not enough data"]

        row   = self.df.iloc[-1]     # forming candle
        prev  = self.df.iloc[-2]     # closed candle ← SINYAL UTAMA
        prev2 = self.df.iloc[-3]     # previous closed candle
        prev3 = self.df.iloc[-4]     # untuk 2-candle RSI confirmation
        reasons = []
        confluence_points = 0
        max_possible_points = 4.5    # 1(BB+SR) + 1(RSI) + 1(MACD) + 0.5(Volume) + 0.25(Wick)

        # ──────────────────────────────────────────────
        # 🛡️ ADX FILTER (Opsional tapi Direkomendasikan)
        # ──────────────────────────────────────────────
        adx_val = prev['adx']
        
        if adx_val > 28:
            return "NEUTRAL", 0, [
                f"{self.tf_name}: VETO — ADX {adx_val:.0f} > 28, trend too strong for reversal"
            ]

        if adx_val < 15:
            reasons.append(f"{self.tf_name}: ADX low ({adx_val:.0f}), ranging market ✅")
        elif adx_val < 20:
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
        # 1b. PRIOR MOMENTUM CONTEXT (Lookback 5 Candles)
        # Reversal valid hanya jika harga SUDAH trending ke arah ekstrem sebelumnya.
        # Jika BB Upper/Lower disentuh tiba-tiba tanpa prior trend = SPIKE, bukan EXHAUSTION.
        # Contoh: harga naik mendadak ke BB Upper padahal 5 candle sebelumnya bearish
        #         → bukan uptrend yang exhausted, melainkan news spike → reversal berisiko tinggi.
        # Kebalikan dari analyze(): di sini conflict = prior berlawanan dengan ARAH MENUJU ekstrem.
        # ──────────────────────────────────────────────
        if len(self.df) >= 10:
            prior = self.df.iloc[-9:-4]  # 5 candle sebelum window trigger (prev4 s/d prev8)
            prior_above_count = int(sum(prior['close'] > prior['bb_mid']))
            prior_below_count = 5 - prior_above_count

            swing_high  = prior['high'].max()
            swing_low   = prior['low'].min()
            price_swing = (swing_high - swing_low) / swing_low if swing_low > 0 else 0

            # at_upper: seharusnya prior bullish (uptrend → exhaustion di atas)
            # → conflict jika prior justru bearish (>= 3 candle di bawah BB Mid)
            # at_lower: seharusnya prior bearish (downtrend → exhaustion di bawah)
            # → conflict jika prior justru bullish (>= 3 candle di atas BB Mid)
            prior_conflict = (at_upper and prior_below_count >= 3) or \
                             (at_lower and prior_above_count >= 3)

            if prior_conflict and price_swing > 0.015:
                spike_dir = "Upward Spike" if at_upper else "Downward Spike"
                prior_opp = prior_below_count if at_upper else prior_above_count
                reasons.append(
                    f"{self.tf_name}: ⚠️ SPIKE VETO — {spike_dir} tanpa prior trend "
                    f"({prior_opp}/5 candle sebelumnya berlawanan, swing {price_swing:.1%}) "
                    f"— bukan exhaustion sejati"
                )
                return "NEUTRAL", 0, reasons
            elif prior_conflict:
                spike_dir = "Upward" if at_upper else "Downward"
                reasons.append(
                    f"{self.tf_name}: ⚠️ Prior context lemah untuk reversal "
                    f"({spike_dir} tanpa strong prior trend, swing {price_swing:.1%}) — proceed cautiously"
                )

        # ──────────────────────────────────────────────
        # 2. LOCATION: S/R ALIGNMENT
        # ──────────────────────────────────────────────
        nearest_sup = prev.get('nearest_support', float('nan'))
        nearest_res = prev.get('nearest_resistance', float('nan'))

        sr_hit = False
        if at_upper:
            if not pd.isna(nearest_res):
                sr_hit = abs(prev['close'] - nearest_res) / prev['close'] < self.tolerance
            if not sr_hit:
                sr_hit = bool(prev.get('is_res', 0)) or abs(prev['close'] - prev['high']) / prev['close'] < self.tolerance
        else:
            if not pd.isna(nearest_sup):
                sr_hit = abs(prev['close'] - nearest_sup) / prev['close'] < self.tolerance
            if not sr_hit:
                sr_hit = bool(prev.get('is_sup', 0)) or abs(prev['close'] - prev['low']) / prev['close'] < self.tolerance

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
        # Perlu 2 candle konfirmasi arah balik (bukan hanya 1 candle dip)
        rsi_rolling = (at_upper and prev['rsi'] < prev2['rsi'] and prev2['rsi'] < prev3['rsi']) or \
                      (at_lower and prev['rsi'] > prev2['rsi'] and prev2['rsi'] > prev3['rsi'])

        if rsi_extreme and rsi_rolling:
            confluence_points += 1.0
            reasons.append(f"{self.tf_name}: RSI Exhausted & Rolling Back 2 candles ({rsi_val:.0f})")
        elif rsi_extreme and ((at_upper and prev['rsi'] < prev2['rsi']) or (at_lower and prev['rsi'] > prev2['rsi'])):
            reasons.append(f"{self.tf_name}: RSI Extreme, 1-candle turn only — wait confirm ({rsi_val:.0f})")
        elif rsi_extreme:
            reasons.append(f"{self.tf_name}: RSI Extreme but Still Pushing (Risk) ({rsi_val:.0f})")
        else:
            reasons.append(f"{self.tf_name}: RSI Not Extreme ({rsi_val:.0f})")

        # ──────────────────────────────────────────────
        # 4. MOMENTUM FADE: MACD HISTOGRAM
        # ──────────────────────────────────────────────
        # Reversal membutuhkan pelemahan momentum — arah DAN nilai absolut mengecil
        hist_weakening = abs(prev['macd_hist']) < abs(prev2['macd_hist'])
        macd_fading = ((at_upper and prev['macd_hist'] < prev2['macd_hist'] and hist_weakening) or
                       (at_lower and prev['macd_hist'] > prev2['macd_hist'] and hist_weakening))

        if macd_fading:
            confluence_points += 1.0
            reasons.append(f"{self.tf_name}: MACD Momentum Fading (weakening)")
        elif (at_upper and prev['macd_hist'] < prev2['macd_hist']) or \
             (at_lower and prev['macd_hist'] > prev2['macd_hist']):
            reasons.append(f"{self.tf_name}: MACD Direction Fading but Magnitude Growing")
        else:
            reasons.append(f"{self.tf_name}: MACD Still Expanding (Trend May Continue)")

        # ──────────────────────────────────────────────
        # 5. PARTICIPATION: VOLUME CLIMAX
        # ──────────────────────────────────────────────
        vol_ratio = prev['volume'] / prev['vol_ma']
        # Volume climax di ekstrem — semakin tinggi, semakin kuat sinyal exhaustion
        if vol_ratio >= 2.0:
            confluence_points += 0.5
            reasons.append(f"{self.tf_name}: Volume Climax ({vol_ratio:.1f}x) ✅")
        elif vol_ratio >= 1.5:
            confluence_points += 0.25
            reasons.append(f"{self.tf_name}: Volume Elevated ({vol_ratio:.1f}x) ⚠️")
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
                confluence_points += 0.25
                reasons.append(f"{self.tf_name}: Forming candle shows strong rejection wick ✅")

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
