# strategy/mtf_confluence.py
from strategy.signal_engine import SignalEngine

class MTFConfluence:
    def __init__(self, df_dict):
        self.df_dict = df_dict
        # Buat SignalEngine untuk setiap TF
        self.higher_se = SignalEngine(df_dict['higher'], '4h')
        self.base_se = SignalEngine(df_dict['base'], '1h')
        self.lower_se = SignalEngine(df_dict['lower'], '15m')
    
    def analyze(self):
        """Gabungkan hasil analisis dari semua timeframe"""
        # Analisis per TF
        higher_signal, higher_score, higher_reasons = self.higher_se.analyze()
        base_signal, base_score, base_reasons = self.base_se.analyze()
        lower_signal, lower_score, lower_reasons = self.lower_se.analyze()
        
        # Bobot skor: Higher TF lebih penting
        total_score = (higher_score * 2) + (base_score * 1.5) + (lower_score * 1)
        
        reasons = higher_reasons + base_reasons + lower_reasons
        
        # Keputusan akhir
        if total_score >= 5:
            signal = "LONG"
        elif total_score <= -5:
            signal = "SHORT"
        else:
            signal = "NO TRADE"
            reasons.append("Skor konfluensi tidak cukup")
        
        # Veto: Jika higher TF netral, jangan trade
        if higher_signal == "NEUTRAL":
            signal = "NO TRADE"
            reasons.append("4h Trend Tidak Jelas (Veto)")
        
        return signal, reasons, total_score

    def get_risk_data(self):
        """Ambil data risiko dari Base TF (1h)"""
        base_data = self.base_se.get_data()
        return {
            'atr': base_data['atr'],
            'price': base_data['price'],
            'df_base': self.base_se.df  # ⭐ KIRIM DataFrame untuk deteksi S/R
        }