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
    
    def add_position(self, position_info, risk_levels=None):
        """Tambah posisi baru ke list"""
        new_position = {
            'symbol': position_info['symbol'],
            'signal': position_info['signal'],
            'entry_price': position_info['entry_price'],
            'current_price': position_info['entry_price'],
            'stop_loss': position_info['stop_loss'],
            'take_profit': position_info['take_profit'],
            # TP multi-level untuk Partial TP. Fallback ke take_profit jika tidak ada.
            'take_profit_1': risk_levels['take_profit_1'] if risk_levels else position_info['take_profit'],
            'take_profit_2': risk_levels['take_profit_2'] if risk_levels else position_info['take_profit'],
            'take_profit_3': risk_levels['take_profit_3'] if risk_levels else position_info['take_profit'],
            'tp_stage': 0,  # 0=belum hit TP apapun, 1=TP1 hit, 2=TP2 hit
            'quantity': position_info['quantity'],
            'leverage': position_info['leverage'],
            'margin_required': position_info['margin_required'],
            'opened_at': datetime.now().isoformat(),
            'status': 'OPEN',
            'method': position_info.get('method', 'Unknown'),
            'unrealized_pnl': 0,
            'unrealized_pnl_pct': 0,
            'breakeven_triggered': False
        }
        
        self.positions.append(new_position)
        self.save_positions()
        print(f"✅ Posisi baru ditambahkan: {new_position['symbol']} {new_position['signal']}")
    
    def update_partial_tp(self, current_prices):
        """
        Monitor TP1 dan TP2, eksekusi partial close dan geser SL.

        tp_stage 0 → 1 (TP1 hit):
            - Tutup 50% posisi (tp1_partial_close_pct)
            - Geser SL ke entry + 10% margin profit (= 0.5% harga di leverage 20x)
            - Catat partial close di history

        tp_stage 1 → 2 (TP2 hit):
            - Flag untuk tutup semua sisa di check_tp_sl()

        Penutupan posisi penuh ditangani oleh check_tp_sl().
        """
        from config import RISK_CONFIG

        if not RISK_CONFIG.get('partial_tp_enabled', True):
            return []

        partial_close_pct    = RISK_CONFIG.get('tp1_partial_close_pct', 0.50)
        sl_profit_margin_pct = RISK_CONFIG.get('tp1_sl_profit_margin_pct', 0.15)
        updated              = []

        for pos in self.positions:
            if pos['status'] != 'OPEN':
                continue
            if pos['symbol'] not in current_prices:
                continue

            current_price = current_prices[pos['symbol']]
            signal        = pos['signal']
            entry         = pos['entry_price']
            tp_stage      = pos.get('tp_stage', 0)

            tp1 = pos.get('take_profit_1', pos['take_profit'])
            tp2 = pos.get('take_profit_2', pos['take_profit'])

            # ── STAGE 0 → 1: TP1 tercapai ─────────────────────────────────
            if tp_stage == 0:
                tp1_hit = (signal == 'LONG'  and current_price >= tp1) or \
                          (signal == 'SHORT' and current_price <= tp1)

                if tp1_hit:
                    # Hitung qty partial close (50%)
                    qty_close    = pos['quantity'] * partial_close_pct
                    qty_remain   = pos['quantity'] - qty_close
                    margin_close = pos['margin_required'] * partial_close_pct

                    # Hitung PnL partial
                    pnl_partial  = self._calculate_pnl_partial(pos, tp1, qty_close)

                    # Catat partial close di history
                    partial_record = {
                        'symbol'       : pos['symbol'],
                        'signal'       : signal,
                        'entry_price'  : entry,
                        'exit_price'   : tp1,
                        'quantity'     : qty_close,
                        'qty_remain'   : qty_remain,
                        'pnl_usdt'     : pnl_partial,
                        'pnl_pct'      : (pnl_partial / margin_close * 100) if margin_close > 0 else 0,
                        'opened_at'    : pos['opened_at'],
                        'closed_at'    : datetime.now().isoformat(),
                        'exit_reason'  : 'TP1_PARTIAL_50PCT',
                        'tp_stage_at_close': 1,
                        'method'       : pos['method'],
                        'is_partial'   : True,
                        'new_sl'       : None   # di-set setelah SL baru dihitung
                    }
                    self.history.append(partial_record)

                    # Update posisi — kurangi qty dan margin
                    pos['quantity']        = qty_remain
                    pos['margin_required'] = pos['margin_required'] * (1 - partial_close_pct)
                    pos['tp_stage']        = 1
                    pos['breakeven_triggered'] = True

                    # Geser SL ke entry + 10% margin profit (= 0.5% harga di leverage 20x)
                    leverage       = pos.get('leverage', 20)
                    sl_price_shift = entry * (sl_profit_margin_pct / leverage)
                    new_sl         = entry + sl_price_shift if signal == 'LONG' else entry - sl_price_shift
                    old_sl         = pos['stop_loss']

                    sl_valid = (signal == 'LONG'  and new_sl > old_sl) or \
                               (signal == 'SHORT' and new_sl < old_sl)
                    if sl_valid:
                        pos['stop_loss'] = new_sl
                        partial_record['new_sl'] = new_sl

                    # Stub eksekusi real order (aktifkan saat live trading)
                    self._execute_partial_close_order(pos['symbol'], signal, qty_close, tp1, paper=True)

                    updated.append(pos['symbol'])
                    print(
                        f"🎯 TP1 PARTIAL: {pos['symbol']} {signal} @ {current_price:.6f} "
                        f"| Tutup {partial_close_pct*100:.0f}% (qty={qty_close:.6f}) "
                        f"| PnL: ${pnl_partial:.4f} "
                        f"| SL {old_sl:.6f} → {new_sl:.6f} (+{sl_profit_margin_pct*100:.0f}% margin)"
                    )

            # ── STAGE 1 → 2: TP2 tercapai → partial close 50% sisa + SL ke TP1 ──
            elif tp_stage == 1:
                tp2_hit = (signal == 'LONG'  and current_price >= tp2) or \
                          (signal == 'SHORT' and current_price <= tp2)

                if tp2_hit:
                    # Tutup 50% dari sisa qty (sisa sudah 50% sejak TP1)
                    qty_close    = pos['quantity'] * 0.50
                    qty_remain   = pos['quantity'] - qty_close
                    margin_close = pos['margin_required'] * 0.50

                    # Hitung PnL partial TP2
                    pnl_partial = self._calculate_pnl_partial(pos, tp2, qty_close)

                    # Catat partial close di history
                    partial_record = {
                        'symbol'           : pos['symbol'],
                        'signal'           : signal,
                        'entry_price'      : entry,
                        'exit_price'       : tp2,
                        'quantity'         : qty_close,
                        'qty_remain'       : qty_remain,
                        'pnl_usdt'         : pnl_partial,
                        'pnl_pct'          : (pnl_partial / margin_close * 100) if margin_close > 0 else 0,
                        'opened_at'        : pos['opened_at'],
                        'closed_at'        : datetime.now().isoformat(),
                        'exit_reason'      : 'TP2_PARTIAL_50PCT',
                        'tp_stage_at_close': 2,
                        'method'           : pos['method'],
                        'is_partial'       : True,
                        'new_sl'           : None   # di-set setelah SL baru dihitung
                    }
                    self.history.append(partial_record)

                    # Update posisi — kurangi qty dan margin
                    pos['quantity']        = qty_remain
                    pos['margin_required'] = pos['margin_required'] * 0.50
                    pos['tp_stage']        = 2

                    # Geser SL ke midpoint antara TP1 dan TP2 (lebih konservatif dari TP1)
                    tp1_price   = pos.get('take_profit_1', pos['take_profit'])
                    midpoint_sl = (tp1_price + tp2) / 2
                    old_sl      = pos['stop_loss']
                    sl_valid    = (signal == 'LONG'  and midpoint_sl > old_sl) or \
                                  (signal == 'SHORT' and midpoint_sl < old_sl)
                    if sl_valid:
                        pos['stop_loss'] = midpoint_sl
                        partial_record['new_sl'] = midpoint_sl

                    # Simpan referensi trailing: harga TP2 sebagai titik awal trailing
                    pos['trailing_sl_ref'] = tp2

                    self._execute_partial_close_order(pos['symbol'], signal, qty_close, tp2, paper=True)

                    updated.append(pos['symbol'])
                    print(
                        f"🎯 TP2 PARTIAL: {pos['symbol']} {signal} @ {current_price:.6f} "
                        f"| Tutup 50% sisa (qty={qty_close:.6f}) "
                        f"| PnL: ${pnl_partial:.4f} "
                        f"| SL {old_sl:.6f} → {midpoint_sl:.6f} (midpoint TP1-TP2) "
                        f"| Trailing ref: {tp2:.6f} (TP2)"
                    )

        if updated:
            self.save_positions()

        return updated

    def _calculate_pnl_partial(self, position, exit_price, qty):
        """Hitung PnL untuk sebagian qty yang ditutup"""
        entry = position['entry_price']
        if position['signal'] == 'LONG':
            pnl = (exit_price - entry) * qty
        else:
            pnl = (entry - exit_price) * qty
        # Fee proporsional terhadap qty yang ditutup
        fee = (position['margin_required'] * (qty / position['quantity'])) * 0.0012
        return pnl - fee

    def _execute_partial_close_order(self, symbol: str, signal: str, qty: float, price: float, paper: bool = True):
        """
        Stub untuk eksekusi partial close order ke exchange.

        Args:
            symbol : trading pair (misal 'BTC/USDT:USDT')
            signal : 'LONG' atau 'SHORT'
            qty    : jumlah kontrak yang ditutup
            price  : harga target (TP1)
            paper  : True = paper trading (tidak kirim order), False = live

        TODO (live trading):
            exchange = ExchangeManager().connect()
            side = 'sell' if signal == 'LONG' else 'buy'
            exchange.create_order(symbol, 'market', side, qty, params={'reduceOnly': True})
        """
        if paper:
            print(f"   📝 [PAPER] Partial close order: {symbol} {signal} qty={qty:.6f} @ {price:.6f}")
        else:
            # Aktifkan blok ini saat live trading
            # from core.exchange import ExchangeManager
            # exchange = ExchangeManager().connect()
            # side = 'sell' if signal == 'LONG' else 'buy'
            # exchange.create_order(symbol, 'market', side, qty, params={'reduceOnly': True})
            pass

    def update_breakeven_sl(self, current_prices):
        """
        1. Breakeven: geser SL ke entry+buffer saat profit cukup (sekali saja).
        2. Trailing SL: aktif setelah TP2 hit (tp_stage==2) — setiap harga naik
           1% dari trailing_sl_ref, SL naik 0.5% dari trailing_sl_ref.
           Trailing ref awal = harga TP2 saat TP2 di-hit.

        Dipanggil setiap scan cycle sebelum check_tp_sl().
        """
        from config import RISK_CONFIG

        trigger_pct = RISK_CONFIG.get('breakeven_profit_trigger_pct', 30)
        fee_buffer  = RISK_CONFIG.get('breakeven_fee_buffer', 0.0012)

        updated = []

        for pos in self.positions:
            if pos['status'] != 'OPEN':
                continue
            if pos['symbol'] not in current_prices:
                continue

            current_price = current_prices[pos['symbol']]
            signal        = pos['signal']

            # ── 1. Breakeven (hanya untuk posisi yang belum pernah di-trigger) ──
            if not pos.get('breakeven_triggered', False):
                if pos['unrealized_pnl_pct'] >= trigger_pct:
                    entry      = pos['entry_price']
                    fee_amount = entry * fee_buffer

                    if signal == 'LONG':
                        new_sl = entry + fee_amount
                        if new_sl <= pos['stop_loss']:
                            pass
                        else:
                            old_sl = pos['stop_loss']
                            pos['stop_loss']           = new_sl
                            pos['breakeven_triggered'] = True
                            updated.append(pos['symbol'])
                            print(
                                f"🔒 BREAKEVEN SL: {pos['symbol']} {signal} "
                                f"| Profit {pos['unrealized_pnl_pct']:.1f}% ≥ {trigger_pct}% "
                                f"| SL {old_sl:.6f} → {new_sl:.6f} (entry+fee)"
                            )
                    else:  # SHORT
                        new_sl = entry - fee_amount
                        if new_sl >= pos['stop_loss']:
                            pass
                        else:
                            old_sl = pos['stop_loss']
                            pos['stop_loss']           = new_sl
                            pos['breakeven_triggered'] = True
                            updated.append(pos['symbol'])
                            print(
                                f"🔒 BREAKEVEN SL: {pos['symbol']} {signal} "
                                f"| Profit {pos['unrealized_pnl_pct']:.1f}% ≥ {trigger_pct}% "
                                f"| SL {old_sl:.6f} → {new_sl:.6f} (entry-fee)"
                            )

            # ── 2. Trailing SL (aktif setelah TP2 hit, tp_stage == 2) ──────────
            if pos.get('tp_stage', 0) == 2 and pos.get('trailing_sl_ref') is not None:
                trailing_ref = pos['trailing_sl_ref']

                if signal == 'LONG':
                    trigger_price = trailing_ref * 1.01          # +1% dari ref
                    if current_price >= trigger_price:
                        sl_delta = trailing_ref * 0.005          # +0.5% dari ref
                        new_sl   = pos['stop_loss'] + sl_delta
                        if new_sl > pos['stop_loss']:            # SL hanya boleh naik
                            old_sl = pos['stop_loss']
                            pos['stop_loss']       = round(new_sl, 8)
                            pos['trailing_sl_ref'] = trailing_ref * 1.01  # geser ref
                            if pos['symbol'] not in updated:
                                updated.append(pos['symbol'])
                            print(
                                f"🔀 TRAILING SL: {pos['symbol']} LONG "
                                f"| Ref {trailing_ref:.6f} → {pos['trailing_sl_ref']:.6f} "
                                f"| SL {old_sl:.6f} → {new_sl:.6f} (+{sl_delta:.6f})"
                            )

                else:  # SHORT
                    trigger_price = trailing_ref * 0.99          # -1% dari ref
                    if current_price <= trigger_price:
                        sl_delta = trailing_ref * 0.005          # 0.5% dari ref
                        new_sl   = pos['stop_loss'] - sl_delta
                        if new_sl < pos['stop_loss']:            # SL hanya boleh turun
                            old_sl = pos['stop_loss']
                            pos['stop_loss']       = round(new_sl, 8)
                            pos['trailing_sl_ref'] = trailing_ref * 0.99  # geser ref
                            if pos['symbol'] not in updated:
                                updated.append(pos['symbol'])
                            print(
                                f"🔀 TRAILING SL: {pos['symbol']} SHORT "
                                f"| Ref {trailing_ref:.6f} → {pos['trailing_sl_ref']:.6f} "
                                f"| SL {old_sl:.6f} → {new_sl:.6f} (-{sl_delta:.6f})"
                            )

        if updated:
            self.save_positions()

        return updated

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

            # jika sudah diatas 150% equity auto TP saja
            if (pos['current_price'] - pos['entry_price']) / pos['entry_price'] * 100 * pos['leverage'] > 150:
                exit_price = pos['current_price']
                exit_reason = 'AUTO_TP_HIT'

            else:
                # Gunakan TP3 sebagai final exit jika tersedia (Partial TP flow)
                # tp_stage 2 = TP1 & TP2 sudah hit, menunggu TP3 atau SL
                final_tp = pos.get('take_profit_3', pos['take_profit'])

                if pos['signal'] == 'LONG':
                    if current_price <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL_HIT'
                    elif current_price >= final_tp:
                        exit_price = final_tp
                        exit_reason = 'TP3_HIT' if pos.get('tp_stage', 0) >= 2 else 'TP_HIT'
                else:  # SHORT
                    if current_price >= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        exit_reason = 'SL_HIT'
                    elif current_price <= final_tp:
                        exit_price = final_tp
                        exit_reason = 'TP3_HIT' if pos.get('tp_stage', 0) >= 2 else 'TP_HIT'
            
            # Jika exit, hitung PnL dan tutup posisi
            if exit_price:
                # Hitung PnL berdasarkan qty sisa (bisa sudah 50% jika TP1 pernah hit)
                pnl = self._calculate_pnl_partial(pos, exit_price, pos['quantity'])

                # Label exit reason lebih spesifik untuk partial flow
                tp_stage_now = pos.get('tp_stage', 0)
                if exit_reason == 'TP_HIT' and tp_stage_now >= 2:
                    exit_reason = 'TP3_FINAL_CLOSE'
                elif exit_reason == 'TP3_HIT':
                    exit_reason = 'TP3_FINAL_CLOSE'
                elif exit_reason == 'SL_HIT' and tp_stage_now >= 2:
                    exit_reason = 'SL_HIT_AFTER_TP2'
                elif exit_reason == 'SL_HIT' and tp_stage_now >= 1:
                    exit_reason = 'SL_HIT_AFTER_TP1'

                closed_pos = {
                    'symbol'           : pos['symbol'],
                    'signal'           : pos['signal'],
                    'entry_price'      : pos['entry_price'],
                    'exit_price'       : exit_price,
                    'quantity'         : pos['quantity'],
                    'pnl_usdt'         : pnl,
                    'pnl_pct'          : (pnl / pos['margin_required'] * 100) if pos['margin_required'] > 0 else 0,
                    'opened_at'        : pos['opened_at'],
                    'closed_at'        : datetime.now().isoformat(),
                    'exit_reason'      : exit_reason,
                    'tp_stage_at_close': tp_stage_now,
                    'method'           : pos['method'],
                    'is_partial'       : False
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