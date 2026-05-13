# indicators/technical_bb.py
import pandas as pd
import ta
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
            bb = ta.volatility.BollingerBands(
                close=df_copy['close'],
                window=cfg['bb_period'],
                window_dev=cfg['bb_std']
            )
            df_copy['bb_upper'] = bb.bollinger_hband()
            df_copy['bb_mid']   = bb.bollinger_mavg()
            df_copy['bb_lower'] = bb.bollinger_lband()

            # BB %B — posisi close relatif terhadap band (0.0=lower, 0.5=mid, 1.0=upper)
            band_width = (df_copy['bb_upper'] - df_copy['bb_lower']).replace(0, float('nan'))
            df_copy['bb_pct_b'] = (df_copy['close'] - df_copy['bb_lower']) / band_width

            # RSI
            df_copy['rsi'] = ta.momentum.RSIIndicator(
                close=df_copy['close'],
                window=cfg['rsi_period']
            ).rsi()

            # MACD
            macd_ind = ta.trend.MACD(
                close=df_copy['close'],
                window_fast=cfg['macd_fast'],
                window_slow=cfg['macd_slow'],
                window_sign=cfg['macd_signal']
            )
            df_copy['macd']        = macd_ind.macd()
            df_copy['macd_signal'] = macd_ind.macd_signal()
            df_copy['macd_hist']   = macd_ind.macd_diff()

            # Volume MA
            df_copy['vol_ma'] = df_copy['volume'].rolling(window=cfg['vol_ma_period']).mean()

            # ADX
            adx_ind = ta.trend.ADXIndicator(
                high=df_copy['high'],
                low=df_copy['low'],
                close=df_copy['close'],
                window=cfg['adx_period']
            )
            df_copy['adx'] = adx_ind.adx()

            # ATR
            df_copy['atr'] = ta.volatility.AverageTrueRange(
                high=df_copy['high'],
                low=df_copy['low'],
                close=df_copy['close'],
                window=cfg['atr_period']
            ).average_true_range()

            # S/R Proxy (recent swing)
            df_copy['is_res'] = (df_copy['high'] == df_copy['high'].rolling(20).max()).astype(int)
            df_copy['is_sup'] = (df_copy['low'] == df_copy['low'].rolling(20).min()).astype(int)

            processed[tf_key] = df_copy

        self.df_dict = processed
        return processed


            
