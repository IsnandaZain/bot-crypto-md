import pandas as pd
from config import TIMEFRAMES


class DataFetcher:
    def __init__(self, exchange):
        self.exchange = exchange

    def fetch_ohlcv(self, symbol, timeframe, limit=300):
        """Fetch single TF"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].astype('float64')
            return df
        except Exception as e:
            print(f"❌ Error fetch {symbol} {timeframe}: {e}")
            return None
        
    def fetch_multi_timeframe(self, symbol):
        """Fetch semua TF untuk 1 simbol"""
        dataframes = {}
        for tf_key, tf_value in TIMEFRAMES.items():
            limit = 300
            df = self.fetch_ohlcv(symbol, tf_value, limit=limit)
            if df is not None:
                dataframes[tf_key] = df
            else:
                print(f"⚠️ Gagal ambil data {tf_value} untuk {symbol}")
                return None  # Jika satu TF gagal, batalkan simbol ini
        return dataframes  # Return: {'higher': df, 'base': df, 'lower': df}
