# strategy/signal_engine.py
# Hanya tambahkan parameter tf_name untuk identifikasi
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt

from datetime import datetime
import os

class SignalEngine:
    def __init__(self, df, tf_name='base'):
        self.df = df
        self.tf_name = tf_name  # NEW: 'higher', 'base', atau 'lower'
        self.last = df.iloc[-1]
        self.prev = df.iloc[-2]
    
    def analyze(self):
        """Analisis sinyal untuk 1 timeframe tertentu"""
        signal = "NEUTRAL"  # Ubah dari NO TRADE agar tidak konflik dengan MTF
        score = 0
        reasons = []
        
        # Extract values
        ema_short = self.last['EMA_SHORT']
        ema_long = self.last['EMA_LONG']
        close = self.last['close']
        rsi = self.last['RSI']
        macd_hist = self.last['MACDh_12_26_9']
        adx = self.last['ADX']
        volume = self.last['volume']
        vol_avg = self.last['VOL_SMA']
        
        # Trend Check
        if ema_short > ema_long:
            score += 1
            reasons.append(f"{self.tf_name}: Bullish Trend")
        elif ema_short < ema_long:
            score -= 1
            reasons.append(f"{self.tf_name}: Bearish Trend")
        
        # Momentum Check
        if macd_hist > 0:
            score += 0.5
            reasons.append(f"{self.tf_name}: MACD Positive")
        else:
            score -= 0.5
        
        # RSI Check
        if 40 < rsi < 60:
            score += 0.5
            reasons.append(f"{self.tf_name}: RSI Neutral (Good for Entry)")
        elif rsi > 70:
            score -= 1
            reasons.append(f"{self.tf_name}: RSI Overbought")
        elif rsi < 30:
            score += 1
            reasons.append(f"{self.tf_name}: RSI Oversold")
        
        # Volume Check
        if volume > vol_avg:
            score += 0.5
            reasons.append(f"{self.tf_name}: Volume Confirmed")
        
        # ADX Check (Trend Strength)
        if adx > 25:
            score += 1
            reasons.append(f"{self.tf_name}: Strong Trend (ADX>25)")
        elif adx < 20:
            score -= 0.5
            reasons.append(f"{self.tf_name}: Weak Trend (ADX<20)")
        
        # Tentukan sinyal berdasarkan score
        if score >= 2:
            signal = "BULLISH"
        elif score <= -2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        
        return signal, score, reasons
    
    def get_data(self):
        """Ambil data penting dari timeframe ini"""
        return {
            'tf': self.tf_name,
            'price': self.last['close'],
            'atr': self.last['ATR'],
            'rsi': self.last['RSI'],
            'adx': self.last['ADX'],
        }

    def plot_and_save_to_signal_folder(self, signal_folder: str, n_candles: int = 30, symbol: str = "Unknown"):
        """
        Plot dan simpan chart ke dalam folder sinyal yang sudah ditentukan.
        
        Args:
            signal_folder: Path ke folder sinyal
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
                    'EMA_SHORT', 'EMA_LONG', 'RSI', 'MACDh_12_26_9', 'ADX']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Kolom wajib belum ada: {missing}")

        # Setup overlay plot
        tf_name = getattr(self, "tf_name", "Chart")
        apds = [
            mpf.make_addplot(df['EMA_SHORT'], color='blue', width=0.8, ylabel='EMA/MACD'),
            mpf.make_addplot(df['EMA_LONG'], color='red', width=0.8),
            mpf.make_addplot(df['RSI'], panel=1, color='purple', ylabel='RSI'),
            mpf.make_addplot(pd.DataFrame({'30': [30]*len(df), '70': [70]*len(df)}, index=df.index),
                             panel=1, color='black', linestyle=':', width=0.8),
            mpf.make_addplot(df['MACDh_12_26_9'], type='bar', panel=2,
                             color=['green' if v >= 0 else 'red' for v in df['MACDh_12_26_9']],
                             ylabel='MACD Hist'),
            mpf.make_addplot(df['ADX'], panel=3, color='orange', width=1.5, ylabel='ADX')
        ]

        # 🔹 Generate filename
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        filename = os.path.join(signal_folder, f"{safe_symbol}_ema_{tf_name}_chart.png")

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