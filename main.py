# main.py
import time
from core.exchange import ExchangeManager
from core.data_fetcher import DataFetcher
from indicators.technical import IndicatorCalculator
from strategy.mtf_confluence import MTFConfluence
from risk.manager import RiskManager
from risk.position_sizer import PositionSizer
from risk.position_tracker import PositionTracker  # ⭐ IMPORT BARU
from utils.logger import BotLogger
from config import WATCHLIST, TRADING_CONFIG

def scan_market():
    print("\n" + "="*70)
    print("🚀 Memulai Multi-Coin MTF Scanner...")
    print("="*70)
    
    # 1. Connect Exchange
    exchange_mgr = ExchangeManager()
    exchange = exchange_mgr.connect()
    if not exchange:
        return
    
    # 2. Initialize Position Tracker (Load dari JSON)
    tracker = PositionTracker()
    
    # 3. Get Account Balance
    if TRADING_CONFIG['auto_fetch_balance']:
        try:
            balance_info = exchange.fetch_balance()
            account_balance = balance_info['total']['USDT']
            print(f"💰 Balance dari API: ${account_balance:.2f}")
        except:
            account_balance = TRADING_CONFIG['account_balance_usdt']
            print(f"⚠️ Gagal fetch balance, pakai manual: ${account_balance:.2f}")
    else:
        account_balance = TRADING_CONFIG['account_balance_usdt']
        print(f"💰 Balance Manual: ${account_balance:.2f}")
    
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
            # SKIP jika sudah ada posisi aktif untuk koin ini
            if tracker.is_position_active(symbol):
                print(f"⏭️  Skip {symbol} (sudah ada posisi aktif)")
                continue
            
            print(f"\n🔍 Scanning {symbol}...")
            
            # Fetch Multi-TF
            df_dict = fetcher.fetch_multi_timeframe(symbol)
            if df_dict is None:
                continue
            
            # Calculate Indicators
            ind_calc = IndicatorCalculator(df_dict)
            df_dict = ind_calc.calculate_all()
            
            # Analyze Confluence
            mtf = MTFConfluence(df_dict)
            signal, reasons, score = mtf.analyze()

            # add logger
            emoji = "🟢" if signal == "LONG" else "🔴" if signal == "SHORT" else "⚪"
            print(f"Result : {symbol} - {emoji} {signal} | Score : ({score})")

            risk_data = mtf.get_risk_data()
            
            # Calculate Risk Levels
            risk_levels = None
            position_info = None
            
            if signal != "NO TRADE":
                rm = RiskManager(
                    atr=risk_data['atr'],
                    price=risk_data['price'],
                    signal=signal,
                    df_base=risk_data.get('df_base')
                )
                risk_levels = rm.calculate_levels()
                
                ps = PositionSizer(account_balance, TRADING_CONFIG['leverage'])
                position_info = ps.calculate_position(
                    entry_price=risk_levels['entry'],
                    stop_loss_price=risk_levels['stop_loss'],
                    signal=signal
                )
                
                # Tambahkan symbol ke position_info
                position_info['symbol'] = symbol
                position_info['method'] = risk_levels['method']
                
                # Tambahkan ke tracker
                tracker.add_position(position_info)
                new_signals.append({
                    'symbol': symbol,
                    'signal': signal,
                    'reasons': reasons,
                    'risk': risk_levels,
                    'position': position_info
                })
            
            time.sleep(0.5)
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
            print("\n⏳ Menunggu 120 detik sebelum scan berikutnya...")
            time.sleep(120)
        except KeyboardInterrupt:
            print("\n🛑 Bot dihentikan oleh user")
            break
        except Exception as e:
            print(f"❌ Error di main loop: {e}")
            time.sleep(10)