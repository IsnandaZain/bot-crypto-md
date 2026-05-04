# risk/position_tracker.py
import json
import os
from datetime import datetime
from config import TRADING_CONFIG

class PositionTracker:
    def __init__(self, data_folder='data'):
        self.data_folder = data_folder
        self.positions_file = os.path.join(data_folder, 'active_positions.json')
        self.positions = []
        self.history = []
        
        # Pastikan folder ada
        if not os.path.exists(data_folder):
            os.makedirs(data_folder)
        
        # Load data saat init
        self.load_positions()
    
    def load_positions(self):
        """Load posisi aktif dari JSON file (untuk bot restart)"""
        if os.path.exists(self.positions_file):
            try:
                with open(self.positions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.positions = data.get('positions', [])
                    self.history = data.get('history', [])
                print(f"📂 Loaded {len(self.positions)} posisi aktif dari file")
            except Exception as e:
                print(f"⚠️ Gagal load posisi: {e}")
                self.positions = []
                self.history = []
        else:
            print("📂 Tidak ada file posisi sebelumnya (start fresh)")
            self.positions = []
            self.history = []
    
    def save_positions(self):
        """Simpan posisi aktif ke JSON file"""
        data = {
            'positions': self.positions,
            'history': self.history[-50:],  # Simpan 50 history terakhir saja
            'last_updated': datetime.now().isoformat()
        }
        
        try:
            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Gagal save posisi: {e}")
    
    def is_position_active(self, symbol):
        """Cek apakah simbol sudah punya posisi aktif"""
        for pos in self.positions:
            if pos['symbol'] == symbol and pos['status'] == 'OPEN':
                return True
        return False
    
    def get_active_positions(self, symbol):
        """Kembalikan {'LONG': pos_data, 'SHORT': pos_data} untuk simbol tertentu"""
        result = {"LONG": None, "SHORT": None}
        for pos in self.positions:
            if pos['symbol'] == symbol and pos['status'] == 'OPEN':
                side = str(pos.get('signal', '')).upper()
                if side in result:
                    result[side] = pos
        # Hapus key yang nilainya None agar bersih
        return {k: v for k, v in result.items() if v is not None}
    
    def add_position(self, position_info):
        """Tambah posisi baru ke list"""
        new_position = {
            'symbol': position_info['symbol'],
            'signal': position_info['signal'],
            'entry_price': position_info['entry_price'],
            'current_price': position_info['entry_price'],
            'stop_loss': position_info['stop_loss'],
            'take_profit': position_info['take_profit'],
            'quantity': position_info['quantity'],
            'leverage': position_info['leverage'],
            'margin_required': position_info['margin_required'],
            'opened_at': datetime.now().isoformat(),
            'status': 'OPEN',
            'method': position_info.get('method', 'Unknown'),
            'unrealized_pnl': 0,
            'unrealized_pnl_pct': 0
        }
        
        self.positions.append(new_position)
        self.save_positions()
        print(f"✅ Posisi baru ditambahkan: {new_position['symbol']} {new_position['signal']}")
    
    def check_tp_sl(self, current_prices):
        """
        Cek semua posisi aktif apakah kena TP atau SL
        
        Args:
            current_prices: dict {symbol: current_price}
        
        Returns:
            list of closed positions
        """
        closed_positions = []
        
        for pos in self.positions[:]:  # Copy list untuk aman saat remove
            if pos['status'] != 'OPEN':
                continue
            
            symbol = pos['symbol']
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]
            exit_price = None
            exit_reason = None

            # jika sudah diatas 105% auto TP saja
            # print((pos['current_price'] - pos['entry_price']) / pos['entry_price'] * 100 * pos['leverage'])
            if (pos['current_price'] - pos['entry_price']) / pos['entry_price'] * 100 * pos['leverage'] > 150:
                exit_price = pos['current_price']
                exit_reason = 'AUTO_TP_HIT'

            else:
                # Cek SL
                if pos['signal'] == 'LONG':
                    if current_price <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL_HIT'
                    elif current_price >= pos['take_profit']:
                        exit_price = pos['take_profit']
                        exit_reason = 'TP_HIT'
                else:  # SHORT
                    if current_price >= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL_HIT'
                    elif current_price <= pos['take_profit']:
                        exit_price = pos['take_profit']
                        exit_reason = 'TP_HIT'
            
            # Jika exit, hitung PnL dan tutup posisi
            if exit_price:
                pnl = self._calculate_pnl(pos, exit_price)
                
                closed_pos = {
                    'symbol': pos['symbol'],
                    'signal': pos['signal'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'quantity': pos['quantity'],
                    'pnl_usdt': pnl,
                    'pnl_pct': (pnl / pos['margin_required'] * 100) if pos['margin_required'] > 0 else 0,
                    'opened_at': pos['opened_at'],
                    'closed_at': datetime.now().isoformat(),
                    'exit_reason': exit_reason,
                    'method': pos['method']
                }
                
                closed_positions.append(closed_pos)
                self.history.append(closed_pos)
                self.positions.remove(pos)
                
                emoji = "🎯" if exit_reason == 'TP_HIT' else "🛑"
                print(f"{emoji} Posisi ditutup: {pos['symbol']} - {exit_reason} - PnL: ${pnl:.6f}")
        
        # Save setelah update
        if closed_positions:
            self.save_positions()
        
        return closed_positions
    
    def _calculate_pnl(self, position, exit_price):
        """Hitung PnL (Profit and Loss) dalam USDT"""
        qty = position['quantity']
        entry = position['entry_price']
        exit_p = exit_price
        
        if position['signal'] == 'LONG':
            pnl = (exit_p - entry) * qty
        else:  # SHORT
            pnl = (entry - exit_p) * qty
        
        # Kurangi fee estimasi (0.06% taker fee × 2 untuk entry+exit)
        fee = position['margin_required'] * 0.0012
        pnl -= fee
        
        return pnl
    
    def update_unrealized_pnl(self, current_prices):
        """Update unrealized PnL untuk semua posisi aktif"""
        for pos in self.positions:
            if pos['status'] != 'OPEN':
                continue
            
            symbol = pos['symbol']
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]

            # update current price
            pos['current_price'] = current_price

            # update unrealized_pnl
            pos['unrealized_pnl'] = self._calculate_pnl(pos, current_price)
            
            if pos['margin_required'] > 0:
                pos['unrealized_pnl_pct'] = (pos['unrealized_pnl'] / pos['margin_required'] * 100)
            else:
                pos['unrealized_pnl_pct'] = 0
    
    def get_summary(self):
        """Ringkasan semua posisi aktif"""
        total_margin = sum(p['margin_required'] for p in self.positions if p['status'] == 'OPEN')
        total_unrealized_pnl = sum(p['unrealized_pnl'] for p in self.positions if p['status'] == 'OPEN')
        
        return {
            'total_positions': len([p for p in self.positions if p['status'] == 'OPEN']),
            'total_margin_used': total_margin,
            'total_unrealized_pnl': total_unrealized_pnl,
            'positions': self.positions
        }
    
    def get_all_history(self):
        """Ambil semua history trading"""
        return self.history