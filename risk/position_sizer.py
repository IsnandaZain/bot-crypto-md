# risk/position_sizer.py
from config import TRADING_CONFIG, RISK_CONFIG

class PositionSizer:
    def __init__(self, account_balance, leverage=None):
        """
        Args:
            account_balance: Total equity akun dalam USDT
            leverage: Leverage yang akan digunakan (default dari config)
        """
        self.balance = account_balance
        self.leverage = leverage or TRADING_CONFIG['leverage']
        self.cfg = RISK_CONFIG
    
    def calculate_position(self, entry_price, stop_loss_price, signal):
        """
        Hitung ukuran posisi berdasarkan risk management
        """
        if signal == "NO TRADE" or entry_price <= 0:
            return None

        # 1. Round harga terlebih dahulu, lalu hitung risk_distance sekali (fix #3)
        entry_price     = self._round_to_precision(entry_price, 6)
        stop_loss_price = self._round_to_precision(stop_loss_price, 6)

        risk_distance = abs(entry_price - stop_loss_price)
        risk_pct      = risk_distance / entry_price
        print(f"entry_price : {entry_price} | stop_loss_price : {stop_loss_price}")
        print(f"risk_distance : {risk_distance} | risk_pct : {risk_pct}")

        # 2. Hitung Modal yang Siap Di-risk
        max_position_pct = TRADING_CONFIG['max_position_size_pct'] / 100
        risk_capital     = self.balance * max_position_pct
        print(f"risk_capital : {risk_capital}")

        # 3. Hitung Quantity berbasis risk capital & risk distance (fix #1)
        # Rumus: quantity = risk_capital / risk_distance
        # Jaminan: jika kena SL → loss = quantity × risk_distance = risk_capital ✓
        if risk_distance > 0:
            quantity = risk_capital / risk_distance
        else:
            quantity = 0.0

        # 4. Hitung Position Value dari quantity, lalu batasi dengan buying power
        position_value   = quantity * entry_price
        max_buying_power = self.balance * self.leverage
        if position_value > max_buying_power:
            position_value = max_buying_power
            quantity       = position_value / entry_price

        print(f"position_value : {position_value}")

        # 5. Round quantity setelah semua kalkulasi selesai
        quantity = self._round_to_precision(quantity, 3)

        # 6. Hitung TP sesuai arah sinyal
        if signal == "LONG":
            take_profit_price = self._round_to_precision(
                entry_price + (risk_distance * self.cfg['rr_ratio']), 6
            )
        else:  # SHORT
            take_profit_price = self._round_to_precision(
                entry_price - (risk_distance * self.cfg['rr_ratio']), 6
            )

        # 7. Hitung Estimasi Fee (Taker fee Bybit ~0.05% - 0.06%)
        taker_fee_rate = 0.0006
        estimated_fee  = position_value * taker_fee_rate

        # 8. Loss aktual saat kena SL = quantity × risk_distance (fix #2)
        estimated_loss_at_sl = self._round_to_precision(quantity * risk_distance, 4)

        return {
            'signal': signal,
            'entry_price': entry_price,
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'quantity': quantity,
            'position_value_usdt': position_value,
            'leverage': self.leverage,
            'margin_required': position_value / self.leverage,
            'risk_capital': risk_capital,
            'estimated_loss_at_sl': estimated_loss_at_sl,
            'estimated_fee': estimated_fee,
            'account_balance': self.balance,
            'free_balance_after': self.balance - (position_value / self.leverage)
        }
    
    def _round_to_precision(self, value, precision):
        """Round angka sesuai presisi exchange"""
        return round(value, precision)