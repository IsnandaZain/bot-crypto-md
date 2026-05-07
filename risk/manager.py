# risk/manager.py
import numpy as np
import pandas as pd
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
        Baca nearest_support & nearest_resistance dari kolom df_base yang sudah
        dianotasi oleh SupportResistanceDetector, lalu terapkan sr_buffer_pct.
        Lebih akurat dibanding scan raw highs/lows karena S/R sudah divalidasi
        dengan pivot window + volume filter.
        """
        if self.df_base is None:
            return None, None

        # Gunakan closed candle (prev) agar konsisten dengan SignalEngineBB
        last = self.df_base.iloc[-2]
        buffer_pct = self.cfg.get('sr_buffer_pct', 0.005)

        nearest_sup = last.get('nearest_support', float('nan'))
        nearest_res = last.get('nearest_resistance', float('nan'))

        support    = float(nearest_sup) * (1 - buffer_pct) if not pd.isna(nearest_sup) else None
        resistance = float(nearest_res) * (1 + buffer_pct) if not pd.isna(nearest_res) else None

        return support, resistance
    
    def _get_dynamic_atr_multiplier(self):
        """
        Sesuaikan ATR multiplier berdasarkan kekuatan tren dari ADX (closed candle).

        Logika:
        - ADX rendah (ranging) → SL lebih ketat karena harga tidak trending jauh.
        - ADX tinggi (strong trend) → SL lebih lebar agar tidak terkena reversal noise.

        ADX Range     | Multiplier | Kondisi Pasar
        < 15          | 2.0        | Ranging / sideways
        15 – 20       | 2.5        | Tren lemah
        20 – 28       | 3.0        | Tren moderat
        ≥ 28          | 3.5        | Tren kuat
        """
        if self.df_base is None:
            return self.cfg['sl_atr_multiplier']

        adx = self.df_base.iloc[-2].get('adx', float('nan'))
        if pd.isna(adx):
            return self.cfg['sl_atr_multiplier']

        if adx < 15:
            return 2.0
        elif adx < 20:
            return 2.5
        elif adx < 28:
            return 3.0
        else:
            return 3.5

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
    
    def _apply_bb_aware_tp(self, tp_price: float, method_used: str):
        """
        Sesuaikan TP dengan mempertimbangkan BB Mid sebagai level mean reversion utama.

        Rasional:
        - BB Mid (MA20) adalah magnet utama harga setelah menyentuh band ekstrem.
        - Jika RR-based TP melewati BB Mid, ada risiko harga berbalik sebelum mencapai target.
        - Strategi: clamp TP ke BB Mid (+ buffer kecil) jika BB Mid berada di antara
          entry dan RR-TP, sehingga TP lebih realistis dan probabilitas hit lebih tinggi.

        LONG  : entry < BB Mid < RR-TP → TP di clamp ke BB Mid (tidak overshoot ke atas)
        SHORT : RR-TP < BB Mid < entry → TP di clamp ke BB Mid (tidak overshoot ke bawah)
        """
        if self.df_base is None:
            return tp_price, method_used

        last = self.df_base.iloc[-2]  # closed candle, konsisten dengan SignalEngineBB
        bb_mid = last.get('bb_mid', float('nan'))

        if pd.isna(bb_mid):
            return tp_price, method_used

        bb_buffer = 0.002  # 0.2% — jangan tepat di BB Mid agar tidak kena spread

        if self.signal == "SHORT":
            # Price turun: TP < entry. BB Mid obstacle jika: RR-TP < BB Mid < entry
            if tp_price < bb_mid < self.price:
                tp_price    = bb_mid * (1 - bb_buffer)
                method_used = method_used + " + BB Mid TP Cap"
        else:  # LONG
            # Price naik: TP > entry. BB Mid obstacle jika: entry < BB Mid < RR-TP
            if self.price < bb_mid < tp_price:
                tp_price    = bb_mid * (1 + bb_buffer)
                method_used = method_used + " + BB Mid TP Cap"

        return tp_price, method_used

    def _calculate_tp_levels(self, risk_distance: float):
        """
        Hitung 3 level TP berdasarkan struktur harga dan BB.

        TP1 (Konservatif) — Mean Reversion Target:
            Snap ke BB Mid jika BB Mid jatuh antara entry dan TP2.
            Ideal untuk partial close atau pair yang sering berbalik di BB Mid.
            Fallback: entry ± 1× risk_distance.

        TP2 (Standard) — Core RR Target:
            entry ± rr_ratio × risk_distance (default 2×).
            Target utama posisi.

        TP3 (Max) — Extended Target:
            entry ± (rr_ratio + 1)× risk_distance.
            Snap ke BB band berlawanan jika band tersebut lebih konservatif dari target,
            karena band berlawanan adalah batas atas/bawah natural Bollinger.

        Ordering selalu dijaga: untuk SHORT TP3 < TP2 < TP1, untuk LONG TP1 < TP2 < TP3.
        """
        entry     = self.price
        direction = 1 if self.signal == "LONG" else -1
        rr_ratio  = self.cfg['rr_ratio']
        bb_buf    = 0.002  # 0.2% buffer agar tidak tepat di level BB (hindari spread)

        # ── Base targets dari kelipatan risk_distance ────────────────────────
        tp1_raw = entry + direction * risk_distance * 1.0
        tp2_raw = entry + direction * risk_distance * rr_ratio
        tp3_raw = entry + direction * risk_distance * (rr_ratio + 1.0)

        # ── Baca BB columns dari closed candle ───────────────────────────────
        bb_mid   = float('nan')
        bb_upper = float('nan')
        bb_lower = float('nan')
        if self.df_base is not None:
            last     = self.df_base.iloc[-2]
            bb_mid   = last.get('bb_mid',   float('nan'))
            bb_upper = last.get('bb_upper', float('nan'))
            bb_lower = last.get('bb_lower', float('nan'))

        # ── TP1: snap ke BB Mid jika BB Mid berada antara entry dan TP2 ──────
        # BB Mid adalah magnet mean reversion paling dekat — jadikan TP1 yang realistis.
        if not pd.isna(bb_mid):
            if self.signal == "SHORT" and tp2_raw < bb_mid < entry:
                tp1_raw = bb_mid * (1 - bb_buf)
            elif self.signal == "LONG" and entry < bb_mid < tp2_raw:
                tp1_raw = bb_mid * (1 + bb_buf)

        # ── TP3: snap ke BB band berlawanan jika calculated TP3 melewati band──
        # BB band berlawanan adalah batas natural volatilitas.
        # Jika TP3 lebih ambisius dari band, tarik ke band (lebih konservatif & realistis).
        if self.signal == "SHORT" and not pd.isna(bb_lower):
            # SHORT target harga turun; BB Lower = support natural, jangan lampaui
            if tp3_raw <= bb_lower:
                tp3_raw = bb_lower * (1 - bb_buf)
        elif self.signal == "LONG" and not pd.isna(bb_upper):
            # LONG target harga naik; BB Upper = resistance natural, jangan lampaui
            if tp3_raw >= bb_upper:
                tp3_raw = bb_upper * (1 + bb_buf)

        # ── Apply minimum TP guardrail ke setiap level ───────────────────────
        tp1 = self._apply_tp_guardrails(tp1_raw)
        tp2 = self._apply_tp_guardrails(tp2_raw)
        tp3 = self._apply_tp_guardrails(tp3_raw)

        # ── Pastikan urutan TP tidak terbalik akibat adjustment ──────────────
        if self.signal == "SHORT":
            # Harga turun: TP3 < TP2 < TP1 (dalam nilai absolut)
            tp2 = min(tp2, tp1)
            tp3 = min(tp3, tp2)
        else:
            # Harga naik: TP1 < TP2 < TP3 (dalam nilai absolut)
            tp2 = max(tp2, tp1)
            tp3 = max(tp3, tp2)

        return tp1, tp2, tp3

    def calculate_levels(self):
        """Hitung SL/TP dengan metode Hybrid ATR + S/R, Dynamic ATR Multiplier, dan TP1/TP2/TP3"""
        if self.signal == "NO TRADE":
            return None
        
        # --- 1. ATR Multiplier Dinamis berdasarkan ADX ---
        atr_multiplier  = self._get_dynamic_atr_multiplier()
        atr_sl_distance = self.atr * atr_multiplier
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
        method_used = f"ATR-only (×{atr_multiplier})"
        
        if use_hybrid and sr_sl is not None:
            if self.signal == "LONG":
                final_sl = max(atr_sl, sr_sl)
            else:
                final_sl = min(atr_sl, sr_sl)
            
            if final_sl == sr_sl:
                method_used = f"Hybrid S/R {sr_level_used} (ATR×{atr_multiplier})"
            else:
                method_used = f"Hybrid ATR Dominant (×{atr_multiplier})"
        else:
            final_sl = atr_sl
        
        # --- 4. Apply SL Guardrails ---
        final_sl = self._apply_guardrails(final_sl)
        
        # --- 5. Hitung TP1, TP2, TP3 ---
        risk_distance = abs(self.price - final_sl)
        take_profit_1, take_profit_2, take_profit_3 = self._calculate_tp_levels(risk_distance)
        
        # --- 6. Recalculate RR berdasarkan TP2 (standard target) ---
        reward_distance = abs(take_profit_2 - self.price)
        rr_ratio_actual = reward_distance / risk_distance if risk_distance > 0 else 0
        
        # Pct selalu positif (fix A) — gunakan abs()
        stop_loss_pct    = abs(self.price - final_sl) / self.price * 100
        tp1_pct          = abs(take_profit_1 - self.price) / self.price * 100
        tp2_pct          = abs(take_profit_2 - self.price) / self.price * 100
        tp3_pct          = abs(take_profit_3 - self.price) / self.price * 100

        return {
            'entry': self.price,
            'stop_loss': final_sl,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2,
            'take_profit_3': take_profit_3,
            'tp1_pct': tp1_pct,
            'tp2_pct': tp2_pct,
            'tp3_pct': tp3_pct,
            # Backward-compat: take_profit = TP2 (standard target)
            'take_profit': take_profit_2,
            'take_profit_pct': tp2_pct,
            'risk_distance': risk_distance,
            'reward_distance': reward_distance,
            'rr_ratio_actual': rr_ratio_actual,
            'method': method_used,
            'atr_sl_raw': atr_sl,
            'atr_multiplier_used': atr_multiplier,
            'sr_sl_raw': sr_sl,
            'leverage': TRADING_CONFIG['leverage'],
            'max_position_pct': TRADING_CONFIG['max_position_size_pct'],
            'sl_pct_from_entry': f"{stop_loss_pct:.2f}%",
            'tp1_pct_from_entry': f"{tp1_pct:.2f}%",
            'tp2_pct_from_entry': f"{tp2_pct:.2f}%",
            'tp3_pct_from_entry': f"{tp3_pct:.2f}%",
            'equity_loss_at_sl': f"{(risk_distance / self.price * 100 * TRADING_CONFIG['leverage']):.1f}%"
        }