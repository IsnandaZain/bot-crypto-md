# core/exchange.py
import ccxt
from config import EXCHANGE_CONFIG


class ExchangeManager:
    def __init__(self):
        self.exchange = None

    def connect(self):
        """Inisialisasi koneksi ke exchange"""
        try:
            exchange_class = getattr(ccxt, EXCHANGE_CONFIG['name'])
            self.exchange = exchange_class({
                'enableRateLimit': EXCHANGE_CONFIG['enableRateLimit'],
                'options': {'defaultType': EXCHANGE_CONFIG['defaultType']},
                # 'proxies': EXCHANGE_CONFIG['proxies'],
                # API Key akan dimuat jika ada di config
                **({k: v for k, v in EXCHANGE_CONFIG.items() if k in ['apiKey', 'secret']})
            })
            print(f"✅ Terhubung ke {EXCHANGE_CONFIG['name'].upper()}")
            return self.exchange
        except Exception as e:
            print(f"❌ Gagal koneksi: {e}")
            return None

    def get_exchange(self):
        return self.exchange


def place_sl_tp_orders(
    symbol: str,
    signal: str,
    qty: float,
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: float,
    take_profit_3: float,
    paper: bool = True
) -> dict:
    """
    Pasang SL dan TP orders ke exchange setelah entry.

    Strategi order yang dikirim ke Bybit:
    ─────────────────────────────────────────────────────────────────
    • SL  : 1 order stop-market (100% qty) → reduceOnly=True
    • TP1 : 1 order limit (50% qty)        → reduceOnly=True
    • TP2 : 1 order limit (25% qty)        → reduceOnly=True
    • TP3 : 1 order limit (25% qty)        → reduceOnly=True

    Total qty TP1+TP2+TP3 = 100% qty posisi.
    SL dikirim sebagai stop terpisah (bukan TP3 = all-in).
    Exchange akan membatalkan SL otomatis setelah semua TP terisi.

    Args:
        symbol        : ccxt symbol, misal 'BTC/USDT:USDT'
        signal        : 'LONG' atau 'SHORT'
        qty           : total qty kontrak posisi (sudah disesuaikan leverage)
        entry_price   : harga entry (dipakai untuk log saja)
        stop_loss     : harga SL
        take_profit_1 : harga TP1 (50% qty)
        take_profit_2 : harga TP2 (25% qty)
        take_profit_3 : harga TP3 (25% qty)
        paper         : True = paper mode (tidak kirim order ke exchange)

    Returns:
        dict berisi status tiap order yang ditempatkan / disimulasikan
    """
    # Arah order penutup: LONG ditutup dengan 'sell', SHORT ditutup dengan 'buy'
    close_side = 'sell' if signal == 'LONG' else 'buy'

    # Pembagian qty: TP1=50%, TP2=25%, TP3=25%
    qty_tp1 = round(qty * 0.50, 8)
    qty_tp2 = round(qty * 0.25, 8)
    qty_tp3 = qty - qty_tp1 - qty_tp2   # sisa, hindari floating point rounding

    results = {
        'symbol'   : symbol,
        'signal'   : signal,
        'entry'    : entry_price,
        'paper'    : paper,
        'orders'   : {}
    }

    if paper:
        # ── PAPER MODE: log saja, tidak kirim ke exchange ─────────────────
        print(f"   📝 [PAPER] SL/TP orders untuk {symbol} {signal} @ {entry_price:.6f}")
        print(f"      SL  (100%={qty:.6f})  → stop @ {stop_loss:.6f}")
        print(f"      TP1 (50% ={qty_tp1:.6f}) → limit @ {take_profit_1:.6f}")
        print(f"      TP2 (25% ={qty_tp2:.6f}) → limit @ {take_profit_2:.6f}")
        print(f"      TP3 (25% ={qty_tp3:.6f}) → limit @ {take_profit_3:.6f}")

        results['orders'] = {
            'sl' : {'type': 'stop_market', 'qty': qty,     'price': stop_loss,     'status': 'simulated'},
            'tp1': {'type': 'limit',       'qty': qty_tp1, 'price': take_profit_1, 'status': 'simulated'},
            'tp2': {'type': 'limit',       'qty': qty_tp2, 'price': take_profit_2, 'status': 'simulated'},
            'tp3': {'type': 'limit',       'qty': qty_tp3, 'price': take_profit_3, 'status': 'simulated'},
        }
        return results

    # ── LIVE MODE ─────────────────────────────────────────────────────────
    # Aktifkan blok ini saat live trading (paper=False)
    try:
        exchange = ExchangeManager().connect()
        if exchange is None:
            raise ConnectionError("Gagal terhubung ke exchange")

        order_params = {'reduceOnly': True}

        # Stop-loss: stop-market order
        sl_order = exchange.create_order(
            symbol, 'stop_market', close_side, qty,
            params={**order_params, 'stopPrice': stop_loss, 'triggerDirection': 2 if signal == 'LONG' else 1}
        )
        results['orders']['sl'] = {'id': sl_order['id'], 'qty': qty, 'price': stop_loss, 'status': 'placed'}

        # TP1: limit order 50%
        tp1_order = exchange.create_order(
            symbol, 'limit', close_side, qty_tp1, take_profit_1,
            params=order_params
        )
        results['orders']['tp1'] = {'id': tp1_order['id'], 'qty': qty_tp1, 'price': take_profit_1, 'status': 'placed'}

        # TP2: limit order 25%
        tp2_order = exchange.create_order(
            symbol, 'limit', close_side, qty_tp2, take_profit_2,
            params=order_params
        )
        results['orders']['tp2'] = {'id': tp2_order['id'], 'qty': qty_tp2, 'price': take_profit_2, 'status': 'placed'}

        # TP3: limit order 25%
        tp3_order = exchange.create_order(
            symbol, 'limit', close_side, qty_tp3, take_profit_3,
            params=order_params
        )
        results['orders']['tp3'] = {'id': tp3_order['id'], 'qty': qty_tp3, 'price': take_profit_3, 'status': 'placed'}

        print(
            f"✅ SL/TP orders placed: {symbol} {signal} "
            f"| SL={stop_loss:.6f} TP1={take_profit_1:.6f} TP2={take_profit_2:.6f} TP3={take_profit_3:.6f}"
        )

    except Exception as e:
        print(f"❌ Gagal place SL/TP orders untuk {symbol}: {e}")
        results['error'] = str(e)

    return results