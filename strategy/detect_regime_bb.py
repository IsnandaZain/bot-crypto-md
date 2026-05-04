

class DetecRegimeBB:
    def __init__(self, df_dict):
        # hanya ambil timeframe base (1h)
        self.df = df_dict['base']

    def detect(self):
        """Mendeteksi rezim pasar → mengembalikan mode strategi yang aman"""
        if self.df.empty or len(self.df) < 3:
            return "NEUTRAL"
            
        row = self.df.iloc[-1]
        prev = self.df.iloc[-2]
        prev2 = self.df.iloc[-3]
        
        adx = row.get('adx', 0)
        rsi = row.get('rsi', 50)
        
        # BB Width = volatilitas relatif
        bb_width = (row['bb_upper'] - row['bb_lower']) / row['bb_mid']
        bb_width_prev = (prev['bb_upper'] - prev['bb_lower']) / prev['bb_mid']
        
        # 1. TRENDING KUAT
        if adx > 25 and bb_width >= bb_width_prev * 0.9 and (45 < rsi < 70 or 30 < rsi < 55):
            return "TREND_FOLLOWING"
            
        # 2. RANGING / REVERSAL ZONE
        if adx < 20 and bb_width < bb_width_prev * 1.15:
            return "REVERSAL"
            
        # 3. EXHAUSTION TRANSISI (ADX turun + RSI ekstrem)
        if adx < 28 and (rsi > 70 or rsi < 30):
            return "REVERSAL"
            
        # 4. VOLATILITY EXPANSION (news/breakout)
        if bb_width > bb_width_prev * 1.4:
            return "NEUTRAL"  # Tunggu retest
            
        # Default aman
        return "TREND_FOLLOWING" if adx > 20 else "REVERSAL"