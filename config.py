
EXCHANGE_CONFIG = {
    "name": "bybit",
    "defaultType": "swap", # swap, linear, spot
    "enableRateLimit": True
}

# DAFTAR COIN YANG DI SCAN
WATCHLIST = [
    'SOL/USDT:USDT',
    'XRP/USDT:USDT',
    'HYPE/USDT:USDT',
    'ADA/USDT:USDT',
    'TAO/USDT:USDT',
    'SUI/USDT:USDT',
    'ASTER/USDT:USDT',
    'DOGE/USDT:USDT',
    'PENDLE/USDT:USDT',
    'FARTCOIN/USDT:USDT',
    'PENGU/USDT:USDT',
    'ARB/USDT:USDT',
    'NEAR/USDT:USDT'
]

"""
'TAO/USDT:USDT',
'SUI/USDT:USDT',
'SOL/USDT:USDT',
'FARTCOIN/USDT:USDT',
'DOGE/USDT:USDT'
"""

# KONFIGURASI MULTI-TIMEFRAME
TIMEFRAMES = {
    'higher': '4h', # Trend
    'base': '1h', # Signal
    'lower': '15m' # Entry
}

TRADING_CONFIG = {
    'leverage': 20,
    'max_position_size_pct': 4,

    # ⭐ ACCOUNT SETTINGS (Untuk Position Sizing)
    'account_balance_usdt': 50,  # ⚠️ ISI DENGAN BALANCE ANDA (Manual/Paper)
    'auto_fetch_balance': False,   # True jika mau ambil dari API (butuh API Key)

    # ⭐ MAX SIMULTANEOUS POSITIONS (BARU)
    'max_open_positions': 5,  # Maksimal 3 posisi terbuka bersamaan
}

# ⭐ ORDER EXECUTION SETTINGS (BARU)
ORDER_CONFIG = {
    'order_type': 'market',        # 'market' atau 'limit'
    'time_in_force': 'GTC',        # Good Till Cancel
    'reduce_only': False,          # False untuk open position
    'close_on_trigger': False,     # False untuk open position
    'take_profit_trigger': 'last', # 'last' atau 'index'
    'stop_loss_trigger': 'last',
}

"""
INDIKATOR
EMA 200 - Trend Filter Utama
EMA 50 - Trend Menengah + Entry Zone
RSI - Momentum + Divergence
MACD - Momentum Konfirmasi
ATR - Volatility + Stop Loss
ADX - Kekuatan Trend
Bollinger Bands - Volatility + S/R Dinamis
"""
INDICATOR_CONFIG = {
    'ema_short': 50,
    'ema_long': 200,
    'rsi_period': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'atr_period': 14,
    'adx_period': 14
}

RISK_CONFIG = {
    # ⭐ ATR Multiplier lebih tinggi untuk crypto volatility
    'sl_atr_multiplier': 3.5,          # Naik dari 2.5 → 3.5
    
    # ⭐ Guardrails yang lebih longgar
    'sl_min_pct': 0.03,                # Naik dari 1% → 3% (minimum SL)
    'sl_max_pct': 0.08,                # Naik dari 5% → 8% (maximum SL)
    
    # ⭐ Risk:Reward lebih agresif
    'rr_ratio': 2.5,                   # Naik dari 2.0 → 2.5 (TP lebih jauh)
    
    # ⭐ Hybrid SL Config
    'use_hybrid_sl': True,
    'sr_lookback': 30,                 # Naik dari 20 → 30 candle (S/R lebih signifikan)
    'sr_buffer_pct': 0.01,             # Naik dari 0.5% → 1% (buffer lebih besar)
    
    # ⭐ TP Minimum Guardrail (BARU)
    'tp_min_pct': 0.03,                # TP minimal 3% dari entry
}

# ⭐ STORAGE CONFIG (BARU)
STORAGE_CONFIG = {
    'data_folder': 'data',
    'positions_file': 'active_positions.json',
    'max_history_records': 50,
}

