# strategy/mtf_confluence_bb.py
from strategy.signal_engine_bb import SignalEngineBB

class MTFConfluenceBB:
    def __init__(self, df_dict, symbol):
        self.df_dict = df_dict
        self.symbol = symbol

        # Buat SignalEngine untuk setiap TF
        self.higher_se = SignalEngineBB(df_dict['higher'], '4h')
        self.base_se = SignalEngineBB(df_dict['base'], '1h')
        self.lower_se = SignalEngineBB(df_dict['lower'], '15m')    

    def analyze(self):
        """Gabungkan hasil analisis dari semua timeframe"""
        # Analisis per TF
        higher_signal, higher_score, higher_reasons = self.higher_se.analyze()
        base_signal, base_score, base_reasons = self.base_se.analyze()
        lower_signal, lower_score, lower_reasons = self.lower_se.analyze()

        # 📊 Log skor individual per timeframe untuk memantau konfluensi
        print(f"📊 {self.symbol} BB - TF Scores -> 4h: {higher_score} | 1h: {base_score} | 15m: {lower_score}")

        # Generate Chart Image
        # higher_chart = self.higher_se.plot_and_save_last_n(n_candles=30, symbol=self.symbol)
        # base_chart = self.base_se.plot_and_save_last_n(n_candles=30, symbol=self.symbol)
        # lower_chart = self.lower_se.plot_and_save_last_n(n_candles=30, symbol=self.symbol)

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