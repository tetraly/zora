"""Dialog and UI helper functions for the ZORA UI."""

import flet as ft
from typing import Optional
from datetime import datetime
import pytz
import os
import sys


def info_row(label: str,
             value: str,
             label_width: int = 120,
             value_width: Optional[int] = None) -> ft.Row:
    """Create a row with aligned label and value.

    Args:
        label: The label text
        value: The value text
        label_width: Width of the label container (default: 120)
        value_width: Width of the value container (default: None for auto)

    Returns:
        ft.Row: A Flet row with aligned label and value
    """
    value_text = ft.Text(value, selectable=True, no_wrap=True)
    if value_width:
        value_container = ft.Container(value_text, width=value_width)
    else:
        value_container = value_text

    return ft.Row(
        [ft.Container(ft.Text(f"{label}:", weight="w500"), width=label_width), value_container],
        spacing=10)


def show_error_dialog(page: ft.Page, title: str, message: str) -> None:
    """Show an error dialog with a message.

    Args:
        page: The Flet page object
        title: The dialog title
        message: The error message to display
    """

    def close_dlg(e) -> None:
        page.close(dialog)
        page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("OK", on_click=close_dlg),],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.open(dialog)
    page.update()


def show_snackbar(page: ft.Page, message: str) -> None:
    """Show a snackbar notification.

    Args:
        page: The Flet page object
        message: The message to display
    """
    page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
    page.snack_bar.open = True
    page.update()


def show_bug_report_dialog(page: ft.Page, error: Exception, seed: str = None, flagstring: str = None, zr_flagstring: str = None) -> None:
    """Show a bug report dialog with copy-pasteable information.

    Args:
        page: The Flet page object
        error: The exception that occurred
        seed: The ZORA seed being used (optional)
        flagstring: The ZORA flag string being used (optional)
        zr_flagstring: The Zelda Randomizer flag string from the base ROM (optional)
    """
    # Get version
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from version import __version_display__

    # Get current time in Eastern Time
    eastern = pytz.timezone('US/Eastern')
    current_time = datetime.now(eastern).strftime('%Y-%m-%d %I:%M:%S %p %Z')

    # Build the bug report text
    bug_report_lines = [
        f"Version: {__version_display__}",
        f"Date/Time: {current_time}",
        f"Error: {type(error).__name__}: {str(error)}",
        f"ZR Flags: {zr_flagstring if zr_flagstring else 'n/a'}",
        f"ZORA Flags: {flagstring if flagstring else 'n/a'}",
        f"Seed: {seed if seed else 'n/a'}",
    ]

    bug_report_text = "\n".join(bug_report_lines)

    # Create a text field for easy copying
    bug_report_field = ft.TextField(
        value=bug_report_text,
        multiline=True,
        read_only=True,
        min_lines=5,
        max_lines=10,
        text_size=12,
    )

    def close_dlg(e) -> None:
        page.close(dialog)
        page.update()

    def copy_to_clipboard(e) -> None:
        page.set_clipboard(bug_report_text)
        show_snackbar(page, "Bug report copied to clipboard!")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Achievement unlocked: Found a ZORA bug!"),
        content=ft.Column([
            ft.Text(
                "To help make ZORA better, report this in the ZORA Discord #bug-reports channel.",
                size=14
            ),
            ft.Container(height=10),
            ft.Text(
                "Please *copy and paste* the text below. Do not take a screenshot as it makes using the info harder.",
                size=14
            ),
            bug_report_field,
        ], tight=True, spacing=5),
        actions=[
            ft.TextButton("Copy to Clipboard", on_click=copy_to_clipboard),
            ft.TextButton("OK", on_click=close_dlg),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.open(dialog)
    page.update()
