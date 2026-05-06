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
    
    def analyze_reversal(self):
        """
        Agregator Multi-Timeframe khusus untuk SETUP REVERSAL.
        Logika berbeda dari Trend-Following:
        - HTF (1H) = Konteks & Filter Keamanan (bukan komandan arah)
        - LTF (15m) = Pemicu Entry & Konfirmasi Price Action
        - LTF trigger duluan = VALID (Early Reversal)
        - Threshold lebih ketat karena sifat counter-trend
        """
        # 1. Ambil hasil analisis reversal per timeframe
        h1_sig, h1_score, h1_reasons = self.base_se.analyze_reversal()
        m15_sig, m15_score, m15_reasons = self.lower_se.analyze_reversal()
        reasons = h1_reasons + m15_reasons

        total_score = 0.0
        final_signal = "NO TRADE"

        # 2. 🛡️ FILTER KEAMANAN: HTF ADX (Hard VETO)
        # Reversal melawan tren kuat = risiko tinggi. ADX > 30 di 1H = hindari.
        adx_1h = self.base_se.df.iloc[-2].get('adx', 0)
        if adx_1h > 30:
            return "NO TRADE", reasons + [f"🚫 HTF ADX VETO ({adx_1h:.0f} > 30) — Tren terlalu kuat untuk reversal"], round(total_score, 2)

        # ──────────────────────────────────────────────
        # SKENARIO A: KONFLUENSI PENUH (HTF & LTF SEARAH)
        # Probabilitas tertinggi, risiko terkontrol
        # ──────────────────────────────────────────────
        if h1_sig in ("LONG", "SHORT") and m15_sig == h1_sig:
            # Weighting seimbang karena keduanya sudah konfirmasi exhaustion + turn
            total_score = (h1_score * 0.5) + (m15_score * 0.5)

            if abs(total_score) >= 1.3:
                final_signal = h1_sig
                reasons.append("🔥 MTF CONFLUENCE: HTF & LTF Reversal Aligned")
            elif abs(total_score) >= 1.0:
                final_signal = "WATCH"
                reasons.append("⏳ STRONG SETUP: Wait for candle close to confirm")

        # ──────────────────────────────────────────────
        # SKENARIO B: EARLY REVERSAL (LTF Trigger, HTF Neutral/Context)
        # Sangat umum: LTF jenuh & berbalik duluan, HTF masih di zona ekstrem/ranging
        # ──────────────────────────────────────────────
        elif m15_sig in ("LONG", "SHORT") and h1_sig == "NEUTRAL":
            # Cek apakah HTF sebenarnya di zona ekstrem (belum trigger karena close/wick)
            prev_h1 = self.base_se.df.iloc[-2]
            h1_at_extreme = (
                (m15_sig == "SHORT" and prev_h1['high'] >= prev_h1['bb_upper']) or
                (m15_sig == "LONG" and prev_h1['low'] <= prev_h1['bb_lower'])
            )

            if h1_at_extreme or adx_1h < 20:
                # Favor LTF karena dia yang trigger duluan & timing entry lebih presisi
                total_score = (h1_score * 0.3) + (m15_score * 0.7)

                if abs(total_score) >= 1.2:
                    final_signal = m15_sig
                    reasons.append("⚡ EARLY ENTRY: LTF Reversal Trigger + HTF Context Valid")
                else:
                    final_signal = "WATCH"
                    reasons.append("👀 FORMING: LTF showing signs, wait for HTF follow-through")

        # ──────────────────────────────────────────────
        # SKENARIO C: DIVERGENSI / TIMING MISMATCH
        # HTF reversal SHORT, tapi LTF masih LONG (pullback kecil) atau sebaliknya
        # Dalam reversal, ini berarti "belum waktunya" atau "salah timing"
        # ──────────────────────────────────────────────
        elif h1_sig in ("LONG", "SHORT") and m15_sig in ("LONG", "SHORT") and h1_sig != m15_sig:
            return "NO TRADE", reasons + ["⚠️ TIMING MISMATCH — HTF & LTF conflict. Wait for alignment."], round(total_score, 2)

        # ──────────────────────────────────────────────
        # SKENARIO D: TIDAK ADA TRIGGER
        # ──────────────────────────────────────────────
        else:
            return "NO TRADE", reasons + ["No valid reversal setup detected across MTF"], round(total_score, 2)

        # 3. 🎯 THRESHOLD FINAL & OUTPUT
        if final_signal == "NO TRADE" and abs(total_score) < 0.8:
            reasons.append(f"📉 Confluence rendah (score: {total_score:.2f}, butuh ≥1.2)")
        elif final_signal == "WATCH":
            reasons.append(f"📊 Score {total_score:.2f} — Monitor, jangan entry dulu")

        return final_signal, reasons, round(total_score, 2)
    
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