# utils/logger.py

class BotLogger:
    @staticmethod
    def print_position_summary(summary):
        """Print ringkasan semua posisi aktif"""
        print("\n" + "="*70)
        print("📊 POSISI AKTIF")
        print("="*70)
        
        if summary['total_positions'] == 0:
            print("💤 Tidak ada posisi aktif")
        else:
            print(f"Total Posisi: {summary['total_positions']}")
            print(f"Total Margin Used: ${summary['total_margin_used']:.6f}")
            print(f"Total Unrealized PnL: ${summary['total_unrealized_pnl']:.6f}")
            print("-"*70)
            
            for pos in summary['positions']:
                emoji = "🟢" if pos['signal'] == 'LONG' else "🔴"
                pnl_emoji = "📈" if pos['unrealized_pnl'] >= 0 else "📉"
                
                print(f"\n{emoji} {pos['symbol']} ({pos['signal']})")
                print(f"  Entry: ${pos['entry_price']:.6f} | Current Price: ${pos['current_price']:.6f}")
                print(f"  SL: ${pos['stop_loss']:.6f} | TP: ${pos['take_profit']:.6f}")
                print(f"  Qty: {pos['quantity']} | Margin: ${pos['margin_required']:.6f}")
                print(f"  {pnl_emoji} Unrealized PnL: ${pos['unrealized_pnl']:.6f} ({pos['unrealized_pnl_pct']:.2f}%)")
                print(f"  Opened: {pos['opened_at']}")
        
        print("="*70)
    
    @staticmethod
    def log_closed_positions(closed_positions):
        """Log posisi yang baru saja ditutup"""
        for pos in closed_positions:
            emoji = "🎯" if pos['exit_reason'] == 'TP_HIT' else "🛑"
            pnl_emoji = "📈" if pos['pnl_usdt'] >= 0 else "📉"
            
            print(f"\n{emoji} POSISI DITUTUP: {pos['symbol']}")
            print(f"  Signal: {pos['signal']}")
            print(f"  Entry: ${pos['entry_price']:.6f} → Exit: ${pos['exit_price']:.6f}")
            print(f"  Reason: {pos['exit_reason']}")
            print(f"  {pnl_emoji} PnL: ${pos['pnl_usdt']:.6f} ({pos['pnl_pct']:.2f}%)")
            print(f"  Duration: {pos['opened_at']} → {pos['closed_at']}")
    
    @staticmethod
    def print_new_signals(new_signals):
        """Print sinyal baru yang ditemukan"""
        print("\n" + "="*70)
        print("🆕 SINYAL BARU DITEMUKAN")
        print("="*70)
        
        if not new_signals:
            print("💤 Tidak ada sinyal baru kali ini")
        else:
            for r in new_signals:
                print(f"\n{r['symbol']} ({r['signal']})")
                print(f"  Entry: ${r['risk']['entry']:.6f}")
                print(f"  SL: ${r['risk']['stop_loss']:.6f} ({r['risk']['sl_pct_from_entry']})")
                print(f"  TP: ${r['risk']['take_profit']:.6f} ({r['risk']['tp_pct_from_entry']})")
                print(f"  Qty: {r['position']['quantity']}")
                print(f"  Margin: ${r['position']['margin_required']:.6f}")
                print(f"  Method: {r['risk']['method']}")
                
                print(f"  Alasan:")
                for i, reason in enumerate(r['reasons'], 1):
                    print(f"    {i}. {reason}")
        
        print("="*70)
    
    # ... (fungsi print_summary lama bisa dipertahankan untuk debug)