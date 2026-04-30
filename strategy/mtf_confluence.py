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
        """Gabungkan hasil analisis dari semua timeframe — Confluence Rate based"""
        # Analisis per TF
        higher_signal, higher_score, higher_reasons = self.higher_se.analyze()
        base_signal, base_score, base_reasons = self.base_se.analyze()
        lower_signal, lower_score, lower_reasons = self.lower_se.analyze()

        # 📊 Log skor individual per timeframe
        print(f"📊 {self.symbol} TF Scores -> 4h: {higher_score:.2f} | 1h: {base_score:.2f} | 15m: {lower_score:.2f}")

        reasons = higher_reasons + base_reasons + lower_reasons

        # ──────────────────────────────────────────────
        # WEIGHTED CONFLUENCE SCORE
        # Bobot: 4h (50%) > 1h (30%) > 15m (20%)
        # Max weighted score = 3.0
        # ──────────────────────────────────────────────
        total_score = (higher_score * 0.5) + (base_score * 0.3) + (lower_score * 0.2)

        # VETO HIERARCHY — Hard rules
        # 1. Jika 4h NEUTRAL/NO_TRADE → veto semua
        if higher_signal in ("NEUTRAL", "NO_TRADE"):
            signal = "NO TRADE"
            reasons.append("4h VETO — Trend tidak jelas di higher TF")
            return signal, reasons, total_score

        # 2. Jika 4h dan 1h BERLAWANAN → veto
        if (higher_score > 0 and base_score < 0) or (higher_score < 0 and base_score > 0):
            signal = "NO TRADE"
            reasons.append("HTF DIVERGENCE — 4h dan 1h berlawanan arah")
            return signal, reasons, total_score

        # 3. Jika 15m berlawanan → warning tapi bisa trade jika HTF kuat
        if (higher_score > 0 and lower_score < -1) or (higher_score < 0 and lower_score > 1):
            reasons.append("LTF DIVERGENCE — 15m berlawanan, entry harus hati-hati")
            total_score *= 0.7  # Penalty 30%

        # ENTRY THRESHOLD
        # Score range: -3.0 to +3.0
        # Long: total_score >= 1.0 (konfluensi positif)
        # Short: total_score <= -1.0 (konfluensi negatif)
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