# indicators/support_resistance.py
import pandas as pd
from typing import List, Tuple


def _is_support(df: pd.DataFrame, i: int, window: int) -> bool:
    """Cek apakah candle ke-i adalah pivot low (support)"""
    left_min = df['low'].iloc[i - window:i].min()
    right_min = df['low'].iloc[i + 1:i + 1 + window].min()
    return df['low'].iloc[i] <= min(left_min, right_min)


def _is_resistance(df: pd.DataFrame, i: int, window: int) -> bool:
    """Cek apakah candle ke-i adalah pivot high (resistance)"""
    left_max = df['high'].iloc[i - window:i].max()
    right_max = df['high'].iloc[i + 1:i + 1 + window].max()
    return df['high'].iloc[i] >= max(left_max, right_max)


def _merge_levels(levels: List[float], threshold_pct: float) -> List[float]:
    """Gabungkan level-level berdekatan berdasarkan persentase threshold"""
    if not levels:
        return []

    levels = sorted(set(levels))
    merged = []
    current_group = [levels[0]]

    for price in levels[1:]:
        if (price - current_group[-1]) / current_group[-1] <= threshold_pct:
            current_group.append(price)
        else:
            merged.append(sum(current_group) / len(current_group))
            current_group = [price]

    merged.append(sum(current_group) / len(current_group))
    return merged


def _detect_levels(
    df: pd.DataFrame,
    window: int,
    min_volume_multiplier: float,
) -> Tuple[List[float], List[float]]:
    """
    Scan pivot low/high dengan filter volume, kembalikan
    list supports dan resistances setelah merge.
    """
    avg_volume = df['volume'].mean()
    supports, resistances = [], []

    for i in range(window, len(df) - window):
        if df['volume'].iloc[i] < avg_volume * min_volume_multiplier:
            continue
        if _is_support(df, i, window):
            supports.append(df['low'].iloc[i])
        if _is_resistance(df, i, window):
            resistances.append(df['high'].iloc[i])

    # Threshold dinamis: rata-rata True Range relatif terhadap close terakhir
    avg_tr = (df['high'] - df['low']).mean()
    current_price = df['close'].iloc[-1]
    threshold_pct = max(0.005, avg_tr / current_price)

    supports = _merge_levels(supports, threshold_pct)
    resistances = _merge_levels(resistances, threshold_pct)
    return supports, resistances


class SupportResistanceDetector:
    def __init__(self, df_dict: dict, window: int = 3, min_volume_multiplier: float = 1.0):
        """
        Parameters
        ----------
        df_dict : dict
            Output dari DataFetcher.fetch_multi_timeframe()
            Minimal harus punya key 'base'. Key 'lower' opsional.
        window : int
            Jumlah candle kiri/kanan untuk validasi pivot. Default 3.
        min_volume_multiplier : float
            Candle hanya dianggap valid jika volume >= avg_volume * multiplier.
        """
        self.df_dict = {k: v.copy() for k, v in df_dict.items()}
        self.window = window
        self.min_volume_multiplier = min_volume_multiplier

    def _annotate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tambahkan 4 kolom ke df:
          - is_support        : 1 jika candle ini adalah pivot support
          - is_resistance     : 1 jika candle ini adalah pivot resistance
          - nearest_support   : level support terdekat di bawah close terakhir
          - nearest_resistance: level resistance terdekat di atas close terakhir
        """
        window = self.window
        supports, resistances = _detect_levels(df, window, self.min_volume_multiplier)

        # Tandai candle pivot
        df['is_support'] = 0
        df['is_resistance'] = 0
        for i in range(window, len(df) - window):
            if df['volume'].iloc[i] < df['volume'].mean() * self.min_volume_multiplier:
                continue
            if _is_support(df, i, window):
                df.at[df.index[i], 'is_support'] = 1
            if _is_resistance(df, i, window):
                df.at[df.index[i], 'is_resistance'] = 1

        # Level terdekat dari close candle terakhir
        current_price = df['close'].iloc[-1]

        below = [s for s in supports if s < current_price]
        above = [r for r in resistances if r > current_price]

        df['nearest_support'] = max(below) if below else float('nan')
        df['nearest_resistance'] = min(above) if above else float('nan')

        return df

    def calculate_all(self) -> dict:
        """
        Proses 'base' dan 'lower' (jika ada), tambahkan kolom S/R,
        kembalikan df_dict yang sudah dianotasi.
        """
        target_keys = [k for k in ('base', 'lower') if k in self.df_dict]

        for key in target_keys:
            self.df_dict[key] = self._annotate(self.df_dict[key])

        return self.df_dict

    def get_dataframes(self) -> dict:
        return self.df_dict
