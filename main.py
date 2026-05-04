# main.py
import time
from core.exchange import ExchangeManager
from core.data_fetcher import DataFetcher

from risk.manager import RiskManager
from risk.position_sizer import PositionSizer
from risk.position_tracker import PositionTracker
from risk.balance_manager import BalanceManager  # ⭐ Balance dinamis
from utils.logger import BotLogger
from utils.file_manager import get_today_folder, create_signal_folder  # ⭐ IMPORT BARU

from strategy.mtf_confluence import MTFConfluence
from strategy.mtf_confluence_bb import MTFConfluenceBB

from indicators.technical import IndicatorCalculator
from indicators.technical_bb import IndicatorCalculatorBB

from config import WATCHLIST, TRADING_CONFIG
from datetime import datetime
import os


def save_signal_details(signal_folder: str, symbol: str, signal_type: str, risk_data: dict, position_data: dict, reasons: list, method: str = "Unknown"):
    """
    Simpan detail sinyal ke file TXT dalam folder sinyal.
    
    Args:
        signal_folder: Path folder sinyal
        symbol: Nama pair/symbol
        signal_type: Jenis sinyal (LONG/SHORT)
        risk_data: Data risk (entry, stop_loss, take_profit, dll)
        position_data: Data position (size, leverage, dll)
        reasons: List alasan sinyal
        method: Metode yang digunakan (BB/EMA)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Helper untuk format price
    def fmt_price(val):
        if val is None:
            return "N/A"
        try:
            return f"${float(val):,.6f}"
        except:
            return str(val)
    
    def fmt_val(val):
        return val if val is not None else "N/A"
    
    base_coin = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
    
    content = f"""================================================================================
                        📊 SIGNAL DETAILS
================================================================================

📌 Symbol        : {symbol}
📌 Signal Type   : {signal_type}
📌 Method        : {method}
📌 Generated At  : {timestamp}

--------------------------------------------------------------------------------
                        💰 ENTRY & RISK LEVELS
--------------------------------------------------------------------------------

🎯 Entry Price   : {fmt_price(risk_data.get('entry'))}
🛑 Stop Loss     : {fmt_price(risk_data.get('stop_loss'))}
🎯 Take Profit 1 : {fmt_price(risk_data.get('take_profit_1'))}
🎯 Take Profit 2 : {fmt_price(risk_data.get('take_profit_2'))}
🎯 Take Profit 3 : {fmt_price(risk_data.get('take_profit_3'))}

📊 Risk/Reward   : {fmt_val(risk_data.get('risk_reward_ratio'))}

--------------------------------------------------------------------------------
                        📈 POSITION DETAILS
--------------------------------------------------------------------------------

💵 Position Size : {fmt_val(position_data.get('position_size_usd'))} USDT
📊 Amount        : {fmt_val(position_data.get('amount'))} {base_coin}
🔧 Leverage     : {fmt_val(position_data.get('leverage'))}x
📐 Qty           : {fmt_val(position_data.get('qty'))}

--------------------------------------------------------------------------------
                        🧠 SIGNAL REASONS
--------------------------------------------------------------------------------

"""
    
    for i, reason in enumerate(reasons, 1):
        content += f"{i}. {reason}\n"
    
    content += f"""
--------------------------------------------------------------------------------
                        ⚠️ DISCLAIMER
--------------------------------------------------------------------------------

This signal is generated automatically by the trading bot.
Always do your own research before making any trading decisions.
Past performance does not guarantee future results.

================================================================================
"""
    
    # Clean symbol for filename
    safe_symbol = symbol.replace('/', '_').replace(':', '_')
    filename = os.path.join(signal_folder, f"{safe_symbol}_signal_details.txt")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"📄 Signal details saved: {filename}")
    return filename


def scan_market():
    print("\n" + "="*70)
    print("🚀 Memulai Multi-Coin MTF Scanner...")
    print("="*70)

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
    closed_positions = tracker.check_tp_sl(current_prices)

    # Log closed positions
    if closed_positions:
        BotLogger.log_closed_positions(closed_positions)
        # ⭐ Update balance dari PnL posisi yang di-close
        balance_mgr.update_from_closed_positions(closed_positions)
        # Refresh balance untuk scan berikutnya
        account_balance = balance_mgr.get_balance()
    
    # 6. ⭐ PRIORITAS 2: Cek Sinyal Baru (Hanya Jika Ada Slot)
    print("\n" + "="*70)
    print("🔍 CEK SINYAL BARU")
    print("="*70)
    
    summary = tracker.get_summary()
    open_positions_count = summary['total_positions']
    max_positions = TRADING_CONFIG['max_open_positions']
    
    print(f"Posisi Terbuka: {open_positions_count}/{max_positions}")
    
    new_signals = []

    # Hanya cari sinyal baru jika masih ada slot
    if open_positions_count < max_positions:
        fetcher = DataFetcher(exchange)

        for symbol in WATCHLIST:
            print(f"\n🔍 Scanning {symbol}...")

            # Cek apakah ada posisi aktif untuk koin ini
            active_positions = tracker.get_active_positions(symbol)
            existing_signal = None

            # 2. Tentukan arah sinyal yang boleh dicari
            if not active_positions:
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
            ind_calc = IndicatorCalculator(df_dict)
            df_dict = ind_calc.calculate_all()

            ind_calc_bb = IndicatorCalculatorBB(df_dict_bb)
            df_dict_bb = ind_calc_bb.calculate_all()

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

            # Analyze Confluence
            mtf = MTFConfluence(df_dict, symbol)
            signal, reasons, score = mtf.analyze()

            # Analyze Confluence - BB
            mtf_bb = MTFConfluenceBB(df_dict_bb, symbol)
            signal_bb, reasons_bb, score_bb = mtf_bb.analyze()

            # 🎯 FILTER: Jika ada posisi aktif, hanya terima sinyal berlawanan
            if active_positions:
                if signal == existing_signal:
                    print(f"⏭️  Skip {signal} (sama dengan posisi aktif {existing_signal})")
                    signal = "NO_TRADE"
                if signal_bb == existing_signal:
                    print(f"⏭️  Skip {signal_bb} BB (sama dengan posisi aktif {existing_signal})")
                    signal_bb = "NO_TRADE"

            # add logger
            emoji = "🟢" if signal == "LONG" else "🔴" if signal == "SHORT" else "⚪"
            print(f"Result : {symbol} - {emoji} {signal} | Score : ({score})")

            # add logger - bb
            emoji_bb = "🟢" if signal_bb == "LONG" else "🔴" if signal_bb == "SHORT" else "⚪"
            print(f"Result BB : {symbol} - {emoji_bb} {signal_bb} | Score : ({score_bb})")

            # get risk data
            # risk_data = mtf.get_risk_data()
            risk_data_bb = mtf_bb.get_risk_data()

            # Calculate Risk Levels
            risk_levels = None
            position_info = None

            if signal not in ["NO_TRADE", "NO TRADE"]:
                # risk manager
                rm = RiskManager(
                    atr=risk_data['atr'],
                    price=risk_data['price'],
                    signal=signal,
                    df_base=risk_data.get('df_base')
                )
                risk_levels = rm.calculate_levels()

                # position sizer
                ps = PositionSizer(account_balance, TRADING_CONFIG['leverage'])
                position_info = ps.calculate_position(
                    entry_price=risk_levels['entry'],
                    stop_loss_price=risk_levels['stop_loss'],
                    signal=signal
                )

                # Tambahkan symbol ke position_info
                position_info['symbol'] = symbol
                position_info['method'] = risk_levels['method']

                # ⭐ BUAT FOLDER SINYAL & SIMPAN CHART
                signal_folder = create_signal_folder(
                    pair=symbol.replace('/', '').replace(':', ''),
                    signal_type=signal,
                    base_folder=today_folder
                )

                # Simpan chart dari semua timeframe
                mtf.save_signal_charts(signal_folder)
                
                # ⭐ SIMPAN DETAIL SINYAL KE TXT
                save_signal_details(
                    signal_folder=signal_folder,
                    symbol=symbol,
                    signal_type=signal,
                    risk_data=risk_levels,
                    position_data=position_info,
                    reasons=reasons,
                    method=risk_levels.get('method', 'EMA')
                )

                # Tambahkan ke tracker
                tracker.add_position(position_info)
                new_signals.append({
                    'symbol': symbol,
                    'signal': signal,
                    'reasons': reasons,
                    'risk': risk_levels,
                    'position': position_info,
                    'chart_folder': signal_folder  # ⭐ TAMBAHKAN INFO FOLDER
                })

            if signal_bb not in ["NO_TRADE", "NO TRADE"]:
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
                save_signal_details(
                    signal_folder=signal_folder,
                    symbol=symbol,
                    signal_type=signal_bb,
                    risk_data=risk_levels_bb,
                    position_data=position_info_bb,
                    reasons=reasons_bb,
                    method=risk_levels_bb.get('method', 'BB')
                )

                # Tambahkan ke tracker
                tracker.add_position(position_info_bb)
                new_signals.append({
                    'symbol': symbol,
                    'signal': signal_bb,
                    'reasons': reasons_bb,
                    'risk': risk_levels_bb,
                    'position': position_info_bb,
                    'chart_folder': signal_folder  # ⭐ TAMBAHKAN INFO FOLDER
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

if __name__ == "__main__":
    while True:
        try:
            scan_market()
            print("\n⏳ Menunggu 100 detik sebelum scan berikutnya...")
            time.sleep(100)
        except KeyboardInterrupt:
            print("\n🛑 Bot dihentikan oleh user")
            break
        except Exception as e:
            print(f"❌ Error di main loop: {e}")
            time.sleep(90)