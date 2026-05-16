import json
import os
import pandas as pd
from datetime import datetime
from config import TIMEFRAMES
from core.exchange import ExchangeManager
from risk.position_tracker import PositionTracker
from risk.balance_manager import BalanceManager
from utils.logger import BotLogger
from utils.session_report import SessionReport
from utils.telegram_notifier import TelegramNotifier


# ─────────────────────────────────────────────────────────────────────────────
# WATCHLIST AUTO-UPDATE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_FILE = os.path.join('data', 'watchlist.json')

FIXED_PAIRS = [
    'SOL/USDT:USDT',
    'SUI/USDT:USDT',
    'HYPE/USDT:USDT',
    'DOGE/USDT:USDT',
    'PENGU/USDT:USDT',
]

WATCHLIST_TOP_N   = 20           # total pairs target
WATCHLIST_MIN_VOL = 25_000_000   # $25M USDT minimum 24h volume

WATCHLIST_BLACKLIST = {
    'USDC', 'BUSD', 'TUSD', 'FDUSD', 'DAI', 'USDE', 'USDP',  # stablecoin
    'BTCDOM', 'DEFI',                                           # index
}

_LEVERAGE_TOKEN_SUFFIXES = ('3L', '3S', 'UP', 'DOWN', 'BULL', 'BEAR')


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

    def auto_update_watchlist(self, notifier=None, open_pairs: set = None) -> bool:
        """
        Auto-update watchlist dengan top N pairs by 24h USDT volume dari Bybit.

        Aturan:
        - FIXED_PAIRS tidak pernah dihapus
        - Pair dalam open_pairs terlindungi — tidak bisa dikeluarkan
        - Leverage token (*3L/*3S dll) dan stablecoin otomatis dikecualikan
        - Update file watchlist.json di-tempat (hot-reload oleh scan cycle)

        Args:
            notifier   : TelegramNotifier instance (opsional)
            open_pairs : set symbol yang saat ini OPEN (opsional, untuk proteksi)
        """
        print("🔄 [AUTO-WATCHLIST] Mengambil data volume dari Bybit...")

        try:
            tickers = self.exchange.fetch_tickers()
        except Exception as e:
            print(f"❌ [AUTO-WATCHLIST] Gagal fetch tickers: {e}")
            return False

        # ── Filter: hanya USDT perpetual yang memenuhi kriteria ──────────────
        candidates = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith('/USDT:USDT'):
                continue

            base = symbol.split('/')[0]

            if base in WATCHLIST_BLACKLIST:
                continue

            if any(base.endswith(sfx) for sfx in _LEVERAGE_TOKEN_SUFFIXES):
                continue

            vol = ticker.get('quoteVolume') or 0
            if vol < WATCHLIST_MIN_VOL:
                continue

            candidates.append((symbol, vol))

        if not candidates:
            print("⚠️ [AUTO-WATCHLIST] Tidak ada pair yang memenuhi kriteria volume")
            return False

        candidates.sort(key=lambda x: x[1], reverse=True)

        # ── Bangun slot auto (TOP_N dikurangi jumlah fixed pair) ─────────────
        auto_slots = WATCHLIST_TOP_N - len(FIXED_PAIRS)
        auto_pairs = []
        for symbol, _ in candidates:
            if symbol in FIXED_PAIRS:
                continue
            auto_pairs.append(symbol)
            if len(auto_pairs) >= auto_slots:
                break

        # ── Final watchlist: fixed + auto (deduplicated, order terjaga) ──────
        seen: set = set()
        final_watchlist = []
        for sym in FIXED_PAIRS + auto_pairs:
            if sym not in seen:
                seen.add(sym)
                final_watchlist.append(sym)

        # ── Lindungi pair OPEN ────────────────────────────────────────────────
        for op in (open_pairs or set()):
            if op not in seen:
                final_watchlist.append(op)
                seen.add(op)
                print(f"   🔒 Pair OPEN dilindungi: {op}")

        # ── Load watchlist lama untuk diff ────────────────────────────────────
        try:
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            old_watchlist = set(old_data.get('watchlist', []))
        except Exception:
            old_data      = {}
            old_watchlist = set()

        new_set = set(final_watchlist)
        added   = sorted(new_set - old_watchlist)
        removed = sorted(old_watchlist - new_set)

        # ── Simpan ────────────────────────────────────────────────────────────
        save_data = {
            '_comment'   : old_data.get('_comment', 'Dikelola otomatis oleh bot'),
            '_categories': old_data.get('_categories', {}),
            '_updated'   : datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '_fixed'     : FIXED_PAIRS,
            'watchlist'  : final_watchlist,
        }
        try:
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ [AUTO-WATCHLIST] Gagal save: {e}")
            return False

        print(
            f"✅ [AUTO-WATCHLIST] Selesai: {len(final_watchlist)} pairs | "
            f"+{len(added)} masuk, -{len(removed)} keluar"
        )
        if added:
            print(f"   + Masuk : {', '.join(p.split('/')[0] for p in added)}")
        if removed:
            print(f"   - Keluar: {', '.join(p.split('/')[0] for p in removed)}")

        if notifier:
            notifier.notify_watchlist_updated(added, removed, final_watchlist)

        return True

# ─────────────────────────────────────────────────────────────────────────────
# MONITOR MODE — hanya cek TP/SL posisi aktif (off-hours, 02:00-14:00)
# ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def monitor_positions(session: SessionReport = None, notifier: TelegramNotifier = None):
        """
        Mode monitor (off-hours) — hanya cek TP/SL/partial posisi aktif.
        Tidak scan sinyal baru. Hemat resource & API quota.
        """
        tracker     = PositionTracker()
        balance_mgr = BalanceManager()

        open_positions = [p for p in tracker.positions if p['status'] == 'OPEN']
        if not open_positions:
            print(f"💤 [MONITOR] {datetime.now().strftime('%H:%M:%S')} | Tidak ada posisi aktif")
            return

        # Connect exchange
        exchange_mgr = ExchangeManager()
        exchange     = exchange_mgr.connect()
        if not exchange:
            return

        # Fetch harga hanya untuk pair yang punya posisi aktif (hemat quota)
        open_symbols   = [p['symbol'] for p in open_positions]
        current_prices = {}
        for symbol in open_symbols:
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_prices[symbol] = ticker['last']
            except Exception:
                pass

        if not current_prices:
            return

        # ── Monitoring (sama seperti bagian prioritas 1 di scan_market) ──────────
        tracker.update_unrealized_pnl(current_prices)

        _history_len_before = len(tracker.history)
        tracker.update_partial_tp(current_prices)

        # ⭐ Update balance dari partial TP (TP1 / TP2)
        new_partials = [r for r in tracker.history[_history_len_before:] if r.get('is_partial')]
        if new_partials:
            balance_mgr.update_from_closed_positions(new_partials)
            if notifier:
                for rec in new_partials:
                    notifier.notify_partial_tp(rec)
            if session:
                session.record_closed(new_partials)

        tracker.update_breakeven_sl(current_prices)
        closed_positions = tracker.check_tp_sl(current_prices)

        if closed_positions:
            BotLogger.log_closed_positions(closed_positions)
            balance_mgr.update_from_closed_positions(closed_positions)
            if notifier:
                for rec in closed_positions:
                    notifier.notify_position_closed(rec)
            if session:
                session.record_closed(closed_positions)

        tracker.save_positions()

        open_count = len([p for p in tracker.positions if p['status'] == 'OPEN'])
        print(
            f"💤 [MONITOR] {datetime.now().strftime('%H:%M:%S')} "
            f"| Posisi aktif: {open_count} "
            f"| Harga dicek: {len(current_prices)}"
        )
