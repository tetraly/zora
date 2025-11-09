import flet as ft
import logging as log
import os
import sys

# CRITICAL: Set PYTHONHASHSEED=0 for deterministic hash functions
# This ensures the same seed/flags always produce the same ROM
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Add parent directory to path to import ui.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ui import main as ui_main


def main():
    """macOS application entry point."""
    # Configure logging
    log.basicConfig(
        level=log.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    ft.app(target=lambda page: ui_main.main(page, platform="macos"))


if __name__ == "__main__":
    main()
