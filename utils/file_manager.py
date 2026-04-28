# utils/file_manager.py
"""
Utility untuk manajemen folder sinyal:
- Membuat folder tanggal otomatis setiap project di-run
- Membuat sub-folder untuk setiap sinyal baru
"""

import os
from datetime import datetime


def get_today_folder(base_dir: str = "signals") -> str:
    """
    Buat/return folder dengan nama tanggal hari ini.
    
    Args:
        base_dir: Base directory untuk folder sinyal (default: "signals")
    
    Returns:
        Path absolut ke folder tanggal hari ini
    """
    today = datetime.now().strftime("%Y-%m-%d")
    today_folder = os.path.join(base_dir, today)
    
    # Buat folder jika belum ada
    os.makedirs(today_folder, exist_ok=True)
    
    return today_folder


def create_signal_folder(pair: str, signal_type: str, base_folder: str = None) -> str:
    """
    Buat sub-folder untuk sinyal dengan format {PAIR}_{SIGNAL_TYPE}_{HHMMSS}
    
    Args:
        pair: Nama pair (contoh: "SOLUSDT", "BTCUSDT")
        signal_type: Jenis sinyal ("LONG" atau "SHORT")
        base_folder: Folder base (default: folder tanggal hari ini)
    
    Returns:
        Path absolut ke folder sinyal yang baru dibuat
    """
    if base_folder is None:
        base_folder = get_today_folder()
    
    timestamp = datetime.now().strftime("%H%M%S")
    signal_folder = os.path.join(base_folder, f"{pair}_{signal_type}_{timestamp}")
    
    # Buat folder sinyal
    os.makedirs(signal_folder, exist_ok=True)
    
    return signal_folder


def get_signal_folder_path(pair: str, signal_type: str, timestamp: str = None, base_dir: str = "signals") -> str:
    """
    Buat path folder sinyal dengan timestamp spesifik (untuk testing/debugging).
    
    Args:
        pair: Nama pair
        signal_type: Jenis sinyal ("LONG" atau "SHORT")
        timestamp: Timestamp dalam format HHMMSS (default: sekarang)
        base_dir: Base directory
    
    Returns:
        Path absolut ke folder sinyal
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%H%M%S")
    
    today = datetime.now().strftime("%Y-%m-%d")
    signal_folder = os.path.join(base_dir, today, f"{pair}_{signal_type}_{timestamp}")
    
    return signal_folder
