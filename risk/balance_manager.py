# risk/balance_manager.py
import json
import os
from datetime import datetime
from config import TRADING_CONFIG, STORAGE_CONFIG


class BalanceManager:
    """
    Mengelola account balance dan reserve balance secara dinamis.

    Aturan split PnL:
    - Profit (TP)  : 50% → balance (trading), 50% → reserve (protected)
    - Loss   (SL)  : 100% → balance saja, reserve tidak disentuh
    """

    def __init__(self, data_folder=None):
        self.data_folder  = data_folder or STORAGE_CONFIG.get('data_folder', 'data')
        self.balance_file = os.path.join(self.data_folder, 'account_balance.json')

        os.makedirs(self.data_folder, exist_ok=True)

        self.balance, self.reserve = self._load_balance()

    def _load_balance(self):
        """Load balance dan reserve dari file JSON. Jika tidak ada, pakai dari config."""
        if os.path.exists(self.balance_file):
            try:
                with open(self.balance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                balance = data.get('balance', TRADING_CONFIG['account_balance_usdt'])
                reserve = data.get('reserve', 0.0)
                last_updated = data.get('last_updated', 'Unknown')
                print(
                    f"💰 Balance loaded: ${balance:.4f} | Reserve: ${reserve:.4f} "
                    f"(updated: {last_updated})"
                )
                return balance, reserve
            except Exception as e:
                print(f"⚠️ Gagal load balance dari file: {e}")

        # Fallback ke config
        balance = TRADING_CONFIG['account_balance_usdt']
        reserve = 0.0
        print(f"💰 Balance awal dari config: ${balance:.2f} | Reserve: $0.00")
        self._save(balance, reserve, "Initial from config")
        return balance, reserve

    def _save(self, balance, reserve, reason=""):
        """Simpan balance dan reserve ke file JSON."""
        data = {
            'balance'     : round(balance, 6),
            'reserve'     : round(reserve, 6),
            'total'       : round(balance + reserve, 6),
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'reason'      : reason,
        }
        try:
            with open(self.balance_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Gagal save balance: {e}")

    def get_balance(self):
        """Ambil trading balance saat ini."""
        return self.balance

    def get_reserve(self):
        """Ambil reserve balance saat ini."""
        return self.reserve

    def update_balance(self, pnl, reason="Trade closed"):
        """
        Update balance dengan aturan split profit:
        - Profit : 50% ke balance, 50% ke reserve
        - Loss   : 100% dari balance, reserve tidak berubah
        """
        old_balance = self.balance
        old_reserve = self.reserve

        if pnl >= 0:
            # Profit — split 50/50
            to_balance  = round(pnl * 0.50, 6)
            to_reserve  = round(pnl * 0.50, 6)
            self.balance = round(self.balance + to_balance, 6)
            self.reserve = round(self.reserve + to_reserve, 6)

            print(
                f"📈 Profit split: +${pnl:.4f} → "
                f"Balance ${old_balance:.4f} → ${self.balance:.4f} (+${to_balance:.4f}) | "
                f"Reserve ${old_reserve:.4f} → ${self.reserve:.4f} (+${to_reserve:.4f}) | "
                f"{reason}"
            )
        else:
            # Loss — ambil full dari balance
            self.balance = round(self.balance + pnl, 6)

            change_pct = (pnl / old_balance * 100) if old_balance > 0 else 0
            print(
                f"📉 Loss from balance: ${old_balance:.4f} → ${self.balance:.4f} "
                f"({pnl:+.4f}, {change_pct:+.2f}%) | Reserve tidak berubah | {reason}"
            )

        self._save(self.balance, self.reserve, reason)

    def update_from_closed_positions(self, closed_positions):
        """
        Update balance dari multiple closed positions.
        Setiap posisi diproses individual agar split profit akurat.
        """
        for pos in closed_positions:
            pnl    = pos.get('pnl_usdt', 0)
            reason = f"{pos.get('symbol','?')} {pos.get('exit_reason','?')}"
            if pnl != 0:
                self.update_balance(pnl, reason)

    def reset_to_config(self):
        """Reset balance ke nilai awal di config, reserve ke 0 (untuk testing/restart)."""
        self.balance = TRADING_CONFIG['account_balance_usdt']
        self.reserve = 0.0
        self._save(self.balance, self.reserve, "Reset to config")
        print(f"🔄 Balance direset ke: ${self.balance:.2f} | Reserve: $0.00")

