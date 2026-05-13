
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
    'max_position_size_pct': 2.5,      # Turun dari 4% → 2.5% (risk ~1.5% balance per trade)

    # ⭐ ACCOUNT SETTINGS (Untuk Position Sizing)
    'account_balance_usdt': 66,  # ⚠️ ISI DENGAN BALANCE ANDA (Manual/Paper)
    'auto_fetch_balance': False,   # True jika mau ambil dari API (butuh API Key)

    # ⭐ MAX SIMULTANEOUS POSITIONS
    'max_open_positions': 10,       # Turun dari 8 → 6 (worst case 15% balance terpakai)

    # ⭐ MAX DIRECTIONAL POSITIONS (hindari overexposed satu arah saat market crash)
    'max_long_positions': 5,       # Max 4 posisi LONG bersamaan
    'max_short_positions': 5,      # Max 4 posisi SHORT bersamaan
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
    # ⭐ TP1 FLOOR — minimum gain TP1 terhadap entry price
    # 2% harga = 40% gain dengan leverage 20x
    # TP1 akan diambil yang lebih dekat ke entry antara BB Mid dan floor ini
    'tp1_floor_pct': 0.02,             # 2% dari entry
    # ⭐ BREAKEVEN SL CONFIG
    # Saat unrealized profit (dalam % equity) mencapai threshold ini,
    # SL otomatis digeser ke entry price + buffer kecil untuk cover fee.
    # Contoh: profit_trigger_pct=30 → saat profit >= 30% dari margin,
    #         SL digeser ke entry agar posisi tidak bisa rugi.
    'breakeven_profit_trigger_pct': 30,  # % dari margin (bukan % dari harga)
    'breakeven_fee_buffer': 0.0012,      # 0.12% untuk cover entry+exit fee

    # ⭐ PARTIAL TP + SL LOCK CONFIG
    'partial_tp_enabled': True,
    # TP1 hit → tutup 50% posisi, geser SL ke +10% margin profit (0.5% harga di leverage 20x)
    'tp1_partial_close_pct': 0.50,       # Tutup 50% saat TP1
    'tp1_sl_profit_margin_pct': 0.10,    # SL baru = entry + (0.10 / leverage) → 10% margin profit
    # TP2 hit → tutup semua sisa posisi
    # SL hit kapanpun → tutup semua sisa
}

# ⭐ STORAGE CONFIG (BARU)
STORAGE_CONFIG = {
    'data_folder': 'data',
    'positions_file': 'active_positions.json',
    'max_history_records': 100,
}

