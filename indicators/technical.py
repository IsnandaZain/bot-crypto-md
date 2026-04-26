# indicators/technical.py
import pandas as pd
import pandas_ta as ta
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
            df_copy['EMA_SHORT'] = ta.ema(df_copy['close'], length=cfg['ema_short'])
            df_copy['EMA_LONG'] = ta.ema(df_copy['close'], length=cfg['ema_long'])
            
            # RSI
            df_copy['RSI'] = ta.rsi(df_copy['close'], length=cfg['rsi_period'])
            
            # MACD
            macd = ta.macd(df_copy['close'], fast=cfg['macd_fast'], slow=cfg['macd_slow'], signal=cfg['macd_signal'])
            df_copy = pd.concat([df_copy, macd], axis=1)
            
            # ADX & ATR
            df_copy['ADX'] = ta.adx(df_copy['high'], df_copy['low'], df_copy['close'], length=cfg['adx_period'])['ADX_14']
            df_copy['ATR'] = ta.atr(df_copy['high'], df_copy['low'], df_copy['close'], length=cfg['atr_period'])
            
            # Volume Avg
            df_copy['VOL_SMA'] = ta.sma(df_copy['volume'], length=20)
            
            processed[tf_key] = df_copy
        
        self.df_dict = processed
        return processed
    
    def get_dataframes(self):
        return self.df_dict
    

