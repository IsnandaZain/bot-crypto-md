# strategy/mtf_confluence_bb.py
from strategy.signal_engine_bb import SignalEngineBB

class MTFConfluenceBB:
    def __init__(self, df_dict, symbol):
        self.df_dict = df_dict
        self.symbol = symbol

        # Buat SignalEngine untuk setiap TF
        self.base_se = SignalEngineBB(df_dict['base'], '1h')
        self.lower_se = SignalEngineBB(df_dict['lower'], '15m')    

    def analyze(self):
        """Gabungkan hasil analisis dari semua timeframe — Confluence Rate based"""
        # Analisis per TF
        base_signal, base_score, base_reasons = self.base_se.analyze()
        lower_signal, lower_score, lower_reasons = self.lower_se.analyze()

        # 📊 Log skor individual per timeframe
        print(f"📊 {self.symbol} BB - TF Score 1h : {base_score:.2f} | Signal : {base_signal} || TF Score 15m: {lower_score:.2f} | Signal : {lower_signal}")
        reasons = base_reasons + lower_reasons

        # ──────────────────────────────────────────────
        # WEIGHTED CONFLUENCE SCORE
        # Bobot: 4h (50%) > 1h (30%) > 15m (20%)
        # ──────────────────────────────────────────────
        total_score = (base_score * 0.6) + (lower_score * 0.4)

        # VETO HIERARCHY — Hard rules
        if base_signal in ("NEUTRAL", "NO_TRADE"):
            signal = "NO TRADE"
            reasons.append("1H VETO — Tren tidak jelas di Higher TF")
            return signal, reasons, total_score

        # 2. Cek Divergensi antara 1H dan 15M
        is_divergent = (base_score > 0 and lower_score < 0) or (base_score < 0 and lower_score > 0)

        if is_divergent:
            # 🔹 OPSI A: STRICT VETO (Sangat disarankan untuk Futures & hold 36 jam)
            signal = "NO TRADE"
            reasons.append("DIVERGENCE VETO — 1H dan 15m berlawanan arah")
            return signal, reasons, total_score

        if total_score >= 1.0:
            signal = "LONG"
        elif total_score <= -1.0:
            signal = "SHORT"
        else:
            signal = "NO TRADE"
            reasons.append(f"Confluence lemah (score: {total_score:.2f}, butuh ±1.0)")

        return signal, reasons, total_score
    
    def get_risk_data(self):
        """Ambil data risiko dari Base TF (1h)"""
        base_data = self.base_se.get_data()
        return {
            'atr': base_data['atr'],
            'price': base_data['price'],
            'df_base': self.base_se.df  # ⭐ KIRIM DataFrame untuk deteksi S/R
        }

    def save_signal_charts(self, signal_folder: str):
        """
        Simpan chart dari semua timeframe ke folder sinyal.
        
        Args:
            signal_folder: Path folder sinyal untuk menyimpan chart
        """
        try:
            self.base_se.plot_and_save_to_signal_folder(
                signal_folder=signal_folder, 
                n_candles=30, 
                symbol=self.symbol
            )
            self.lower_se.plot_and_save_to_signal_folder(
                signal_folder=signal_folder, 
                n_candles=30, 
                symbol=self.symbol
            )
            print(f"✅ Semua chart {self.symbol} disimpan ke {signal_folder}")
        except Exception as e:
            print(f"⚠️ Gagal menyimpan chart {self.symbol}: {e}")