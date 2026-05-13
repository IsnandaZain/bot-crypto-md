# utils/session_report.py
import json
import os
from datetime import datetime


class SessionReport:
    """
    Mencatat dan menyimpan laporan per session bot.

    Session dimulai saat scan_market() pertama kali dipanggil dalam satu run,
    dan disimpan ke file JSON setiap kali ada posisi yang close.

    Satu "trade" = satu posisi yang dibuka, meski menghasilkan 2 history record
    (TP1_PARTIAL_50PCT + TP2_FINAL_CLOSE atau SL_HIT_AFTER_TP1).
    PnL total = jumlah semua record yang terkait trade tersebut.
    """

    def __init__(self, data_folder: str = 'data'):
        self.data_folder    = data_folder
        self.session_start  = datetime.now()
        self.filename       = os.path.join(
            data_folder,
            f"session_{self.session_start.strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Counter trades (1 trade = 1 posisi dibuka)
        self._trade_ids: set = set()    # track trade unik via opened_at+symbol
        self.total_entries  = 0

        # Counter per exit category
        self.tp1_hit        = 0   # TP1_PARTIAL_50PCT
        self.tp2_hit        = 0   # TP2_FINAL_CLOSE
        self.breakeven_hit  = 0   # SL_HIT_AFTER_TP1  (10% margin profit)
        self.sl_hit         = 0   # SL_HIT langsung (sebelum TP1)
        self.auto_tp_hit    = 0   # AUTO_TP_HIT (>150% equity)

        # PnL kumulatif semua record (partial + final)
        self.total_pnl_usdt = 0.0

        # Raw records untuk keperluan Telegram nanti
        self._records: list = []

        self._save()

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def record_new_entry(self, symbol: str, signal: str, opened_at: str):
        """Dipanggil setiap kali posisi baru ditambahkan ke tracker."""
        trade_id = f"{symbol}_{opened_at}"
        if trade_id not in self._trade_ids:
            self._trade_ids.add(trade_id)
            self.total_entries += 1
            self._save()

    def record_closed(self, history_records: list):
        """
        Dipanggil setiap kali ada record baru masuk ke history tracker.
        Bisa berisi partial record (TP1) maupun final record (TP2/SL).

        Args:
            history_records: list of closed position dicts dari position_tracker
        """
        for rec in history_records:
            exit_reason = rec.get('exit_reason', '')
            pnl         = rec.get('pnl_usdt', 0.0)

            self.total_pnl_usdt += pnl
            self._records.append(rec)

            if exit_reason == 'TP1_PARTIAL_50PCT':
                self.tp1_hit += 1
            elif exit_reason == 'TP2_FINAL_CLOSE':
                self.tp2_hit += 1
            elif exit_reason == 'SL_HIT_AFTER_TP1':
                self.breakeven_hit += 1
            elif exit_reason in ('SL_HIT', 'SL_HIT_AFTER_TP1'):
                if exit_reason == 'SL_HIT':
                    self.sl_hit += 1
            elif exit_reason == 'AUTO_TP_HIT':
                self.auto_tp_hit += 1

        self._save()

    def print_summary(self):
        """Print ringkasan session ke console."""
        duration = self._duration_str()
        print("\n" + "=" * 60)
        print("📊 SESSION REPORT")
        print("=" * 60)
        print(f"  Mulai         : {self.session_start.strftime('%d %b %Y %H:%M:%S')}")
        print(f"  Durasi        : {duration}")
        print("-" * 60)
        print(f"  Total Entry   : {self.total_entries}")
        print(f"  Hit TP1       : {self.tp1_hit}  (partial 50% closed)")
        print(f"  Hit TP2       : {self.tp2_hit}  (full close)")
        print(f"  Breakeven 10% : {self.breakeven_hit}  (SL after TP1)")
        print(f"  Hit SL        : {self.sl_hit}  (langsung sebelum TP1)")
        print(f"  Auto TP       : {self.auto_tp_hit}  (>150% equity)")
        print("-" * 60)
        sign = "+" if self.total_pnl_usdt >= 0 else ""
        print(f"  Total PnL     : {sign}${self.total_pnl_usdt:.4f} USDT")
        print("=" * 60)

    # ──────────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────────

    def _duration_str(self) -> str:
        delta   = datetime.now() - self.session_start
        hours   = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}j {minutes}m"

    def _to_dict(self) -> dict:
        return {
            'session_start'  : self.session_start.isoformat(),
            'session_file'   : self.filename,
            'duration'       : self._duration_str(),
            'total_entries'  : self.total_entries,
            'tp1_hit'        : self.tp1_hit,
            'tp2_hit'        : self.tp2_hit,
            'breakeven_hit'  : self.breakeven_hit,
            'sl_hit'         : self.sl_hit,
            'auto_tp_hit'    : self.auto_tp_hit,
            'total_pnl_usdt' : round(self.total_pnl_usdt, 6),
            'records'        : self._records,
            'last_updated'   : datetime.now().isoformat(),
        }

    def _save(self):
        os.makedirs(self.data_folder, exist_ok=True)
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self._to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Gagal simpan session report: {e}")
