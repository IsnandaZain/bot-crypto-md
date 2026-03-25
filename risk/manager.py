# risk/manager.py
import numpy as np
from config import RISK_CONFIG, TRADING_CONFIG

class RiskManager:
    def __init__(self, atr, price, signal, df_base=None):
        """
        Args:
            atr: Nilai ATR dari Base TF
            price: Harga Entry saat ini
            signal: 'LONG' atau 'SHORT'
            df_base: DataFrame Base TF (1h) untuk deteksi S/R (opsional)
        """
        self.atr = atr
        self.price = price
        self.signal = signal
        self.cfg = RISK_CONFIG
        self.df_base = df_base
    
    def _find_nearest_support_resistance(self):
        """
        Deteksi Support & Resistance terdekat menggunakan Pivot High/Low sederhana.
        Returns:
            (support_price, resistance_price)
        """
        if self.df_base is None:
            return None, None
        
        df = self.df_base.copy()
        close = self.price
        lookback = self.cfg.get('sr_lookback', 20)
        buffer_pct = self.cfg.get('sr_buffer_pct', 0.005)
        
        # Ambil data lookback terakhir
        highs = df['high'].iloc[-lookback:].values
        lows = df['low'].iloc[-lookback:].values
        
        # 1. Cari Resistance: Highest High yang di ATAS harga saat ini
        resistances = highs[highs > close]
        nearest_resistance = resistances.min() if len(resistances) > 0 else None
        if nearest_resistance is not None:
            nearest_resistance = nearest_resistance * (1 + buffer_pct)
        
        # 2. Cari Support: Lowest Low yang di BAWAH harga saat ini
        supports = lows[lows < close]
        nearest_support = supports.max() if len(supports) > 0 else None
        if nearest_support is not None:
            nearest_support = nearest_support * (1 - buffer_pct)
        
        return nearest_support, nearest_resistance
    
    def _apply_guardrails(self, sl_price):
        """
        Pastikan SL tidak terlalu ketat (noise) atau terlalu longgar (risk besar).
        """
        min_dist = self.price * self.cfg.get('sl_min_pct', 0.01)
        max_dist = self.price * self.cfg.get('sl_max_pct', 0.05)
        
        if self.signal == "LONG":
            # SL harus di bawah harga
            min_sl = self.price - max_dist  # Jarak maks = SL paling jauh ke bawah
            max_sl = self.price - min_dist  # Jarak min = SL paling dekat ke bawah
            
            # Jika SL hitungan terlalu jauh, tarik ke max_dist
            if sl_price < min_sl:
                sl_price = min_sl
            # Jika SL hitungan terlalu dekat, dorong ke min_dist
            if sl_price > max_sl:
                sl_price = max_sl
        else:
            # SL harus di atas harga
            min_sl = self.price + min_dist
            max_sl = self.price + max_dist
            
            if sl_price > max_sl:
                sl_price = max_sl
            if sl_price < min_sl:
                sl_price = min_sl
        
        return sl_price
    
    def _apply_tp_guardrails(self, tp_price):
        """
        Pastikan TP tidak terlalu dekat (minimal profit worth it untuk risk yang diambil)
        """
        min_tp_dist = self.price * self.cfg.get('tp_min_pct', 0.03)
        
        if self.signal == "LONG":
            min_tp = self.price + min_tp_dist
            # Jika TP hitungan terlalu dekat, dorong ke minimum
            if tp_price < min_tp:
                tp_price = min_tp
        else:
            min_tp = self.price - min_tp_dist
            if tp_price > min_tp:
                tp_price = min_tp
        
        return tp_price
    
    def calculate_levels(self):
        """Hitung SL/TP dengan metode Hybrid ATR + S/R"""
        if self.signal == "NO TRADE":
            return None
        
        # --- 1. Hitung ATR-Based SL ---
        atr_sl_distance = self.atr * self.cfg['sl_atr_multiplier']
        if self.signal == "LONG":
            atr_sl = self.price - atr_sl_distance
        else:
            atr_sl = self.price + atr_sl_distance
        
        # --- 2. Hitung S/R-Based SL ---
        support, resistance = self._find_nearest_support_resistance()
        sr_sl = None
        sr_level_used = None
        
        if self.signal == "LONG" and support is not None:
            sr_sl = support
            sr_level_used = "Support"
        elif self.signal == "SHORT" and resistance is not None:
            sr_sl = resistance
            sr_level_used = "Resistance"
        
        # --- 3. Hybrid Logic ---
        use_hybrid = self.cfg.get('use_hybrid_sl', True)
        method_used = "ATR-only"
        
        if use_hybrid and sr_sl is not None:
            if self.signal == "LONG":
                final_sl = max(atr_sl, sr_sl)
            else:
                final_sl = min(atr_sl, sr_sl)
            
            if final_sl == sr_sl:
                method_used = f"Hybrid (S/R {sr_level_used})"
            else:
                method_used = "Hybrid (ATR Dominant)"
        else:
            final_sl = atr_sl
        
        # --- 4. Apply SL Guardrails ---
        final_sl = self._apply_guardrails(final_sl)
        
        # --- 5. Hitung Take Profit (Risk:Reward) ---
        risk_distance = abs(self.price - final_sl)
        tp_distance = risk_distance * self.cfg['rr_ratio']
        
        if self.signal == "LONG":
            take_profit = self.price + tp_distance
        else:
            take_profit = self.price - tp_distance
        
        # --- 6. Apply TP Guardrails (BARU) ---
        take_profit = self._apply_tp_guardrails(take_profit)
        
        # --- 7. Recalculate Risk:Reward setelah TP adjustment ---
        final_reward_distance = abs(take_profit - self.price)
        final_rr_ratio = final_reward_distance / risk_distance if risk_distance > 0 else 0
        
        stop_loss_pct = (self.price - final_sl) / self.price * 100
        take_profit_pct = (take_profit - self.price) / self.price * 100
        
        return {
            'entry': self.price,
            'stop_loss': final_sl,
            'stop_loss_pct': stop_loss_pct,
            'take_profit': take_profit,
            'take_profit_pct': take_profit_pct,
            'risk_distance': risk_distance,
            'reward_distance': final_reward_distance,
            'rr_ratio_actual': final_rr_ratio,
            'method': method_used,
            'atr_sl_raw': atr_sl,
            'sr_sl_raw': sr_sl,
            'leverage': TRADING_CONFIG['leverage'],
            'max_position_pct': TRADING_CONFIG['max_position_size_pct'],
            # ⭐ Informasi tambahan untuk analisis
            'sl_pct_from_entry': f"{(risk_distance / self.price * 100):.2f}%",
            'tp_pct_from_entry': f"{(final_reward_distance / self.price * 100):.2f}%",
            'equity_loss_at_sl': f"{(risk_distance / self.price * 100 * TRADING_CONFIG['leverage']):.1f}%"
        }