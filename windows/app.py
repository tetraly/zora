import flet as ft
import os
import sys

# Add parent directory to path to import ui.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ui import main as ui_main


def main():
    """Windows application entry point."""
    # Get the assets directory path
    # When running as PyInstaller bundle, use sys._MEIPASS
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        assets_dir = os.path.join(sys._MEIPASS, 'assets')
    else:
        # Running in normal Python environment (one level up from windows/)
        assets_dir = os.path.join(os.path.dirname(__file__), '..', 'assets')
        assets_dir = os.path.abspath(assets_dir)

    # Run the Flet app with assets directory configured
    ft.app(
        target=lambda page: ui_main.main(page, platform="windows"),
        assets_dir=assets_dir
    )


if __name__ == "__main__":
    main()
