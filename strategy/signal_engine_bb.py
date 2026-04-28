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
        """Analisis teknikal BB untuk satu timeframe tertentu (mirip SignalEngine.analyze)"""
        if self.df.empty:
            return "NEUTRAL", 0, []
        
        row = self.df.iloc[-1]
        prev = self.df.iloc[-2]
        score = 0
        reasons = []

        adx = row['adx']

        # 1. Bollinger Bands & Trend Bias
        if row['close'] > row['bb_mid']:
            score += 1
            reasons.append(f"{self.tf_name}: Price Above BB Mid")
        else:
            score -= 1
            reasons.append(f"{self.tf_name}: Price Below BB Mid")

        # 2. Reversal / Bounce Signals (BB Extremes + S/R)
        long_bb = row['close'] <= row['bb_lower']
        short_bb = row['close'] >= row['bb_upper']
        long_sr = row.get('is_sup', 0) or abs(row['close'] - row['low'])/row['close'] < self.tolerance
        short_sr = row.get('is_res', 0) or abs(row['close'] - row['high'])/row['close'] < self.tolerance

        if long_bb:
            score += 1
            reasons.append(f"{self.tf_name}: BB Lower Touched")
            if long_sr:
                score += 1  # Total +2 jika konfluensi
                reasons.append(f"{self.tf_name}: + S/R Support Confirmed")
        elif short_bb:
            score -= 1
            reasons.append(f"{self.tf_name}: BB Upper Touched")
            if short_sr:
                score -= 1  # Total -2 jika konfluensi
                reasons.append(f"{self.tf_name}: + S/R Resistance Confirmed")

        # 3. RSI Momentum
        if row['rsi'] < 35:
            score += 1
            reasons.append(f"{self.tf_name}: RSI Oversold")
        elif row['rsi'] > 65:
            score -= 1
            reasons.append(f"{self.tf_name}: RSI Overbought")

        # 4. MACD Histogram Change
        if row['macd_hist'] > prev['macd_hist']:
            score += 0.5
        else:
            score -= 0.5

        # 5. Volume Confirmation
        if row['volume'] > row['vol_ma'] * 1.2:
            score += 0.5 if score > 0 else -0.5
            reasons.append(f"{self.tf_name}: High Volume")

        # Tentukan status TF
        if score >= 2: signal = "BULLISH"
        elif score <= -2: signal = "BEARISH"
        else: signal = "NEUTRAL"

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
