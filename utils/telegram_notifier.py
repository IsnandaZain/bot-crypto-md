# utils/telegram_notifier.py
import requests
from datetime import datetime
from config import TELEGRAM_CONFIG


class TelegramNotifier:
    """
    Kirim notifikasi trading ke Telegram Bot.

    Setup:
        1. Buat bot via @BotFather di Telegram → dapat bot_token
        2. Kirim pesan ke bot tersebut, lalu ambil chat_id via:
               https://api.telegram.org/bot<TOKEN>/getUpdates
        3. Isi TELEGRAM_CONFIG di config.py:
               'enabled'   : True
               'bot_token' : '<token dari BotFather>'
               'chat_id'   : '<chat_id atau channel_id>'
        4. Set 'enabled': True

    Notifikasi yang dikirim:
        - Bot started
        - New entry (entry price, SL, TP1/TP2/TP3, size)
        - TP1 / TP2 partial close
        - TP3 final close / SL hit
        - Session report (end of session)
    """

    _BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self):
        self.enabled   = TELEGRAM_CONFIG.get('enabled', False)
        self.bot_token = TELEGRAM_CONFIG.get('bot_token', '')
        self.chat_id   = TELEGRAM_CONFIG.get('chat_id', '')
        self._url      = self._BASE_URL.format(token=self.bot_token)

    # ──────────────────────────────────────────────────────────────────────
    # Base
    # ──────────────────────────────────────────────────────────────────────

    def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Kirim pesan ke Telegram. Return True jika berhasil."""
        if not self.enabled:
            return False
        if not self.bot_token or not self.chat_id:
            print("⚠️  Telegram: bot_token / chat_id belum diisi di config.py")
            return False
        try:
            resp = requests.post(
                self._url,
                json={'chat_id': self.chat_id, 'text': text, 'parse_mode': parse_mode},
                timeout=10
            )
            if resp.status_code != 200:
                print(f"⚠️  Telegram API error {resp.status_code}: {resp.text[:120]}")
                return False
            return True
        except requests.exceptions.Timeout:
            print("⚠️  Telegram: timeout saat kirim pesan")
            return False
        except Exception as e:
            print(f"⚠️  Telegram error: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Event Notifications
    # ──────────────────────────────────────────────────────────────────────

    def notify_bot_started(self, watchlist_count: int, balance: float):
        """Notifikasi bot pertama kali start (service restart / deploy baru)."""
        if not self.enabled:
            return
        text = (
            f"🤖 <b>BOT STARTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Balance : <code>${balance:.2f} USDT</code>\n"
            f"📋 Pairs   : {watchlist_count} coins\n"
            f"🕐 {datetime.now().strftime('%d %b %Y %H:%M:%S')}"
        )
        self.send_message(text)

    def notify_session_started(self, balance: float, pairs_count: int):
        """Notifikasi sesi trading aktif dimulai (14:00 WIB)."""
        if not self.enabled:
            return
        text = (
            f"🟢 <b>SESI AKTIF DIMULAI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Balance : <code>${balance:.2f} USDT</code>\n"
            f"📋 Pairs   : {pairs_count} coins\n"
            f"🕐 {datetime.now().strftime('%d %b %Y %H:%M:%S')}"
        )
        self.send_message(text)

    def notify_session_ended(self, session):
        """Notifikasi sesi trading aktif berakhir (02:00 WIB) + kirim report."""
        if not self.enabled:
            return
        self.send_message(
            f"🔴 <b>SESI AKTIF BERAKHIR</b> — {datetime.now().strftime('%d %b %H:%M')}\n"
            f"Bot beralih ke mode monitor (off-hours)"
        )
        self.notify_session_report(session)

    def notify_bot_stopped(self, session):
        """Notifikasi bot stop paksa (SIGTERM / Ctrl+C) — kirim session report."""
        if not self.enabled:
            return
        self.send_message(f"🛑 <b>BOT STOPPED</b> — {datetime.now().strftime('%H:%M:%S')}")
        self.notify_session_report(session)

    def notify_new_entry(self, symbol: str, signal: str, risk_levels: dict, position_info: dict):
        """Notifikasi entry posisi baru."""
        if not self.enabled:
            return

        direction_emoji = "📈" if signal == "LONG" else "📉"
        entry  = risk_levels.get('entry', 0)
        sl     = risk_levels.get('stop_loss', 0)
        tp1    = risk_levels.get('take_profit_1', 0)
        tp2    = risk_levels.get('take_profit_2', 0)
        tp3    = risk_levels.get('take_profit_3', 0)
        qty    = position_info.get('quantity', 0)
        margin = position_info.get('margin_required', 0)
        coin   = symbol.split('/')[0]

        def _pct(price, ref):
            if not ref:
                return "0.00%"
            return f"{((price - ref) / ref * 100):+.2f}%"

        text = (
            f"{direction_emoji} <b>NEW ENTRY — {signal}</b>\n"
            f"📌 <b>{coin}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Entry  : <code>${entry:,.4f}</code>\n"
            f"🛑 SL     : <code>${sl:,.4f}</code>  <i>({_pct(sl, entry)})</i>\n"
            f"🎯 TP1    : <code>${tp1:,.4f}</code>  <i>({_pct(tp1, entry)})</i>\n"
            f"🎯 TP2    : <code>${tp2:,.4f}</code>  <i>({_pct(tp2, entry)})</i>\n"
            f"🎯 TP3    : <code>${tp3:,.4f}</code>  <i>({_pct(tp3, entry)})</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Margin : <code>${margin:.2f}</code>  Qty: <code>{qty:.4f}</code>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(text)

    def notify_partial_tp(self, record: dict):
        """Notifikasi partial TP1 atau TP2 dari partial_record di position_tracker."""
        if not self.enabled:
            return

        symbol      = record.get('symbol', '?')
        signal      = record.get('signal', '?')
        exit_reason = record.get('exit_reason', '')
        exit_price  = record.get('exit_price', 0)
        pnl         = record.get('pnl_usdt', 0)
        qty_closed  = record.get('quantity', 0)
        qty_remain  = record.get('qty_remain', 0)
        new_sl      = record.get('new_sl')
        coin        = symbol.split('/')[0]
        sign        = "+" if pnl >= 0 else ""
        tp_level    = 1 if exit_reason == 'TP1_PARTIAL_50PCT' else 2
        emoji       = "🎯"

        sl_line = f"🔒 SL baru : <code>${new_sl:,.4f}</code>\n" if new_sl else ""

        text = (
            f"{emoji} <b>TP{tp_level} HIT — PARTIAL CLOSE</b>\n"
            f"📌 <b>{coin}</b> {signal}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Exit    : <code>${exit_price:,.4f}</code>\n"
            f"📦 Closed  : <code>{qty_closed:.4f}</code>\n"
            f"📦 Sisa    : <code>{qty_remain:.4f}</code>\n"
            f"💵 PnL     : <code>{sign}${pnl:.4f}</code>\n"
            f"{sl_line}"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(text)

    def notify_position_closed(self, record: dict):
        """Notifikasi posisi fully closed (TP3 atau SL)."""
        if not self.enabled:
            return

        symbol      = record.get('symbol', '?')
        signal      = record.get('signal', '?')
        exit_reason = record.get('exit_reason', '?')
        exit_price  = record.get('exit_price', 0)
        entry_price = record.get('entry_price', 0)
        pnl         = record.get('pnl_usdt', 0)
        coin        = symbol.split('/')[0]
        sign        = "+" if pnl >= 0 else ""

        reason_map = {
            'TP3_FINAL_CLOSE'  : ("🏆", "TP3 HIT — FULL CLOSE"),
            'SL_HIT'           : ("❌", "SL HIT"),
            'SL_HIT_AFTER_TP1' : ("🔒", "SL HIT (setelah TP1)"),
            'SL_HIT_AFTER_TP2' : ("🔒", "SL HIT (setelah TP2)"),
            'AUTO_TP_HIT'      : ("⚡", "AUTO TP HIT"),
        }
        emoji, label = reason_map.get(exit_reason, ("📊", exit_reason))

        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0
        if signal == 'SHORT':
            pnl_pct = -pnl_pct

        text = (
            f"{emoji} <b>{label}</b>\n"
            f"📌 <b>{coin}</b> {signal}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Entry   : <code>${entry_price:,.4f}</code>\n"
            f"💰 Exit    : <code>${exit_price:,.4f}</code>  <i>({pnl_pct:+.2f}%)</i>\n"
            f"💵 PnL     : <code>{sign}${pnl:.4f}</code>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(text)

    def notify_session_report(self, session):
        """Kirim ringkasan sesi ke Telegram."""
        if not self.enabled:
            return

        sign         = "+" if session.total_pnl_usdt >= 0 else ""
        result_emoji = "✅" if session.total_pnl_usdt >= 0 else "🔴"
        duration     = session._duration_str()

        # Hitung win rate dari posisi yang fully closed
        closed_count = session.tp3_hit + session.breakeven_hit + session.sl_hit + session.auto_tp_hit
        wins         = session.tp3_hit + session.breakeven_hit + session.auto_tp_hit
        win_rate     = f"{(wins / closed_count * 100):.0f}%" if closed_count > 0 else "N/A"

        text = (
            f"📊 <b>SESSION REPORT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Mulai    : {session.session_start.strftime('%d %b %H:%M')}\n"
            f"⏱ Durasi   : {duration}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Entry    : {session.total_entries}\n"
            f"🎯 TP1      : {session.tp1_hit}  <i>(partial 50%)</i>\n"
            f"🎯 TP2      : {session.tp2_hit}  <i>(partial 25%)</i>\n"
            f"🏆 TP3      : {session.tp3_hit}  <i>(full close)</i>\n"
            f"🔒 BE+      : {session.breakeven_hit}  <i>(SL after TP)</i>\n"
            f"❌ SL       : {session.sl_hit}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Win Rate : {win_rate}\n"
            f"{result_emoji} PnL : <b><code>{sign}${session.total_pnl_usdt:.4f} USDT</code></b>"
        )
        self.send_message(text)

    def notify_periodic_report(self, open_positions: list, balance: float, reserve: float = 0.0):
        """
        Laporan berkala posisi aktif (06:00 / 12:00 / 18:00 / 23:59).
        Menampilkan detail setiap posisi beserta unrealized PnL.
        """
        if not self.enabled:
            return

        now = datetime.now().strftime('%d %b %H:%M')

        if not open_positions:
            text = (
                f"📋 <b>LAPORAN BERKALA</b> — {now}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Tidak ada posisi aktif saat ini.\n"
                f"💰 Balance : <code>${balance:.4f} USDT</code>\n"
                f"🏦 Reserve : <code>${reserve:.4f} USDT</code>"
            )
            self.send_message(text)
            return

        total_upnl = sum(p.get('unrealized_pnl', 0) for p in open_positions)
        total_sign = "+" if total_upnl >= 0 else ""

        lines = [
            f"📋 <b>LAPORAN BERKALA</b> — {now}",
            f"💰 Balance : <code>${balance:.4f} USDT</code>",
            f"🏦 Reserve : <code>${reserve:.4f} USDT</code>",
            f"📊 Open    : {len(open_positions)} posisi",
            f"━━━━━━━━━━━━━━━━━━━━",
        ]

        for pos in open_positions:
            coin      = pos['symbol'].split('/')[0]
            signal    = pos['signal']
            entry     = pos['entry_price']
            current   = pos.get('current_price', entry)
            upnl      = pos.get('unrealized_pnl', 0)
            upnl_pct  = pos.get('unrealized_pnl_pct', 0)
            tp_stage  = pos.get('tp_stage', 0)
            sl        = pos['stop_loss']
            tp1       = pos.get('take_profit_1', pos['take_profit'])
            tp2       = pos.get('take_profit_2', pos['take_profit'])
            tp3       = pos.get('take_profit_3', pos['take_profit'])
            opened_at = pos.get('opened_at', '')[:16].replace('T', ' ')

            sign      = "+" if upnl >= 0 else ""
            dir_emoji = "📈" if signal == "LONG" else "📉"
            stage_tag = f" <i>[TP{tp_stage}✓]</i>" if tp_stage > 0 else ""

            lines.append(
                f"\n{dir_emoji} <b>{coin}</b> {signal}{stage_tag}\n"
                f"   Buka   : <code>${entry:,.4f}</code>  <i>({opened_at})</i>\n"
                f"   Kini   : <code>${current:,.4f}</code>\n"
                f"   uPnL   : <code>{sign}${upnl:.4f}</code>  <i>({sign}{upnl_pct:.1f}%)</i>\n"
                f"   SL     : <code>${sl:,.4f}</code>\n"
                f"   TP1/2/3: <code>${tp1:,.4f}</code> / <code>${tp2:,.4f}</code> / <code>${tp3:,.4f}</code>"
            )

        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💼 Total uPnL : <code>{total_sign}${total_upnl:.4f} USDT</code>")

        self.send_message('\n'.join(lines))
