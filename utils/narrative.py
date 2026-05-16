import re
import os
from datetime import datetime


class NarrativeBuilder:
    def __init__(self):
        pass

    @staticmethod
    def _map_reason_to_sentence(msg: str) -> str:
        """
        Map satu reason string (tanpa prefix TF) ke kalimat naratif Bahasa Indonesia.
        Dipanggil oleh build_narrative() untuk setiap item di reasons list.
        """
        # ── Trend Bias (BB Mid) ──────────────────────────────────────────────
        if 'Price Above BB Mid' in msg:
            candles = msg.split('(')[1].split(')')[0] if '(' in msg else '?/3'
            return f"harga konsisten berada di atas garis tengah Bollinger Bands selama {candles} terakhir, menandakan bias bullish yang dominan"
        if 'Price Below BB Mid' in msg:
            candles = msg.split('(')[1].split(')')[0] if '(' in msg else '?/3'
            return f"harga konsisten berada di bawah garis tengah Bollinger Bands selama {candles} terakhir, menandakan tekanan jual yang dominan"

        # ── Pullback / Spike Veto ────────────────────────────────────────────
        if 'PULLBACK VETO' in msg:
            return "terdeteksi bahwa pergerakan sebelumnya berlawanan secara signifikan — bias saat ini kemungkinan merupakan pullback sementara, bukan tren baru yang sejati"
        if 'Prior' in msg and 'noted' in msg:
            return "meski terdapat konteks momentum sebelumnya yang berlawanan, bias saat ini dinilai cukup kuat untuk dilanjutkan ke tahap analisis berikutnya"
        if 'SPIKE VETO' in msg:
            return "terdeteksi bahwa sentuhan band ekstrem terjadi tanpa prior trend yang mendukung — ini mengindikasikan spike mendadak, bukan exhaustion dari tren yang sudah matang"
        if 'Prior context lemah' in msg:
            return "konteks momentum sebelumnya tergolong lemah untuk mendukung setup reversal ini, sehingga perlu kewaspadaan ekstra dalam eksekusi"

        # ── BB Touch (Two-Tier) ──────────────────────────────────────────────
        if 'BB Strict Touch + S/R Confirmed' in msg:
            return "harga menyentuh band ekstrem Bollinger secara langsung (wick) sekaligus bertepatan dengan zona Support/Resistance yang valid, memberikan konfirmasi berlapis yang sangat kuat"
        if 'BB Near Touch + S/R Confirmed' in msg:
            m = re.search(r'%B=([\d.]+|N/A)', msg)
            val = m.group(1) if m else '?'
            return f"harga berada di zona 20% terluar Bollinger Bands (%B={val}) dan bertepatan dengan zona Support/Resistance yang valid, konfirmasi kuat meski belum menyentuh band secara langsung"
        if 'BB Strict Touch (No S/R Confirm)' in msg:
            return "harga menyentuh band ekstrem Bollinger secara langsung, namun tidak ada konfirmasi dari zona Support/Resistance sehingga kekuatan sinyal berkurang"
        if 'BB Near Touch (No S/R Confirm)' in msg:
            m = re.search(r'%B=([\d.]+|N/A)', msg)
            val = m.group(1) if m else '?'
            return f"harga mendekati band ekstrem Bollinger (%B={val}) namun belum menyentuhnya dan tidak ada konfirmasi S/R, memberikan sinyal parsial yang membutuhkan konfirmasi tambahan"
        if 'No BB Touch' in msg:
            m = re.search(r'%B=([\d.]+|N/A)', msg)
            val = m.group(1) if m else '?'
            return f"harga tidak berada di zona ekstrem Bollinger Bands (%B={val}), tidak ada trigger dari level volatilitas manapun"
        if 'PREREQ VETO' in msg:
            m = re.search(r'Volume lemah ([\d.]+x)', msg)
            vol = m.group(1) if m else '?'
            return f"sinyal ditolak pada tahap prasyarat karena tidak ada anchor price action yang valid — harga jauh dari zona band ekstrem dan volume lemah ({vol}), sehingga sinyal hanya berasal dari indikator lagging (RSI + MACD) tanpa pemicu harga yang nyata"

        # ── BB Band Position (Reversal) ──────────────────────────────────────
        if 'Price at Upper Band' in msg:
            return "harga mencapai atau melampaui Bollinger Band atas, sebuah zona overbought potensial yang menjadi pemicu analisis pembalikan arah"
        if 'Price at Lower Band' in msg:
            return "harga mencapai atau melampaui Bollinger Band bawah, sebuah zona oversold potensial yang menjadi pemicu analisis pembalikan arah"

        # ── ADX ──────────────────────────────────────────────────────────────
        if 'ADX low' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"ADX bernilai rendah ({val}), mengindikasikan pasar sedang dalam kondisi ranging atau sideways yang ideal untuk setup reversal"
        if 'ADX moderate' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"ADX berada di level moderat ({val}), tren tidak terlalu kuat sehingga masih terbuka peluang pembalikan meski perlu kehati-hatian"
        if 'ADX elevated' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"ADX cukup tinggi ({val}), menandakan tren masih aktif sehingga risiko reversal lebih tinggi dari kondisi normal"

        # ── S/R untuk Reversal ───────────────────────────────────────────────
        if 'S/R Confirmed at Extreme' in msg:
            return "posisi ekstrem ini bertepatan dengan zona Support/Resistance yang telah teruji sebelumnya, memperkuat probabilitas terjadinya pembalikan arah"
        if 'No S/R Alignment' in msg:
            return "tidak ditemukan zona Support/Resistance yang selaras di posisi ekstrem ini, sehingga probabilitas pembalikan relatif lebih rendah"

        # ── RSI ──────────────────────────────────────────────────────────────
        if 'RSI Agrees' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            arah = 'naik' if 'rising' in msg else 'turun'
            return f"RSI berada di level {val} dan sedang bergerak {arah}, mengkonfirmasi momentum yang selaras dengan arah bias tren"
        if 'RSI Overbought' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI memasuki zona overbought ({val}), mengindikasikan adanya risiko tekanan jual yang dapat membalikkan arah harga"
        if 'RSI Oversold' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI memasuki zona oversold ({val}), mengindikasikan adanya risiko tekanan beli yang dapat membalikkan arah harga"
        if 'RSI Wrong Direction' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI ({val}) bergerak berlawanan dengan arah bias tren, melemahkan konfirmasi momentum secara keseluruhan"
        if 'RSI Neutral' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI berada di zona netral ({val}) tanpa arah yang tegas, tidak memberikan konfirmasi momentum yang cukup"
        if 'RSI Exhausted & Rolling Back' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI ({val}) berada di zona ekstrem dan telah berbalik arah secara konsisten selama 2 candle berturut-turut, sebuah sinyal kelelahan momentum yang sangat kuat"
        if 'RSI Extreme, 1-candle turn' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI ({val}) berada di zona ekstrem dan baru mulai berbalik dalam 1 candle — belum cukup untuk konfirmasi penuh, perlu menunggu candle berikutnya"
        if 'RSI Extreme but Still Pushing' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI ({val}) berada di zona ekstrem namun masih bergerak searah tren, menunjukkan belum ada tanda kelelahan yang definitif"
        if 'RSI Not Extreme' in msg:
            m = re.search(r'\((\d+)', msg)
            val = m.group(1) if m else '?'
            return f"RSI ({val}) belum mencapai zona ekstrem, sehingga sinyal kelelahan momentum dari RSI belum terkonfirmasi"

        # ── MACD ─────────────────────────────────────────────────────────────
        if 'MACD Momentum Agrees' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '0'
            try:
                arah = "negatif dan melemah (bearish)" if float(val) < 0 else "positif dan menguat (bullish)"
            except ValueError:
                arah = "selaras dengan bias"
            return f"MACD histogram ({val}) bernilai {arah}, mengkonfirmasi momentum yang searah dengan tren"
        if 'MACD Direction OK but Wrong Side of Zero' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '0'
            return f"MACD histogram ({val}) bergerak ke arah yang tepat namun masih berada di sisi yang salah dari garis nol — konfirmasi parsial"
        if 'MACD Diverges' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '0'
            return f"MACD histogram ({val}) bergerak berlawanan arah dengan bias tren, menjadi faktor yang melemahkan sinyal"
        if 'MACD Momentum Fading' in msg:
            return "MACD histogram menunjukkan pelemahan momentum secara absolut, mengindikasikan kelelahan tren yang menjadi syarat utama setup reversal"
        if 'MACD Direction Fading but Magnitude Growing' in msg:
            return "MACD menunjukkan arah pelemahan namun nilai absolutnya masih membesar — momentum belum sepenuhnya habis, reversal belum terkonfirmasi penuh"
        if 'MACD Still Expanding' in msg:
            return "MACD histogram masih mengembang dan belum menunjukkan tanda pelemahan, mengindikasikan tren masih kuat dan belum siap untuk reversal"

        # ── Volume ───────────────────────────────────────────────────────────
        if 'Volume Climax' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume mencapai level climax ({val}x rata-rata) tepat di zona ekstrem, sebuah tanda kelelahan yang sangat kuat dan sering menandai akhir dari gerakan besar"
        if 'Volume Elevated' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume di atas rata-rata ({val}x), memberikan konfirmasi parsial terhadap potensi pembalikan arah"
        if 'Volume Strong' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume tergolong tinggi ({val}x rata-rata), menunjukkan partisipasi pasar yang kuat dan memperkuat validitas pergerakan harga"
        if 'Volume Moderate' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume cukup memadai ({val}x rata-rata), memberikan konfirmasi parsial terhadap pergerakan harga"
        if 'Volume Weak' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume tergolong lemah ({val}x rata-rata), menunjukkan kurangnya partisipasi pasar sehingga pergerakan harga ini kurang terkonfirmasi secara volume"
        if 'Volume Normal' in msg:
            m = re.search(r'\((-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"volume berada pada level normal ({val}x rata-rata), tidak ada sinyal climax yang mengkonfirmasi kelelahan"

        # ── Forming Candle ───────────────────────────────────────────────────
        if 'Forming candle confirms continuation' in msg:
            return "candle yang sedang terbentuk turut mengkonfirmasi kelanjutan pergerakan ke arah yang sama"
        if 'Forming candle shows strong rejection wick' in msg:
            return "candle yang sedang terbentuk menampilkan wick penolakan yang panjang, mengindikasikan tekanan pembalikan harga yang aktif"

        # ── Confluence Summary ───────────────────────────────────────────────
        if 'Reversal Confluence OK' in msg:
            m = re.search(r'\((\d+%)', msg)
            rate = m.group(1) if m else '?'
            return f"keseluruhan faktor reversal menghasilkan konfluensi {rate}, cukup untuk menghasilkan sinyal pembalikan arah"
        if 'Confluence OK' in msg:
            m = re.search(r'\((\d+%)', msg)
            rate = m.group(1) if m else '?'
            return f"keseluruhan faktor menghasilkan tingkat konfluensi {rate}, memenuhi threshold minimum untuk menghasilkan sinyal yang valid"
        if 'Confluence rendah' in msg:
            m = re.search(r'\((\d+%)', msg)
            rate = m.group(1) if m else '?'
            return f"tingkat konfluensi hanya mencapai {rate}, belum memenuhi threshold minimum"

        # ── MTF-level reasons (tanpa TF prefix) ──────────────────────────────
        if '1H VETO' in msg:
            return "Timeframe 1 jam tidak menunjukkan arah tren yang jelas sehingga bertindak sebagai veto terhadap sinyal apapun"
        if 'DIVERGENCE VETO' in msg:
            return "Terjadi divergensi arah antara timeframe 1 jam dan 15 menit — keduanya saling bertentangan sehingga tidak ada sinyal yang aman untuk dieksekusi"
        if 'Confluence lemah' in msg:
            m = re.search(r'score: (-?[\d.]+)', msg)
            val = m.group(1) if m else '?'
            return f"Skor konfluensi multi-timeframe hanya mencapai {val}, terlalu rendah untuk menghasilkan sinyal yang dapat diandalkan"
        if 'MTF CONFLUENCE' in msg:
            return "Kedua timeframe (1 jam dan 15 menit) menunjukkan arah yang selaras, menghasilkan konfluensi penuh antar timeframe"

        return None  # Reason dekoratif / tidak dikenali, skip


    @staticmethod
    def build_narrative(reasons: list, signal: str, score: float) -> str:
        """
        Konversi list reasons dari analyze() / analyze_reversal() menjadi satu
        paragraf naratif panjang Bahasa Indonesia untuk laporan sinyal.
        """
        tf_sentences: dict = {'1h': [], '15m': [], 'mtf': []}

        for reason in reasons:
            clean = reason.strip()
            if clean.startswith('1h:'):
                tf, msg = '1h', clean[3:].strip()
            elif clean.startswith('15m:'):
                tf, msg = '15m', clean[4:].strip()
            else:
                tf, msg = 'mtf', clean

            sentence = NarrativeBuilder._map_reason_to_sentence(msg)
            if sentence:
                tf_sentences[tf].append(sentence)

        parts = []
        signal_label = {'SHORT': 'SHORT (jual/turun)', 'LONG': 'LONG (beli/naik)'}.get(signal, signal)
        score_abs = abs(score)
        strength = "kuat" if score_abs >= 2.0 else "cukup kuat" if score_abs >= 1.5 else "moderat"

        parts.append(
            f"Sistem mengidentifikasi peluang {signal_label} dengan skor konfluensi "
            f"multi-timeframe sebesar {score:.2f} yang tergolong {strength}."
        )

        if tf_sentences['mtf']:
            parts.append(' '.join(tf_sentences['mtf']) + '.')

        if tf_sentences['1h']:
            joined = '; '.join(tf_sentences['1h'])
            parts.append(f"Pada timeframe 1 jam: {joined}.")

        if tf_sentences['15m']:
            joined = '; '.join(tf_sentences['15m'])
            parts.append(f"Pada timeframe 15 menit: {joined}.")

        parts.append(
            "Pastikan untuk memverifikasi kondisi pasar secara mandiri dan menerapkan "
            "manajemen risiko yang ketat sebelum mengeksekusi posisi."
        )

        return ' '.join(parts)
    
    @staticmethod
    def save_signal_details(signal_folder: str, symbol: str, signal_type: str, risk_data: dict, position_data: dict, reasons: list, regime: str, score: float = 0.0, method: str = "Unknown"):
        """
        Simpan detail sinyal ke file TXT dalam folder sinyal.
        
        Args:
            signal_folder: Path folder sinyal
            symbol: Nama pair/symbol
            signal_type: Jenis sinyal (LONG/SHORT)
            risk_data: Data risk (entry, stop_loss, take_profit, dll)
            position_data: Data position (size, leverage, dll)
            reasons: List alasan sinyal
            method: Metode yang digunakan (BB/EMA)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Helper untuk format price
        def fmt_price(val):
            if val is None:
                return "N/A"
            try:
                return f"${float(val):,.6f}"
            except:
                return str(val)

        def fmt_price_pct(val, entry, is_long: bool):
            """Format harga + persentase jarak terhadap entry price."""
            if val is None or entry is None:
                return "N/A"
            try:
                price = float(val)
                ref = float(entry)
                if ref == 0:
                    return fmt_price(val)
                pct = (price - ref) / ref * 100
                sign = "+" if pct >= 0 else ""
                return f"${price:,.6f}  ({sign}{pct:.2f}%)"
            except:
                return str(val)

        def fmt_val(val):
            return val if val is not None else "N/A"

        entry_price = risk_data.get('entry')
        is_long = signal_type == "LONG"
        base_coin = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')

        content = f"""================================================================================
                            📊 SIGNAL DETAILS
    ================================================================================

    📌 Symbol        : {symbol}
    📌 Signal Type   : {signal_type}
    📌 Regime        : {regime}
    📌 Method        : {method}
    📌 Generated At  : {timestamp}

    --------------------------------------------------------------------------------
                            💰 ENTRY & RISK LEVELS
    --------------------------------------------------------------------------------

    🎯 Entry Price   : {fmt_price(entry_price)}
    🛑 Stop Loss     : {fmt_price_pct(risk_data.get('stop_loss'), entry_price, is_long)}
    🎯 Take Profit 1 : {fmt_price_pct(risk_data.get('take_profit_1'), entry_price, is_long)}
    🎯 Take Profit 2 : {fmt_price_pct(risk_data.get('take_profit_2'), entry_price, is_long)}
    🎯 Take Profit 3 : {fmt_price_pct(risk_data.get('take_profit_3'), entry_price, is_long)}

    📊 Risk/Reward   : {fmt_val(risk_data.get('risk_reward_ratio'))}

    --------------------------------------------------------------------------------
                            📈 POSITION DETAILS
    --------------------------------------------------------------------------------

    💵 Position Size : {fmt_val(position_data.get('position_size_usd'))} USDT
    📊 Amount        : {fmt_val(position_data.get('amount'))} {base_coin}
    🔧 Leverage     : {fmt_val(position_data.get('leverage'))}x
    📐 Qty           : {fmt_val(position_data.get('qty'))}

    --------------------------------------------------------------------------------
                            🧠 SIGNAL REASONS
    --------------------------------------------------------------------------------

    """
        
        for i, reason in enumerate(reasons, 1):
            content += f"{i}. {reason}\n"

        narrative = NarrativeBuilder.build_narrative(reasons, signal_type, score)
        content += f"""
    --------------------------------------------------------------------------------
                            📝 ANALISIS NARATIF
    --------------------------------------------------------------------------------

    {narrative}

    """
        content += f"""
    --------------------------------------------------------------------------------
                            ⚠️ DISCLAIMER
    --------------------------------------------------------------------------------

    This signal is generated automatically by the trading bot.
    Always do your own research before making any trading decisions.
    Past performance does not guarantee future results.

    ================================================================================
    """
        
        # Clean symbol for filename
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        filename = os.path.join(signal_folder, f"{safe_symbol}_signal_details.txt")
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"📄 Signal details saved: {filename}")
        return filename


