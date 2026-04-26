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
        
        # 1. Hitung Risk Distance (Jarak SL dalam harga)
        risk_distance = abs(entry_price - stop_loss_price)
        risk_pct = risk_distance / entry_price  # Contoh: 0.05 = 5%
        print(f"entry_price : {entry_price} | stop_loss_price : {stop_loss_price}")
        print(f"risk_distance : {risk_distance} | risk_pct : {risk_pct}")
        
        # 2. Hitung Modal yang Siap Di-risk (Misal 5% dari balance)
        max_position_pct = TRADING_CONFIG['max_position_size_pct'] / 100  # 0.05
        risk_capital = self.balance * max_position_pct
        print(f"risk_capital : {risk_capital}")
        
        # 3. Hitung Ukuran Posisi Sebenarnya (Dengan Leverage)
        # Rumus: Position Value = Risk Capital / (Risk % * Leverage)
        # Ini memastikan jika kena SL, loss hanya sebesar risk_capital
        position_value = risk_capital * self.leverage  # Fallback jika SL = 0
        
        # 4. Batasi Position Value agar tidak melebihi buying power
        max_buying_power = self.balance * self.leverage
        if position_value > max_buying_power:
            position_value = max_buying_power
        
        # 5. Hitung Quantity Koin (Quantity = Value / Price)
        print(f"position_value : {position_value}")
        quantity = position_value / entry_price
        
        # 6. Sesuaikan dengan Precision Exchange (Bybit TAOUSDT)
        # TAO biasanya 3 desimal untuk quantity, 2 desimal untuk price
        quantity = self._round_to_precision(quantity, 3)  # 3 desimal
        entry_price = self._round_to_precision(entry_price, 6)
        stop_loss_price = self._round_to_precision(stop_loss_price, 6)
        take_profit_price = self._round_to_precision(
            entry_price + (abs(entry_price - stop_loss_price) * self.cfg['rr_ratio']), 6
        )
        
        # 7. Hitung Estimasi Fee (Taker fee Bybit ~0.05% - 0.06%)
        taker_fee_rate = 0.0006
        estimated_fee = position_value * taker_fee_rate
        
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
            'estimated_loss_at_sl': risk_capital,  # Karena kita hitung dari risk_capital
            'estimated_fee': estimated_fee,
            'account_balance': self.balance,
            'free_balance_after': self.balance - (position_value / self.leverage)
        }
    
    def _round_to_precision(self, value, precision):
        """Round angka sesuai presisi exchange"""
        return round(value, precision)