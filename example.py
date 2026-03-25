import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime


def fetch_crypto_data():
    exchange = ccxt.bybit({
        "enableRateLimit": True,
        "options": {
            "defaultType": "linear"
        }
    })

    # Definisi Parameter
    symbol = "TAO/USDT:USDT"
    timeframe = "1h"
    limit = 100

    print(f"Mengambil data {symbol} dari Bybit ({timeframe})...")

    try:
        # Fetch OHLCV Data
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

        # Konversi ke DataFrame Pandas
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Pre-processing Data
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Pastikan tipe data numerik adalat float
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].astype(float)

        df.to_csv("TAO.csv")

        # Hitung indikator Teknikal
        df['EMA_14'] = ta.ema(df['close'], length=14)
        df['EMA_50'] = ta.ema(df['close'], length=50)

        # Bollinger Bands (Length 20, StdDev 2)
        bbands = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1) # Gabungkan kolom BB ke DataFrame utama

        # RSI (Relative Strength Index)
        df['RSI'] = ta.rsi(df['close'], length=14)

        # 7. Tampilkan Hasil Terakhir
        print("\n--- 5 Data Terakhir beserta Indikator ---")
        # Memilih kolom tertentu agar tampilan rapi
        display_cols = ['timestamp', 'close', 'EMA_14', 'BBM_20_2.0', 'BBU_20_2.0', 'RSI']
        print(df[display_cols].tail())

        # Contoh Logika Sederhana (Opsional)
        last_close = df['close'].iloc[-1]
        last_ema = df['EMA_14'].iloc[-1]
        last_rsi = df['RSI'].iloc[-1]

        print("\n--- Analisis Singkat ---")
        print(f"Harga Terakhir: {last_close}")
        print(f"EMA 14: {last_ema:.2f}")
        print(f"RSI: {last_rsi:.2f}")
        
        if last_close > last_ema:
            print("Trend: Bullish (Harga di atas EMA 14)")
        else:
            print("Trend: Bearish (Harga di bawah EMA 14)")
            
        if last_rsi > 70:
            print("Status RSI: Overbought (Jenuh Beli)")
        elif last_rsi < 30:
            print("Status RSI: Oversold (Jenuh Jual)")
        else:
            print("Status RSI: Neutral")

        return df

    except ccxt.NetworkError as e:
        print(f"Terjadi kesalahan jaringan: {e}")
    except ccxt.ExchangeError as e:
        print(f"Terjadi kesalahan dari exchange: {e}")
    except Exception as e:
        print(f"Terjadi kesalahan umum: {e}")

if __name__ == "__main__":
    fetch_crypto_data()