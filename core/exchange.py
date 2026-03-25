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