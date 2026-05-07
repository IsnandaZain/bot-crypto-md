

class DetectRegimeBB:
    def __init__(self, df_dict):
        # hanya ambil timeframe base (1h)
        self.df = df_dict['base']

    def detect(self):
        """Mendeteksi rezim pasar → mengembalikan mode strategi yang aman"""
        if self.df.empty or len(self.df) < 4:
            return "NEUTRAL"

        row   = self.df.iloc[-1]   # forming candle — tidak dipakai untuk keputusan
        prev  = self.df.iloc[-2]   # closed candle ← SINYAL UTAMA
        prev2 = self.df.iloc[-3]   # untuk arah BB Width
        prev3 = self.df.iloc[-4]   # untuk konfirmasi tren BB Width

        # Baca dari closed candle agar stabil (bukan forming)
        adx = prev.get('adx', 0)
        rsi = prev.get('rsi', 50)

        # BB Width = volatilitas relatif (3 titik untuk tren arah)
        bb_width       = (prev['bb_upper']  - prev['bb_lower'])  / prev['bb_mid']
        bb_width_prev  = (prev2['bb_upper'] - prev2['bb_lower']) / prev2['bb_mid']
        bb_width_prev2 = (prev3['bb_upper'] - prev3['bb_lower']) / prev3['bb_mid']

        # Arah tren BB Width (3 candle berturut-turut)
        bb_expanding   = bb_width > bb_width_prev > bb_width_prev2
        bb_contracting = bb_width < bb_width_prev < bb_width_prev2

        rsi_extreme = rsi >= 70 or rsi <= 30

        # 1. TRENDING KUAT
        # ADX kuat + BB tidak menyempit tiba-tiba + RSI di zona wajar
        if adx > 25 and not bb_contracting and (45 < rsi <= 70 or 30 <= rsi < 50):
            return "TREND_FOLLOWING"

        # 2. RANGING / SIDEWAYS
        # ADX lemah + BB benar-benar menyempit (konsolidasi, belum pilih arah)
        # Bukan REVERSAL — belum ada tren yang di-reverse
        if adx < 20 and bb_contracting:
            return "RANGING"

        # 3. EXHAUSTION REVERSAL (ADX melemah + RSI ekstrem)
        # Tren aktif kehilangan energi + harga sudah overshooting
        # ADX < 22 agar tidak overlap dengan grey area 22-28
        if adx < 22 and rsi_extreme:
            return "REVERSAL"

        # 4. VOLATILITY EXPANSION (news/breakout)
        # BB expanding kuat atau lonjakan mendadak — tunggu retest
        if bb_expanding or bb_width > bb_width_prev * 1.4:
            return "NEUTRAL"

        # Default: grey area ambigu — tidak ada aksi yang aman
        if adx > 20 and not rsi_extreme:
            return "TREND_FOLLOWING"
        return "NEUTRAL"