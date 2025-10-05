"""Web entry point for Render.com deployment."""
import flet as ft
import os
import sys

# Add parent directory to path to import ui.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ui import main as ui_main


def main(page: ft.Page):
    """Web application entry point."""
    ui_main.main(page, platform="web")


if __name__ == "__main__":
    # Run as web app on the port specified by Render (default 8080)
    port = int(os.environ.get("PORT", 8080))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port)
