import flet as ft
import logging as log
import os
import sys
import traceback
from datetime import datetime

# Add parent directory to path to import ui.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ui import main as ui_main


def setup_logging():
    """Set up logging to both console and file."""
    # Create logs directory in user's temp folder
    log_dir = os.path.join(os.path.expanduser('~'), 'ZORA_logs')
    os.makedirs(log_dir, exist_ok=True)

    # Create log file
    log_filepath = os.path.join(log_dir, 'zora_log.txt')

    # Configure logging with both file and console handlers
    log.basicConfig(
        level=log.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            log.FileHandler(log_filepath, encoding='utf-8'),
            log.StreamHandler(sys.stdout)
        ]
    )

    log.info("=" * 70)
    log.info("ZORA Application Starting")
    log.info(f"Log file: {log_filepath}")
    log.info(f"Python version: {sys.version}")
    log.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    log.info("=" * 70)

    return log_filepath


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Don't log keyboard interrupts
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log.error("=" * 70)
    log.error("UNHANDLED EXCEPTION")
    log.error("=" * 70)
    log.error("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    log.error("=" * 70)


def main():
    """Windows application entry point."""
    try:
        # Set up logging
        log_filepath = setup_logging()

        # Install global exception handler
        sys.excepthook = handle_exception

    except Exception as e:
        # If logging setup fails, at least try to write somewhere
        fallback_log = os.path.join(os.path.expanduser('~'), 'zora_error.log')
        with open(fallback_log, 'w') as f:
            f.write(f"Failed to set up logging: {e}\n")
            f.write(traceback.format_exc())
        raise

    try:
        # Get the assets directory path
        # When running as PyInstaller bundle, use sys._MEIPASS
        if getattr(sys, 'frozen', False):
            # Running in a PyInstaller bundle
            assets_dir = os.path.join(sys._MEIPASS, 'assets')
        else:
            # Running in normal Python environment (one level up from windows/)
            assets_dir = os.path.join(os.path.dirname(__file__), '..', 'assets')
            assets_dir = os.path.abspath(assets_dir)

        log.info(f"Assets directory: {assets_dir}")

        # Run the Flet app with assets directory configured
        ft.app(
            target=lambda page: ui_main.main(page, platform="windows"),
            assets_dir=assets_dir
        )

        log.info("Application closed normally")

    except Exception as e:
        log.error("=" * 70)
        log.error("FATAL ERROR IN MAIN")
        log.error("=" * 70)
        log.error(f"Error: {e}")
        log.error(traceback.format_exc())
        log.error("=" * 70)
        log.error(f"Please send the log file to the developers:")
        log.error(f"Log location: {log_filepath}")
        log.error("=" * 70)
        raise


if __name__ == "__main__":
    main()
