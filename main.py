# main.py
import time
import signal
from core.exchange import ExchangeManager
from core.data_fetcher import DataFetcher

from risk.manager import RiskManager
from risk.position_sizer import PositionSizer
from risk.position_tracker import PositionTracker
from risk.balance_manager import BalanceManager  # ⭐ Balance dinamis
from utils.logger import BotLogger
from utils.file_manager import get_today_folder, create_signal_folder
from utils.session_report import SessionReport
from utils.telegram_notifier import TelegramNotifier

from strategy.mtf_confluence import MTFConfluence
from strategy.mtf_confluence_bb import MTFConfluenceBB

from strategy.detect_regime_bb import DetectRegimeBB

from indicators.technical import IndicatorCalculator
from indicators.technical_bb import IndicatorCalculatorBB

from config import TRADING_CONFIG
from datetime import datetime
import os
import re
import json

WATCHLIST_FILE = os.path.join('data', 'watchlist.json')

def load_watchlist() -> list:
    """Baca watchlist dari data/watchlist.json (hot-reload setiap scan cycle)"""
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        wl = data.get('watchlist', [])
        if not wl:
            print(f"⚠️  watchlist.json kosong, tidak ada coin yang di-scan")
        return wl
    except FileNotFoundError:
        print(f"⚠️  {WATCHLIST_FILE} tidak ditemukan, watchlist kosong")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Format watchlist.json tidak valid: {e}")
        return []


def _map_reason_to_sentence(msg: str) -> str:
    """
    Map satu reason string (tanpa prefix TF) ke kalimat naratif Bahasa Indonesia.
    Dipanggil oleh _build_narrative() untuk setiap item di reasons list.
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


def _build_narrative(reasons: list, signal: str, score: float) -> str:
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

        sentence = _map_reason_to_sentence(msg)
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

    narrative = _build_narrative(reasons, signal_type, score)
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


# ─────────────────────────────────────────────────────────────────────────────
# SESSION TIME HELPER
# ─────────────────────────────────────────────────────────────────────────────

def is_active_session() -> bool:
    """
    Kembalikan True jika saat ini dalam jam sesi trading aktif.
    Sesi aktif : 14:00 – 02:00 WIB (hari berikutnya)
    Off-hours   : 02:00 – 14:00 WIB
    """
    h = datetime.now().hour
    return h >= 12 or h < 3

    
# ─────────────────────────────────────────────────────────────────────────────
# MONITOR MODE — hanya cek TP/SL posisi aktif (off-hours, 02:00-14:00)
# ─────────────────────────────────────────────────────────────────────────────

def monitor_positions(session: SessionReport = None, notifier: TelegramNotifier = None):
    """
    Mode monitor (off-hours) — hanya cek TP/SL/partial posisi aktif.
    Tidak scan sinyal baru. Hemat resource & API quota.
    """
    tracker     = PositionTracker()
    balance_mgr = BalanceManager()

    open_positions = [p for p in tracker.positions if p['status'] == 'OPEN']
    if not open_positions:
        print(f"💤 [MONITOR] {datetime.now().strftime('%H:%M:%S')} | Tidak ada posisi aktif")
        return

    # Connect exchange
    exchange_mgr = ExchangeManager()
    exchange     = exchange_mgr.connect()
    if not exchange:
        return

    # Fetch harga hanya untuk pair yang punya posisi aktif (hemat quota)
    open_symbols   = [p['symbol'] for p in open_positions]
    current_prices = {}
    for symbol in open_symbols:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_prices[symbol] = ticker['last']
        except Exception:
            pass

    if not current_prices:
        return

    # ── Monitoring (sama seperti bagian prioritas 1 di scan_market) ──────────
    tracker.update_unrealized_pnl(current_prices)

    _history_len_before = len(tracker.history)
    tracker.update_partial_tp(current_prices)

    # ⭐ Update balance dari partial TP (TP1 / TP2)
    new_partials = [r for r in tracker.history[_history_len_before:] if r.get('is_partial')]
    if new_partials:
        balance_mgr.update_from_closed_positions(new_partials)
        if notifier:
            for rec in new_partials:
                notifier.notify_partial_tp(rec)
        if session:
            session.record_closed(new_partials)

    tracker.update_breakeven_sl(current_prices)
    closed_positions = tracker.check_tp_sl(current_prices)

    if closed_positions:
        BotLogger.log_closed_positions(closed_positions)
        balance_mgr.update_from_closed_positions(closed_positions)
        if notifier:
            for rec in closed_positions:
                notifier.notify_position_closed(rec)
        if session:
            session.record_closed(closed_positions)

    tracker.save_positions()

    open_count = len([p for p in tracker.positions if p['status'] == 'OPEN'])
    print(
        f"💤 [MONITOR] {datetime.now().strftime('%H:%M:%S')} "
        f"| Posisi aktif: {open_count} "
        f"| Harga dicek: {len(current_prices)}"
    )


def scan_market(session: SessionReport = None, notifier: TelegramNotifier = None):
    print("\n" + "="*70)
    print("🚀 Memulai Multi-Coin MTF Scanner...")
    print("="*70)

    # ⭐ LOAD WATCHLIST (hot-reload dari data/watchlist.json)
    WATCHLIST = load_watchlist()
    print(f"📋 Watchlist ({len(WATCHLIST)} coin): {', '.join(WATCHLIST)}")

    # 0. ⭐ BUAT FOLDER TANGGAL OTOMATIS
    today_folder = get_today_folder()
    print(f"📁 Folder sinyal hari ini: {today_folder}")

    # 1. Connect Exchange
    exchange_mgr = ExchangeManager()
    exchange = exchange_mgr.connect()
    if not exchange:
        return
    
    # 2. Initialize Position Tracker (Load dari JSON)
    tracker = PositionTracker()

    # 3. ⭐ Initialize Balance Manager (Dynamic Balance)
    balance_mgr = BalanceManager()
    account_balance = balance_mgr.get_balance()
    print(f"💰 Balance saat ini: ${account_balance:.2f}")
    
    # 4. Fetch Current Prices untuk Semua Koin (Untuk Cek TP/SL)
    current_prices = {}
    for symbol in WATCHLIST:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_prices[symbol] = ticker['last']
        except:
            pass
    
    # 5. ⭐ PRIORITAS 1: Cek Posisi Aktif (TP/SL Check)
    print("\n" + "="*70)
    print("📍 CEK POSISI AKTIF (TP/SL)")
    print("="*70)
    
    tracker.update_unrealized_pnl(current_prices)

    # Catat panjang history sebelum update_partial_tp untuk deteksi record baru
    _history_len_before = len(tracker.history)
    tracker.update_partial_tp(current_prices)

    # ⭐ Update balance dari partial TP (TP1 / TP2) yang baru ter-trigger
    new_partial_records = [r for r in tracker.history[_history_len_before:] if r.get('is_partial')]
    if new_partial_records:
        balance_mgr.update_from_closed_positions(new_partial_records)
        account_balance = balance_mgr.get_balance()
        if notifier:
            for rec in new_partial_records:
                notifier.notify_partial_tp(rec)
        if session:
            session.record_closed(new_partial_records)

    tracker.update_breakeven_sl(current_prices)
    closed_positions = tracker.check_tp_sl(current_prices)

    # Log closed positions
    if closed_positions:
        BotLogger.log_closed_positions(closed_positions)
        # ⭐ Update balance dari PnL posisi yang di-close (final close)
        balance_mgr.update_from_closed_positions(closed_positions)
        # Refresh balance untuk scan berikutnya
        account_balance = balance_mgr.get_balance()
        # ⭐ Notifikasi posisi yang fully closed
        if notifier:
            for rec in closed_positions:
                notifier.notify_position_closed(rec)
        # ⭐ Catat ke session report
        if session:
            session.record_closed(closed_positions)

    # 6. ⭐ PRIORITAS 2: Cek Sinyal Baru (Hanya Jika Ada Slot)
    print("\n" + "="*70)
    print("🔍 CEK SINYAL BARU")
    print("="*70)

    summary = tracker.get_summary()
    open_positions_count = summary['total_positions']
    max_positions        = TRADING_CONFIG['max_open_positions']
    max_long             = TRADING_CONFIG.get('max_long_positions', max_positions)
    max_short            = TRADING_CONFIG.get('max_short_positions', max_positions)

    # Hitung posisi LONG dan SHORT yang sedang aktif
    all_positions = summary['positions']
    long_count  = sum(1 for p in all_positions if p['status'] == 'OPEN' and p['signal'] == 'LONG')
    short_count = sum(1 for p in all_positions if p['status'] == 'OPEN' and p['signal'] == 'SHORT')

    print(f"Posisi Terbuka : {open_positions_count}/{max_positions}")
    print(f"Long / Short   : {long_count}/{max_long}  |  {short_count}/{max_short}")

    new_signals = []

    # Hanya cari sinyal baru jika masih ada slot total
    if open_positions_count < max_positions:
        fetcher = DataFetcher(exchange)

        for symbol in WATCHLIST:
            print(f"\n🔍 Scanning {symbol}...")

            # Cek apakah ada posisi aktif untuk koin ini
            active_positions = tracker.get_active_positions(symbol)
            existing_signal = None

            # Tentukan arah sinyal yang boleh dicari
            if not active_positions:
                # Cek slot directional sebelum izinkan scan
                long_ok  = long_count  < max_long
                short_ok = short_count < max_short
                if not long_ok and not short_ok:
                    print(f"⛔ Slot LONG ({long_count}/{max_long}) dan SHORT ({short_count}/{max_short}) penuh → Skip")
                    continue
                elif not long_ok:
                    print(f"⚠️  Slot LONG penuh ({long_count}/{max_long}) → Hanya cari SHORT")
                elif not short_ok:
                    print(f"⚠️  Slot SHORT penuh ({short_count}/{max_short}) → Hanya cari LONG")
                else:
                    print("📍 Tidak ada posisi aktif → Mencari semua peluang")
                existing_signal = None
            else:
                active_sides = list(active_positions.keys())

                if "LONG" in active_sides and "SHORT" not in active_sides:
                    print("⚡ Ada posisi LONG → Mencari peluang SHORT saja (reversal/close)")
                    opposite_signal = "SHORT"
                    existing_signal = "LONG"
                elif "SHORT" in active_sides and "LONG" not in active_sides:
                    print("⚡ Ada posisi SHORT → Mencari peluang LONG saja (reversal/close)")
                    opposite_signal = "LONG"
                    existing_signal = "SHORT"
                else:
                    # Kasus Hedging: kedua sisi terbuka
                    print("⚡ Posisi LONG & SHORT aktif (Hedging) → Tidak cari entry baru")
                    continue

            # Fetch Multi-TF
            df_dict = fetcher.fetch_multi_timeframe(symbol)
            df_dict_bb = df_dict.copy()
            if df_dict is None:
                continue

            # Calculate Indicators
            ind_calc_bb = IndicatorCalculatorBB(df_dict_bb)
            df_dict_bb = ind_calc_bb.calculate_all()

            # Decide Method to Use (Trend Following / Reversal)
            detect_regime_bb = DetectRegimeBB(df_dict_bb)
            regime_bb = detect_regime_bb.detect()
            print(f"✅ Regime {regime_bb} used")

            # ⭐ Simpan df_dict ke file TXT untuk inspeksi data (Debug)
            try:
                safe_symbol = symbol.replace('/', '_').replace(':', '_')
                debug_file = f"data/{safe_symbol}_debug.txt"
                with open(debug_file, "w", encoding='utf-8') as f:
                    for tf_key, df in df_dict.items():
                        f.write(f"\n{'='*30} TIMEFRAME: {tf_key} {'='*30}\n")
                        f.write(df.tail(20).to_string(float_format='%.6f')) # Pastikan desimal terlihat 6 angka
                        f.write("\n")
                print(f"📄 Data debug {symbol} disimpan ke {debug_file}")
            except Exception as e:
                print(f"⚠️ Gagal menyimpan file debug untuk {symbol}: {e}")

            # Analyze Confluence - BB
            mtf_bb = MTFConfluenceBB(df_dict_bb, symbol)
            if regime_bb == "TREND_FOLLOWING":
                signal_bb, reasons_bb, score_bb = mtf_bb.analyze()
            elif regime_bb == "REVERSAL":
                signal_bb, reasons_bb, score_bb = mtf_bb.analyze_reversal()
            else:
                print(f"⚠️ Regime {regime_bb} wait n see")
                continue
            
            # 🎯 FILTER: Jika ada posisi aktif, hanya terima sinyal berlawanan
            if active_positions:
                if signal_bb == existing_signal:
                    print(f"⏭️  Skip {signal_bb} BB (sama dengan posisi aktif {existing_signal})")
                    signal_bb = "NO_TRADE"

            # 🎯 FILTER DIRECTIONAL: Cek slot LONG/SHORT sebelum terima sinyal baru
            if signal_bb == "LONG"  and long_count  >= max_long:
                print(f"⛔ Skip LONG — slot LONG penuh ({long_count}/{max_long})")
                signal_bb = "NO_TRADE"
            elif signal_bb == "SHORT" and short_count >= max_short:
                print(f"⛔ Skip SHORT — slot SHORT penuh ({short_count}/{max_short})")
                signal_bb = "NO_TRADE"

            # add logger - bb
            emoji_bb = "🟢" if signal_bb == "LONG" else "🔴" if signal_bb == "SHORT" else "⚪"
            print(f"Result BB : {symbol} - {emoji_bb} {signal_bb} | Score : ({score_bb})")

            # get risk data
            # risk_data = mtf.get_risk_data()
            risk_data_bb = mtf_bb.get_risk_data()

            if signal_bb not in ["NO_TRADE", "NO TRADE", "WATCH"]:
                # risk manager - bb
                rm_bb = RiskManager(
                    atr=risk_data_bb['atr'],
                    price=risk_data_bb['price'],
                    signal=signal_bb,
                    df_base=risk_data_bb.get('df_base')
                )
                risk_levels_bb = rm_bb.calculate_levels()

                # position sizer - bb
                ps_bb = PositionSizer(account_balance, TRADING_CONFIG['leverage'])
                position_info_bb = ps_bb.calculate_position(
                    entry_price=risk_levels_bb['entry'],
                    stop_loss_price=risk_levels_bb['stop_loss'],
                    signal=signal_bb
                )

                # Tambahkan symbol ke position_info
                position_info_bb['symbol'] = symbol
                position_info_bb['method'] = risk_levels_bb['method']

                # ⭐ BUAT FOLDER SINYAL & SIMPAN CHART
                signal_folder = create_signal_folder(
                    pair=symbol.replace('/', '').replace(':', ''),
                    signal_type=signal_bb,
                    base_folder=today_folder
                )

                # Simpan chart dari semua timeframe
                mtf_bb.save_signal_charts(signal_folder)
                
                # ⭐ SIMPAN DETAIL SINYAL KE TXT
                save_signal_details(
                    signal_folder=signal_folder,
                    symbol=symbol,
                    signal_type=signal_bb,
                    risk_data=risk_levels_bb,
                    position_data=position_info_bb,
                    reasons=reasons_bb,
                    regime=regime_bb,
                    score=score_bb,
                    method=risk_levels_bb.get('method', 'BB')
                )

                # Tambahkan ke tracker (sertakan risk_levels untuk TP1/TP2/TP3)
                tracker.add_position(position_info_bb, risk_levels=risk_levels_bb)

                # ⭐ Notifikasi entry baru ke Telegram
                if notifier:
                    notifier.notify_new_entry(
                        symbol        = symbol,
                        signal        = signal_bb,
                        risk_levels   = risk_levels_bb,
                        position_info = position_info_bb
                    )

                # ⭐ Pasang SL/TP orders ke exchange
                # paper=True: hanya log (tidak kirim ke Bybit)
                # Ubah paper=False saat siap live trading
                from core.exchange import place_sl_tp_orders
                place_sl_tp_orders(
                    symbol        = symbol,
                    signal        = signal_bb,
                    qty           = position_info_bb['quantity'],
                    entry_price   = risk_levels_bb['entry'],
                    stop_loss     = risk_levels_bb['stop_loss'],
                    take_profit_1 = risk_levels_bb['take_profit_1'],
                    take_profit_2 = risk_levels_bb['take_profit_2'],
                    take_profit_3 = risk_levels_bb['take_profit_3'],
                    paper         = True
                )

                # ⭐ Catat entry ke session report
                if session:
                    session.record_new_entry(
                        symbol=symbol,
                        signal=signal_bb,
                        opened_at=datetime.now().isoformat()
                    )

                # Update counter directional agar filter berikutnya akurat
                if signal_bb == "LONG":
                    long_count += 1
                elif signal_bb == "SHORT":
                    short_count += 1
                open_positions_count += 1

                new_signals.append({
                    'symbol': symbol,
                    'signal': signal_bb,
                    'reasons': reasons_bb,
                    'risk': risk_levels_bb,
                    'position': position_info_bb,
                    'chart_folder': signal_folder
                })


            
            time.sleep(1)
    else:
        print("⚠️ Slot posisi penuh. Tidak ada scan sinyal baru.")
    
    # 7. Save Final State
    tracker.save_positions()

    # 8. Print Summary
    summary = tracker.get_summary()
    BotLogger.print_position_summary(summary)
    BotLogger.print_new_signals(new_signals)

    # 9. Print Session Report
    if session:
        session.print_summary()

if __name__ == "__main__":
    notifier = TelegramNotifier()

    # ⭐ SIGTERM handler — untuk hard stop (server reboot, dll)
    _stop_flag = {'value': False}
    def _handle_sigterm(signum, frame):
        print("\n🛑 Bot dihentikan oleh sistem (SIGTERM)")
        _stop_flag['value'] = True
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # State tracking transisi sesi
    session      = SessionReport()
    _was_active  = None   # None = belum tahu state awal (siklus pertama)

    # ⭐ Periodic report tracking (06:00, 12:00, 18:00, 23:00)
    _REPORT_HOURS   = {6, 12, 18, 23}
    _reported_hours : set = set()

    _init_balance   = BalanceManager().get_balance()
    _init_watchlist = load_watchlist()
    notifier.notify_bot_started(len(_init_watchlist), _init_balance)

    while not _stop_flag['value']:
        try:
            _now_active = is_active_session()

            # ── Deteksi transisi sesi ─────────────────────────────────────────
            if _was_active is not None and _now_active != _was_active:
                if _now_active:
                    # ── 14:00: Sesi aktif dimulai ────────────────────────────
                    session = SessionReport()
                    notifier.notify_session_started(
                        balance     = BalanceManager().get_balance(),
                        pairs_count = len(load_watchlist())
                    )
                else:
                    # ── 02:00: Sesi aktif berakhir ───────────────────────────
                    session.print_summary()
                    notifier.notify_session_ended(session)
                    # Reset session — aktifitas off-hours tercatat di sesi baru
                    session = SessionReport()

            _was_active = _now_active

            # ── Jalankan sesuai mode ─────────────────────────────────────────
            if _now_active:
                scan_market(session, notifier)
                interval = 100
            else:
                monitor_positions(session, notifier)
                interval = 150

            # ── Periodic report (setiap 6 jam: 06, 12, 18, 23) ──────────────
            _current_hour = datetime.now().hour
            if _current_hour in _REPORT_HOURS and _current_hour not in _reported_hours:
                _pt      = PositionTracker()
                _open    = [p for p in _pt.positions if p['status'] == 'OPEN']
                _bm      = BalanceManager()
                notifier.notify_periodic_report(_open, _bm.get_balance(), _bm.get_reserve())
                _reported_hours.add(_current_hour)
            elif _current_hour not in _REPORT_HOURS:
                _reported_hours.discard(_current_hour)

            print(f"\n⏳ Menunggu {interval} detik...")
            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n🛑 Bot dihentikan oleh user")
            session.print_summary()
            notifier.notify_bot_stopped(session)
            break
        except SystemExit:
            break
        except Exception as e:
            print(f"❌ Error di main loop: {e}")
            time.sleep(90)

    # Final cleanup saat SIGTERM
    if _stop_flag['value']:
        session.print_summary()
        notifier.notify_bot_stopped(session)