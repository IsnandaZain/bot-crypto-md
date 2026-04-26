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