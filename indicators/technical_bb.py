# indicators/technical_bb.py
import pandas as pd
import pandas_ta as ta
from config import INDICATOR_CONFIG_BB


class IndicatorCalculatorBB:
    def __init__(self, df_dict):
        self.df_dict = df_dict  # {'higher': df, 'base': df, 'lower': df}

    def get_dataframes(self):
        return self.df_dict

    def calculate_all(self):
        cfg = INDICATOR_CONFIG_BB
        processed = {}

        for tf_key, df in self.df_dict.items():
            df_copy = df.copy()

            # Bollinger Bands
            bb = ta.bbands(df_copy['close'], length=cfg['bb_period'], std=cfg['bb_std'])
            # Mapping hasil pandas_ta ke kolom yang diinginkan
            df_copy['bb_upper'] = bb.iloc[:, 2] # BBU
            df_copy['bb_mid'] = bb.iloc[:, 1]   # BBM
            df_copy['bb_lower'] = bb.iloc[:, 0] # BBL

            # BB %B — posisi close relatif terhadap band (0.0=lower, 0.5=mid, 1.0=upper)
            # Digunakan untuk near-touch detection tanpa bergantung pada wick
            band_width = (df_copy['bb_upper'] - df_copy['bb_lower']).replace(0, float('nan'))
            df_copy['bb_pct_b'] = (df_copy['close'] - df_copy['bb_lower']) / band_width

            # RSI
            df_copy['rsi'] = ta.rsi(df_copy['close'], length=cfg['rsi_period'])

            # MACD
            macd = ta.macd(df_copy['close'], fast=cfg['macd_fast'], slow=cfg['macd_slow'], signal=cfg['macd_signal'])
            df_copy['macd'] = macd.iloc[:, 0]        # MACD_Line
            df_copy['macd_signal'] = macd.iloc[:, 2] # Signal_Line
            df_copy['macd_hist'] = macd.iloc[:, 1]   # Histogram

            # Volume MA
            df_copy['vol_ma'] = ta.sma(df_copy['volume'], length=cfg['vol_ma_period'])

            # ATR
            adx_df = ta.adx(df_copy['high'], df_copy['low'], df_copy['close'], length=cfg['adx_period'])
            df_copy['adx'] = adx_df.iloc[:, 0] # Ambil kolom pertama (ADX) tanpa peduli nama suffix-nya
            df_copy['atr'] = ta.atr(df_copy['high'], df_copy['low'], df_copy['close'], length=cfg['atr_period'])
            
            # S/R Proxy (recent swing)
            df_copy['is_res'] = (df_copy['high'] == df_copy['high'].rolling(20).max()).astype(int)
            df_copy['is_sup'] = (df_copy['low'] == df_copy['low'].rolling(20).min()).astype(int)

            processed[tf_key] = df_copy

        self.df_dict = processed
        return processed


            
