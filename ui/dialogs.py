"""Dialog and UI helper functions for the ZORA UI."""

import flet as ft
from typing import Optional


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
