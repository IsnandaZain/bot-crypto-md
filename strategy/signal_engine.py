# strategy/signal_engine.py
# Hanya tambahkan parameter tf_name untuk identifikasi
import pandas as pd
# mplfinance dinonaktifkan — chart tidak tersedia di VPS headless
# import mplfinance as mpf
# import matplotlib.pyplot as plt

from datetime import datetime
import os

class SignalEngine:
    def __init__(self, df, tf_name='base'):
        self.df = df
        self.tf_name = tf_name  # NEW: 'higher', 'base', atau 'lower'
        self.last = df.iloc[-1]
        self.prev = df.iloc[-2]
    
    def analyze(self):
        """Analisis sinyal untuk 1 timeframe tertentu — Confluence-based, bukan scoring arbitrer"""
        signal = "NEUTRAL"
        reasons = []
        confluence_count = 0  # Jumlah indikator yang SEPAKAT
        total_checks = 0      # Total indikator yang dicek

        # Extract values
        ema_short = self.last['EMA_SHORT']
        ema_long = self.last['EMA_LONG']
        close = self.last['close']
        rsi = self.last['RSI']
        macd_hist = self.last['MACDh_12_26_9']
        adx = self.last['ADX']
        volume = self.last['volume']
        vol_avg = self.last['VOL_SMA']

        # ──────────────────────────────────────────────
        # 1. TREND BIAS (EMA Cross) — Filter Utama
        # ──────────────────────────────────────────────
        total_checks += 1
        trend_aligned = False
        if ema_short > ema_long:
            trend_aligned = True
            reasons.append(f"{self.tf_name}: Bullish Trend")
        elif ema_short < ema_long:
            trend_aligned = False
            reasons.append(f"{self.tf_name}: Bearish Trend")

        # ──────────────────────────────────────────────
        # 2. MOMENTUM CONFIRMATION (MACD + RSI)
        #    Hanya valid jika SEARAH dengan trend
        # ──────────────────────────────────────────────
        total_checks += 1
        momentum_agrees = False

        macd_positive = macd_hist > 0
        rsi_bullish = rsi > 50 and rsi < 70  # Bullish tapi belum overbought
        rsi_bearish = rsi < 50 and rsi > 30  # Bearish tapi belum oversold

        if trend_aligned and macd_positive and rsi_bullish:
            momentum_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: Momentum Bullish Confirmed (MACD+, RSI {rsi:.0f})")
        elif not trend_aligned and not macd_positive and rsi_bearish:
            momentum_agrees = True
            confluence_count += 1
            reasons.append(f"{self.tf_name}: Momentum Bearish Confirmed (MACD-, RSI {rsi:.0f})")
        else:
            reasons.append(f"{self.tf_name}: Momentum Diverges (MACD {'+' if macd_positive else '-'} vs RSI {rsi:.0f})")

        # ──────────────────────────────────────────────
        # 3. RSI EXTREME — Reversal Warning (VETO)
        #    Jika RSI > 70 atau < 30, batalkan entry searah
        # ──────────────────────────────────────────────
        total_checks += 1
        rsi_extreme = False
        if rsi > 70:
            rsi_extreme = True
            reasons.append(f"{self.tf_name}: RSI Overbought ({rsi:.0f}) — Reversal Risk")
        elif rsi < 30:
            rsi_extreme = True
            reasons.append(f"{self.tf_name}: RSI Oversold ({rsi:.0f}) — Reversal Risk")

        # ──────────────────────────────────────────────
        # 4. VOLUME CONFIRMATION
        #    Hanya count jika ada momentum agreement
        # ──────────────────────────────────────────────
        total_checks += 1
        volume_confirms = False
        if volume > vol_avg * 1.2:  # 20% di atas average
            volume_confirms = True
            if momentum_agrees:
                confluence_count += 1
                reasons.append(f"{self.tf_name}: Volume Strong ({volume/vol_avg:.1f}x avg)")
        else:
            reasons.append(f"{self.tf_name}: Volume Weak ({volume/vol_avg:.1f}x avg)")

        # ──────────────────────────────────────────────
        # 5. ADX — Trend Strength Filter
        #    ADX < 20 = ranging, hindari entry trend-following
        # ──────────────────────────────────────────────
        total_checks += 1
        trend_strong = False
        if adx > 25:
            trend_strong = True
            confluence_count += 0.5  # ADX bukan konfirmasi arah, tapi penguat
            reasons.append(f"{self.tf_name}: Strong Trend (ADX {adx:.0f})")
        elif adx < 20:
            reasons.append(f"{self.tf_name}: Weak/Ranging (ADX {adx:.0f}) — Caution")

        # ──────────────────────────────────────────────
        # KEPUTUSAN: Confluence Rate, bukan Score Accumulator
        # ──────────────────────────────────────────────
        confluence_rate = confluence_count / total_checks  # 0.0 - 1.0

        # VETO conditions (hard stop — tidak boleh trade)
        if rsi_extreme:
            signal = "NO_TRADE"
            reasons.append(f"{self.tf_name}: VETO — RSI Extreme, tunggu pullback")
        elif not trend_aligned and not momentum_agrees:
            signal = "NO_TRADE"
            reasons.append(f"{self.tf_name}: VETO — Trend dan Momentum bertentangan")
        elif adx < 15:
            signal = "NO_TRADE"
            reasons.append(f"{self.tf_name}: VETO — ADX terlalu lemah, market choppy")
        # Entry conditions: confluence rate >= 60% (3 dari 5 indikator searah)
        elif confluence_rate >= 0.6:
            signal = "BULLISH" if trend_aligned else "BEARISH"
        else:
            signal = "NEUTRAL"
            reasons.append(f"{self.tf_name}: Confluence rendah ({confluence_rate:.0%})")

        # Normalize score ke -3 s/d +3 untuk kompatibilitas dengan MTF
        score = (confluence_rate - 0.5) * 6  # Map 0-1 ke -3到+3
        score = max(-3, min(3, score))

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
        """Chart dinonaktifkan — mplfinance tidak tersedia di VPS"""
        print(f"⚠️  Chart dinonaktifkan (mplfinance tidak tersedia)")
        return None

    def _plot_and_save_to_signal_folder_disabled(self, signal_folder: str, n_candles: int = 30, symbol: str = "Unknown"):
        """
        [DISABLED] Plot dan simpan chart ke dalam folder sinyal yang sudah ditentukan.
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