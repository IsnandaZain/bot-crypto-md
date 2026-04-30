# risk/balance_manager.py
import json
import os
from datetime import datetime
from config import TRADING_CONFIG, STORAGE_CONFIG


class BalanceManager:
    """
    Mengelola account balance secara dinamis.
    - Load/save balance dari file JSON
    - Update balance saat posisi di-close (TP/SL)
    - Sinkron dengan initial balance di config
    """

    def __init__(self, data_folder=None):
        self.data_folder = data_folder or STORAGE_CONFIG.get('data_folder', 'data')
        self.balance_file = os.path.join(self.data_folder, 'account_balance.json')

        # Pastikan folder ada
        os.makedirs(self.data_folder, exist_ok=True)

        # Load atau init balance
        self.balance = self._load_balance()

    def _load_balance(self):
        """Load balance dari file JSON. Jika tidak ada, pakai dari config."""
        if os.path.exists(self.balance_file):
            try:
                with open(self.balance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    balance = data.get('balance', TRADING_CONFIG['account_balance_usdt'])
                    last_updated = data.get('last_updated', 'Unknown')
                    print(f"💰 Balance loaded dari file: ${balance:.2f} (updated: {last_updated})")
                    return balance
            except Exception as e:
                print(f"⚠️ Gagal load balance dari file: {e}")

        # Fallback ke config
        balance = TRADING_CONFIG['account_balance_usdt']
        print(f"💰 Balance awal dari config: ${balance:.2f}")
        self._save_balance(balance, "Initial from config")
        return balance

    def _save_balance(self, balance, reason=""):
        """Simpan balance ke file JSON."""
        data = {
            'balance': balance,
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'reason': reason,
        }
        try:
            with open(self.balance_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Gagal save balance: {e}")

    def get_balance(self):
        """Ambil balance saat ini."""
        return self.balance

    def update_balance(self, pnl, reason="Trade closed"):
        """
        Update balance setelah posisi di-close.

        Args:
            pnl: Profit/Loss dalam USDT (bisa positif atau negatif)
            reason: Alasan update (TP_HIT, SL_HIT, dll)
        """
        old_balance = self.balance
        self.balance += pnl
        self.balance = round(self.balance, 6)  # Avoid floating point drift

        change = self.balance - old_balance
        change_pct = (change / old_balance * 100) if old_balance > 0 else 0

        emoji = "📈" if pnl >= 0 else "📉"
        print(f"{emoji} Balance updated: ${old_balance:.2f} → ${self.balance:.2f} ({change:+.6f}, {change_pct:+.2f}%) | Reason: {reason}")

        self._save_balance(self.balance, f"{reason}: {change:+.6f}")

    def update_from_closed_positions(self, closed_positions):
        """
        Update balance dari multiple closed positions.

        Args:
            closed_positions: List dari PositionTracker.check_tp_sl()
        """
        total_pnl = sum(pos['pnl_usdt'] for pos in closed_positions)
        if total_pnl != 0:
            reasons = ", ".join([f"{p['symbol']} {p['exit_reason']}" for p in closed_positions])
            self.update_balance(total_pnl, f"Closed: {reasons}")

    def reset_to_config(self):
        """Reset balance ke nilai awal di config (untuk testing/restart)."""
        self.balance = TRADING_CONFIG['account_balance_usdt']
        self._save_balance(self.balance, "Reset to config")
        print(f"🔄 Balance direset ke: ${self.balance:.2f}")
