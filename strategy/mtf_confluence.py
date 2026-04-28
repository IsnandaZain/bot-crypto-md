# strategy/mtf_confluence.py
from strategy.signal_engine import SignalEngine

class MTFConfluence:
    def __init__(self, df_dict, symbol):
        self.df_dict = df_dict
        self.symbol = symbol

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

        # 📊 Log skor individual per timeframe untuk memantau konfluensi
        print(f"📊 {self.symbol} TF Scores -> 4h: {higher_score} | 1h: {base_score} | 15m: {lower_score}")

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

    def save_signal_charts(self, signal_folder: str):
        """
        Simpan chart dari semua timeframe ke folder sinyal.
        
        Args:
            signal_folder: Path folder sinyal untuk menyimpan chart
        """
        try:
            self.higher_se.plot_and_save_to_signal_folder(
                signal_folder=signal_folder, 
                n_candles=30, 
                symbol=self.symbol
            )
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