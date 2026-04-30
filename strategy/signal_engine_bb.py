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
        confluence_count = 0
        total_checks = 0

        # ──────────────────────────────────────────────
        # 1. TREND BIAS (BB Mid) — Filter Utama
        # ──────────────────────────────────────────────
        total_checks += 1
        trend_bullish = prev['close'] > prev['bb_mid']
        trend_bearish = prev['close'] < prev['bb_mid']

        if trend_bullish:
            reasons.append(f"{self.tf_name}: Price Above BB Mid (closed)")
        elif trend_bearish:
            reasons.append(f"{self.tf_name}: Price Below BB Mid (closed)")

        # ──────────────────────────────────────────────
        # 2. BB TOUCH + S/R CONFIRMATION — Reversal Signal
        #    Closed candle only, low/high untuk deteksi wick
        # ──────────────────────────────────────────────
        total_checks += 1
        bb_sr_confirms = False

        long_bb = prev['low'] <= prev['bb_lower']    # Closed candle pernah sentuh bb_lower
        short_bb = prev['high'] >= prev['bb_upper']  # Closed candle pernah sentuh bb_upper
        long_sr = prev.get('is_sup', 0) or abs(prev['close'] - prev['low'])/prev['close'] < self.tolerance
        short_sr = prev.get('is_res', 0) or abs(prev['close'] - prev['high'])/prev['close'] < self.tolerance

        if long_bb and long_sr:
            bb_sr_confirms = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: BB Lower + S/R Support (closed)")
        elif short_bb and short_sr:
            bb_sr_confirms = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: BB Upper + S/R Resistance (closed)")
        elif long_bb:
            reasons.append(f"{self.tf_name}: BB Lower Touched (no S/R confirm)")
        elif short_bb:
            reasons.append(f"{self.tf_name}: BB Upper Touched (no S/R confirm)")
        else:
            reasons.append(f"{self.tf_name}: No BB Extreme Touch")

        # ──────────────────────────────────────────────
        # 3. RSI MOMENTUM — Harus SEARAH dengan bias
        # ──────────────────────────────────────────────
        total_checks += 1
        rsi_agrees = False

        if trend_bullish and prev['rsi'] > 45 and prev['rsi'] < 70:
            rsi_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: RSI Bullish ({prev['rsi']:.0f})")
        elif trend_bearish and prev['rsi'] < 55 and prev['rsi'] > 30:
            rsi_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: RSI Bearish ({prev['rsi']:.0f})")
        elif prev['rsi'] > 70:
            reasons.append(f"{self.tf_name}: RSI Overbought ({prev['rsi']:.0f}) — Reversal Risk")
        elif prev['rsi'] < 30:
            reasons.append(f"{self.tf_name}: RSI Oversold ({prev['rsi']:.0f}) — Reversal Risk")
        else:
            reasons.append(f"{self.tf_name}: RSI Neutral ({prev['rsi']:.0f})")

        # ──────────────────────────────────────────────
        # 4. MACD HISTOGRAM — Momentum Confirmation
        # ──────────────────────────────────────────────
        total_checks += 1
        macd_agrees = False

        macd_increasing = prev['macd_hist'] > prev2['macd_hist']
        if trend_bullish and macd_increasing:
            macd_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: MACD Increasing (bullish)")
        elif trend_bearish and not macd_increasing:
            macd_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: MACD Decreasing (bearish)")
        else:
            reasons.append(f"{self.tf_name}: MACD Diverges")

        # ──────────────────────────────────────────────
        # 5. VOLUME — Confirmation
        # ──────────────────────────────────────────────
        total_checks += 1
        volume_strong = False
        if prev['volume'] > prev['vol_ma'] * 1.2:
            volume_strong = True
            confluence_count += 0.5  # Volume penguat, bukan penentu arah
            reasons.append(f"{self.tf_name}: Volume Strong ({prev['volume']/prev['vol_ma']:.1f}x avg)")
        else:
            reasons.append(f"{self.tf_name}: Volume Weak ({prev['volume']/prev['vol_ma']:.1f}x avg)")

        # ──────────────────────────────────────────────
        # 5b. FORMING CANDLE CONFIRMATION (Real-time)
        # ──────────────────────────────────────────────
        forming_confirms = False
        if confluence_count > 0:  # Hanya jika sudah ada konfirmasi dari closed candle
            forming_long = row['low'] <= row['bb_lower']
            forming_short = row['high'] >= row['bb_upper']
            if (long_bb and forming_long) or (short_bb and forming_short):
                forming_confirms = True
                reasons.append(f"{self.tf_name}: Forming candle confirms BB touch")

        # ──────────────────────────────────────────────
        # KEPUTUSAN: Confluence Rate
        # ──────────────────────────────────────────────
        confluence_rate = confluence_count / total_checks

        # VETO conditions
        if prev['rsi'] > 75 or prev['rsi'] < 25:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: VETO — RSI Extreme ({prev['rsi']:.0f})")
        elif not trend_bullish and not trend_bearish:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: VETO — Price at BB Mid, unclear bias")
        elif confluence_rate >= 0.6:
            signal = "BULLISH" if trend_bullish else "BEARISH"
        else:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: Confluence rendah ({confluence_rate:.0%})")

        # Normalize score ke -3 s/d +3
        score = (confluence_rate - 0.5) * 6
        score = max(-3, min(3, score))

        return signal, score, reasons

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
