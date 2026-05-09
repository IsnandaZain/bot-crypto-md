
EXCHANGE_CONFIG = {
    "name": "bybit",
    "defaultType": "swap", # swap, linear, spot
    "enableRateLimit": True
}

# DAFTAR COIN YANG DI SCAN dikelola di data/watchlist.json
# Edit file tersebut untuk menambah/hapus coin tanpa restart bot

# KONFIGURASI MULTI-TIMEFRAME
TIMEFRAMES = {
    'base': '1h', # Signal
    'lower': '15m' # Entry
}

TRADING_CONFIG = {
    'leverage': 20,
    'max_position_size_pct': 4,

    # ⭐ ACCOUNT SETTINGS (Untuk Position Sizing)
    'account_balance_usdt': 66,  # ⚠️ ISI DENGAN BALANCE ANDA (Manual/Paper)
    'auto_fetch_balance': False,   # True jika mau ambil dari API (butuh API Key)

    # ⭐ MAX SIMULTANEOUS POSITIONS (BARU)
    'max_open_positions': 8,  # Maksimal 3 posisi terbuka bersamaan
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

INDICATOR_CONFIG_BB = {
    'bb_period': 20,
    'bb_std': 2.0,
    'rsi_period': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'vol_ma_period': 20,
    'atr_period': 14,
    'adx_period': 14
}

RISK_CONFIG = {
    # ⭐ ATR Multiplier lebih tinggi untuk crypto volatility
    'sl_atr_multiplier': 3.5,          # Naik dari 2.5 → 3.5
    
    # ⭐ Guardrails aman untuk leverage 20x (liquidasi ~4.5-5% dari entry)
    'sl_min_pct': 0.010,               # Min SL 1% dari entry
    'sl_max_pct': 0.030,               # Max SL 3% dari entry (aman, jauh dari liquidasi)
    
    # ⭐ Risk:Reward lebih agresif
    'rr_ratio': 2,                   # Naik dari 2.0 → 2.5 (TP lebih jauh)
    
    # ⭐ Hybrid SL Config
    'use_hybrid_sl': True,
    'sr_lookback': 30,                 # Naik dari 20 → 30 candle (S/R lebih signifikan)
    'sr_buffer_pct': 0.01,             # Naik dari 0.5% → 1% (buffer lebih besar)
    
    # ⭐ TP Minimum Guardrail (BARU)
    'tp_min_pct': 0.010,               # TP minimal 1% dari entry

    # ⭐ BREAKEVEN SL CONFIG
    # Saat unrealized profit (dalam % equity) mencapai threshold ini,
    # SL otomatis digeser ke entry price + buffer kecil untuk cover fee.
    # Contoh: profit_trigger_pct=30 → saat profit >= 30% dari margin,
    #         SL digeser ke entry agar posisi tidak bisa rugi.
    'breakeven_profit_trigger_pct': 30,  # % dari margin (bukan % dari harga)
    'breakeven_fee_buffer': 0.0012,      # 0.12% untuk cover entry+exit fee

    # ⭐ PARTIAL TP + SL LOCK CONFIG
    # Saat TP1 tercapai → geser SL ke entry (breakeven) jika belum ter-trigger
    # Saat TP2 tercapai → geser SL ke TP1 (lock sebagian profit)
    # TP3 → tutup posisi penuh (final exit)
    'partial_tp_enabled': True,
    'tp1_sl_lock_to': 'breakeven',  # 'breakeven' atau 'tp1' (agresif)
    'tp2_sl_lock_to': 'tp1',        # geser SL ke TP1 setelah TP2 hit
}

# ⭐ STORAGE CONFIG (BARU)
STORAGE_CONFIG = {
    'data_folder': 'data',
    'positions_file': 'active_positions.json',
    'max_history_records': 100,
}

