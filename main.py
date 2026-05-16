# main.py
import time
import signal
from core.exchange import ExchangeManager
from core.data_fetcher import DataFetcher
from risk.manager import RiskManager
from risk.position_sizer import PositionSizer
from risk.position_tracker import PositionTracker
from risk.balance_manager import BalanceManager  # ⭐ Balance dinamis
from utils.logger import BotLogger
from utils.file_manager import get_today_folder, create_signal_folder
from utils.session_report import SessionReport
from utils.telegram_notifier import TelegramNotifier
from utils.narrative import NarrativeBuilder

from strategy.mtf_confluence import MTFConfluence
from strategy.mtf_confluence_bb import MTFConfluenceBB

from strategy.detect_regime_bb import DetectRegimeBB

from indicators.technical import IndicatorCalculator
from indicators.technical_bb import IndicatorCalculatorBB

from config import TRADING_CONFIG
from datetime import datetime
import os
import json

WATCHLIST_FILE = os.path.join('data', 'watchlist.json')

def load_watchlist() -> list:
    """Baca watchlist dari data/watchlist.json (hot-reload setiap scan cycle)"""
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        wl = data.get('watchlist', [])
        if not wl:
            print(f"⚠️  watchlist.json kosong, tidak ada coin yang di-scan")
        return wl
    except FileNotFoundError:
        print(f"⚠️  {WATCHLIST_FILE} tidak ditemukan, watchlist kosong")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Format watchlist.json tidak valid: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SESSION TIME HELPER
# ─────────────────────────────────────────────────────────────────────────────

def is_active_session() -> bool:
    """
    Kembalikan True jika saat ini dalam jam sesi trading aktif.
    Sesi aktif : 14:00 – 02:00 WIB (hari berikutnya)
    Off-hours   : 02:00 – 14:00 WIB
    """
    h = datetime.now().hour
    return h >= 12 or h < 3


def scan_market(session: SessionReport = None, notifier: TelegramNotifier = None):
    print("\n" + "="*70)
    print("🚀 Memulai Multi-Coin MTF Scanner...")
    print("="*70)

    # ⭐ LOAD WATCHLIST (hot-reload dari data/watchlist.json)
    WATCHLIST = load_watchlist()
    print(f"📋 Watchlist ({len(WATCHLIST)} coin): {', '.join(WATCHLIST)}")

    # 0. ⭐ BUAT FOLDER TANGGAL OTOMATIS
    today_folder = get_today_folder()
    print(f"📁 Folder sinyal hari ini: {today_folder}")

    # 1. Connect Exchange
    exchange_mgr = ExchangeManager()
    exchange = exchange_mgr.connect()
    if not exchange:
        return
    
    # 2. Initialize Position Tracker (Load dari JSON)
    tracker = PositionTracker()

    # 3. ⭐ Initialize Balance Manager (Dynamic Balance)
    balance_mgr = BalanceManager()
    account_balance = balance_mgr.get_balance()
    print(f"💰 Balance saat ini: ${account_balance:.2f}")
    
    # 4. Fetch Current Prices untuk Semua Koin (Untuk Cek TP/SL)
    current_prices = {}
    for symbol in WATCHLIST:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_prices[symbol] = ticker['last']
        except:
            pass
    
    # 5. ⭐ PRIORITAS 1: Cek Posisi Aktif (TP/SL Check)
    print("\n" + "="*70)
    print("📍 CEK POSISI AKTIF (TP/SL)")
    print("="*70)
    
    tracker.update_unrealized_pnl(current_prices)

    # Catat panjang history sebelum update_partial_tp untuk deteksi record baru
    _history_len_before = len(tracker.history)
    tracker.update_partial_tp(current_prices)

    # ⭐ Update balance dari partial TP (TP1 / TP2) yang baru ter-trigger
    new_partial_records = [r for r in tracker.history[_history_len_before:] if r.get('is_partial')]
    if new_partial_records:
        balance_mgr.update_from_closed_positions(new_partial_records)
        account_balance = balance_mgr.get_balance()
        if notifier:
            for rec in new_partial_records:
                notifier.notify_partial_tp(rec)
        if session:
            session.record_closed(new_partial_records)

    tracker.update_breakeven_sl(current_prices)
    closed_positions = tracker.check_tp_sl(current_prices)

    # Log closed positions
    if closed_positions:
        BotLogger.log_closed_positions(closed_positions)
        # ⭐ Update balance dari PnL posisi yang di-close (final close)
        balance_mgr.update_from_closed_positions(closed_positions)
        # Refresh balance untuk scan berikutnya
        account_balance = balance_mgr.get_balance()
        # ⭐ Notifikasi posisi yang fully closed
        if notifier:
            for rec in closed_positions:
                notifier.notify_position_closed(rec)
        # ⭐ Catat ke session report
        if session:
            session.record_closed(closed_positions)

    # 6. ⭐ PRIORITAS 2: Cek Sinyal Baru (Hanya Jika Ada Slot)
    print("\n" + "="*70)
    print("🔍 CEK SINYAL BARU")
    print("="*70)

    summary = tracker.get_summary()
    open_positions_count = summary['total_positions']
    max_positions        = TRADING_CONFIG['max_open_positions']
    max_long             = TRADING_CONFIG.get('max_long_positions', max_positions)
    max_short            = TRADING_CONFIG.get('max_short_positions', max_positions)

    # Hitung posisi LONG dan SHORT yang sedang aktif
    all_positions = summary['positions']
    long_count  = sum(1 for p in all_positions if p['status'] == 'OPEN' and p['signal'] == 'LONG')
    short_count = sum(1 for p in all_positions if p['status'] == 'OPEN' and p['signal'] == 'SHORT')

    print(f"Posisi Terbuka : {open_positions_count}/{max_positions}")
    print(f"Long / Short   : {long_count}/{max_long}  |  {short_count}/{max_short}")

    new_signals = []

    # Hanya cari sinyal baru jika masih ada slot total
    if open_positions_count < max_positions:
        fetcher = DataFetcher(exchange)

        for symbol in WATCHLIST:
            print(f"\n🔍 Scanning {symbol}...")

            # Cek apakah ada posisi aktif untuk koin ini
            active_positions = tracker.get_active_positions(symbol)
            existing_signal = None

            # Tentukan arah sinyal yang boleh dicari
            if not active_positions:
                # Cek slot directional sebelum izinkan scan
                long_ok  = long_count  < max_long
                short_ok = short_count < max_short
                if not long_ok and not short_ok:
                    print(f"⛔ Slot LONG ({long_count}/{max_long}) dan SHORT ({short_count}/{max_short}) penuh → Skip")
                    continue
                elif not long_ok:
                    print(f"⚠️  Slot LONG penuh ({long_count}/{max_long}) → Hanya cari SHORT")
                elif not short_ok:
                    print(f"⚠️  Slot SHORT penuh ({short_count}/{max_short}) → Hanya cari LONG")
                else:
                    print("📍 Tidak ada posisi aktif → Mencari semua peluang")
                existing_signal = None
            else:
                active_sides = list(active_positions.keys())

                if "LONG" in active_sides and "SHORT" not in active_sides:
                    print("⚡ Ada posisi LONG → Mencari peluang SHORT saja (reversal/close)")
                    opposite_signal = "SHORT"
                    existing_signal = "LONG"
                elif "SHORT" in active_sides and "LONG" not in active_sides:
                    print("⚡ Ada posisi SHORT → Mencari peluang LONG saja (reversal/close)")
                    opposite_signal = "LONG"
                    existing_signal = "SHORT"
                else:
                    # Kasus Hedging: kedua sisi terbuka
                    print("⚡ Posisi LONG & SHORT aktif (Hedging) → Tidak cari entry baru")
                    continue

            # Fetch Multi-TF
            df_dict = fetcher.fetch_multi_timeframe(symbol)
            df_dict_bb = df_dict.copy()
            if df_dict is None:
                continue

            # Calculate Indicators
            ind_calc_bb = IndicatorCalculatorBB(df_dict_bb)
            df_dict_bb = ind_calc_bb.calculate_all()

            # Decide Method to Use (Trend Following / Reversal)
            detect_regime_bb = DetectRegimeBB(df_dict_bb)
            regime_bb = detect_regime_bb.detect()
            print(f"✅ Regime {regime_bb} used")

            # ⭐ Simpan df_dict ke file TXT untuk inspeksi data (Debug)
            try:
                safe_symbol = symbol.replace('/', '_').replace(':', '_')
                debug_file = f"data/{safe_symbol}_debug.txt"
                with open(debug_file, "w", encoding='utf-8') as f:
                    for tf_key, df in df_dict.items():
                        f.write(f"\n{'='*30} TIMEFRAME: {tf_key} {'='*30}\n")
                        f.write(df.tail(20).to_string(float_format='%.6f')) # Pastikan desimal terlihat 6 angka
                        f.write("\n")
                print(f"📄 Data debug {symbol} disimpan ke {debug_file}")
            except Exception as e:
                print(f"⚠️ Gagal menyimpan file debug untuk {symbol}: {e}")

            # Analyze Confluence - BB
            mtf_bb = MTFConfluenceBB(df_dict_bb, symbol)
            if regime_bb == "TREND_FOLLOWING":
                signal_bb, reasons_bb, score_bb = mtf_bb.analyze()
            elif regime_bb == "REVERSAL":
                signal_bb, reasons_bb, score_bb = mtf_bb.analyze_reversal()
            else:
                print(f"⚠️ Regime {regime_bb} wait n see")
                continue
            
            # 🎯 FILTER: Jika ada posisi aktif, hanya terima sinyal berlawanan
            if active_positions:
                if signal_bb == existing_signal:
                    print(f"⏭️  Skip {signal_bb} BB (sama dengan posisi aktif {existing_signal})")
                    signal_bb = "NO_TRADE"

            # 🎯 FILTER DIRECTIONAL: Cek slot LONG/SHORT sebelum terima sinyal baru
            if signal_bb == "LONG"  and long_count  >= max_long:
                print(f"⛔ Skip LONG — slot LONG penuh ({long_count}/{max_long})")
                signal_bb = "NO_TRADE"
            elif signal_bb == "SHORT" and short_count >= max_short:
                print(f"⛔ Skip SHORT — slot SHORT penuh ({short_count}/{max_short})")
                signal_bb = "NO_TRADE"

            # add logger - bb
            emoji_bb = "🟢" if signal_bb == "LONG" else "🔴" if signal_bb == "SHORT" else "⚪"
            print(f"Result BB : {symbol} - {emoji_bb} {signal_bb} | Score : ({score_bb})")

            # get risk data
            # risk_data = mtf.get_risk_data()
            risk_data_bb = mtf_bb.get_risk_data()

            if signal_bb not in ["NO_TRADE", "NO TRADE", "WATCH"]:
                # risk manager - bb
                rm_bb = RiskManager(
                    atr=risk_data_bb['atr'],
                    price=risk_data_bb['price'],
                    signal=signal_bb,
                    df_base=risk_data_bb.get('df_base')
                )
                risk_levels_bb = rm_bb.calculate_levels()

                # position sizer - bb
                ps_bb = PositionSizer(account_balance, TRADING_CONFIG['leverage'])
                position_info_bb = ps_bb.calculate_position(
                    entry_price=risk_levels_bb['entry'],
                    stop_loss_price=risk_levels_bb['stop_loss'],
                    signal=signal_bb
                )

                # Tambahkan symbol ke position_info
                position_info_bb['symbol'] = symbol
                position_info_bb['method'] = risk_levels_bb['method']

                # ⭐ BUAT FOLDER SINYAL & SIMPAN CHART
                signal_folder = create_signal_folder(
                    pair=symbol.replace('/', '').replace(':', ''),
                    signal_type=signal_bb,
                    base_folder=today_folder
                )

                # Simpan chart dari semua timeframe
                mtf_bb.save_signal_charts(signal_folder)
                
                # ⭐ SIMPAN DETAIL SINYAL KE TXT
                NarrativeBuilder.save_signal_details(
                    signal_folder=signal_folder,
                    symbol=symbol,
                    signal_type=signal_bb,
                    risk_data=risk_levels_bb,
                    position_data=position_info_bb,
                    reasons=reasons_bb,
                    regime=regime_bb,
                    score=score_bb,
                    method=risk_levels_bb.get('method', 'BB')
                )

                # Tambahkan ke tracker (sertakan risk_levels untuk TP1/TP2/TP3)
                tracker.add_position(position_info_bb, risk_levels=risk_levels_bb)

                # ⭐ Notifikasi entry baru ke Telegram
                if notifier:
                    notifier.notify_new_entry(
                        symbol        = symbol,
                        signal        = signal_bb,
                        risk_levels   = risk_levels_bb,
                        position_info = position_info_bb
                    )

                # ⭐ Pasang SL/TP orders ke exchange
                # paper=True: hanya log (tidak kirim ke Bybit)
                # Ubah paper=False saat siap live trading
                from core.exchange import place_sl_tp_orders
                place_sl_tp_orders(
                    symbol        = symbol,
                    signal        = signal_bb,
                    qty           = position_info_bb['quantity'],
                    entry_price   = risk_levels_bb['entry'],
                    stop_loss     = risk_levels_bb['stop_loss'],
                    take_profit_1 = risk_levels_bb['take_profit_1'],
                    take_profit_2 = risk_levels_bb['take_profit_2'],
                    take_profit_3 = risk_levels_bb['take_profit_3'],
                    paper         = True
                )

                # ⭐ Catat entry ke session report
                if session:
                    session.record_new_entry(
                        symbol=symbol,
                        signal=signal_bb,
                        opened_at=datetime.now().isoformat()
                    )

                # Update counter directional agar filter berikutnya akurat
                if signal_bb == "LONG":
                    long_count += 1
                elif signal_bb == "SHORT":
                    short_count += 1
                open_positions_count += 1

                new_signals.append({
                    'symbol': symbol,
                    'signal': signal_bb,
                    'reasons': reasons_bb,
                    'risk': risk_levels_bb,
                    'position': position_info_bb,
                    'chart_folder': signal_folder
                })


            
            time.sleep(1)
    else:
        print("⚠️ Slot posisi penuh. Tidak ada scan sinyal baru.")
    
    # 7. Save Final State
    tracker.save_positions()

    # 8. Print Summary
    summary = tracker.get_summary()
    BotLogger.print_position_summary(summary)
    BotLogger.print_new_signals(new_signals)

    # 9. Print Session Report
    if session:
        session.print_summary()

if __name__ == "__main__":
    notifier = TelegramNotifier()

    # ⭐ SIGTERM handler — untuk hard stop (server reboot, dll)
    _stop_flag = {'value': False}
    def _handle_sigterm(signum, frame):
        print("\n🛑 Bot dihentikan oleh sistem (SIGTERM)")
        _stop_flag['value'] = True
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # State tracking transisi sesi
    session      = SessionReport()
    _was_active  = None   # None = belum tahu state awal (siklus pertama)

    # ⭐ Periodic report tracking (06:00, 12:00, 18:00, 23:00)
    _REPORT_HOURS   = {6, 12, 18, 23}
    _reported_hours : set = set()

    # ⭐ Watchlist auto-update tracking (07:00 WIB, 1x per hari)
    _watchlist_updated_date = None

    _init_balance   = BalanceManager().get_balance()
    _init_watchlist = load_watchlist()
    notifier.notify_bot_started(len(_init_watchlist), _init_balance)

    while not _stop_flag['value']:
        try:
            _now_active = is_active_session()

            # ── Deteksi transisi sesi ─────────────────────────────────────────
            if _was_active is not None and _now_active != _was_active:
                if _now_active:
                    # ── 14:00: Sesi aktif dimulai ────────────────────────────
                    session = SessionReport()
                    notifier.notify_session_started(
                        balance     = BalanceManager().get_balance(),
                        pairs_count = len(load_watchlist())
                    )
                else:
                    # ── 02:00: Sesi aktif berakhir ───────────────────────────
                    session.print_summary()
                    notifier.notify_session_ended(session)
                    # Reset session — aktifitas off-hours tercatat di sesi baru
                    session = SessionReport()

            _was_active = _now_active

            # ── Jalankan sesuai mode ─────────────────────────────────────────
            if _now_active:
                scan_market(session, notifier)
                interval = 100
            else:
                DataFetcher.monitor_positions(session, notifier)
                interval = 150

            # ── Periodic report (setiap 6 jam: 06, 12, 18, 23) ──────────────
            _current_hour = datetime.now().hour
            if _current_hour in _REPORT_HOURS and _current_hour not in _reported_hours:
                _pt      = PositionTracker()
                _open    = [p for p in _pt.positions if p['status'] == 'OPEN']
                _bm      = BalanceManager()
                notifier.notify_periodic_report(_open, _bm.get_balance(), _bm.get_reserve())
                _reported_hours.add(_current_hour)
            elif _current_hour not in _REPORT_HOURS:
                _reported_hours.discard(_current_hour)

            # ── Watchlist auto-update jam 07:00 WIB (off-hours saja) ─────────
            _today = datetime.now().date()
            if (not _now_active
                    and _current_hour == 8
                    and _watchlist_updated_date != _today):
                _wl_exch = ExchangeManager().connect()
                if _wl_exch:
                    _tracker    = PositionTracker()
                    _open_pairs = {p['symbol'] for p in _tracker.positions if p['status'] == 'OPEN'}
                    DataFetcher(_wl_exch).auto_update_watchlist(notifier, _open_pairs)
                _watchlist_updated_date = _today

            print(f"\n⏳ Menunggu {interval} detik...")
            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n🛑 Bot dihentikan oleh user")
            session.print_summary()
            notifier.notify_bot_stopped(session)
            break
        except SystemExit:
            break
        except Exception as e:
            print(f"❌ Error di main loop: {e}")
            time.sleep(90)

    # Final cleanup saat SIGTERM
    if _stop_flag['value']:
        session.print_summary()
        notifier.notify_bot_stopped(session)