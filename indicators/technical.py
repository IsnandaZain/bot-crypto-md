# indicators/technical.py
import pandas as pd
import ta
from config import INDICATOR_CONFIG

class IndicatorCalculator:
    def __init__(self, df_dict):
        self.df_dict = df_dict  # {'higher': df, 'base': df, 'lower': df}
    
    def calculate_all(self):
        cfg = INDICATOR_CONFIG
        processed = {}
        
        for tf_key, df in self.df_dict.items():
            df_copy = df.copy()
            
            # EMA
            df_copy['EMA_SHORT'] = ta.trend.EMAIndicator(
                close=df_copy['close'], window=cfg['ema_short']
            ).ema_indicator()
            df_copy['EMA_LONG'] = ta.trend.EMAIndicator(
                close=df_copy['close'], window=cfg['ema_long']
            ).ema_indicator()
            
            # RSI
            df_copy['RSI'] = ta.momentum.RSIIndicator(
                close=df_copy['close'], window=cfg['rsi_period']
            ).rsi()
            
            # MACD
            macd_ind = ta.trend.MACD(
                close=df_copy['close'],
                window_fast=cfg['macd_fast'],
                window_slow=cfg['macd_slow'],
                window_sign=cfg['macd_signal']
            )
            df_copy['MACD_12_26_9']      = macd_ind.macd()
            df_copy['MACDs_12_26_9']     = macd_ind.macd_signal()
            df_copy['MACDh_12_26_9']     = macd_ind.macd_diff()
            
            # ADX & ATR
            adx_ind = ta.trend.ADXIndicator(
                high=df_copy['high'],
                low=df_copy['low'],
                close=df_copy['close'],
                window=cfg['adx_period']
            )
            df_copy['ADX'] = adx_ind.adx()
            df_copy['ATR'] = ta.volatility.AverageTrueRange(
                high=df_copy['high'],
                low=df_copy['low'],
                close=df_copy['close'],
                window=cfg['atr_period']
            ).average_true_range()
            
            # Volume Avg
            df_copy['VOL_SMA'] = df_copy['volume'].rolling(window=20).mean()
            
            processed[tf_key] = df_copy
        
        self.df_dict = processed
        return processed
    
    def get_dataframes(self):
        return self.df_dict
    

