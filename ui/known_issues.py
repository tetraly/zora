"""Known Issues page for ZORA."""
import flet as ft


def build_known_issues_page(page: ft.Page, on_back) -> ft.Container:
    """Build the Known Issues page.

    Args:
        page: Flet page object
        on_back: Callback function to return to main page
    """
    return ft.Container(
        content=ft.Column([
            # Header
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    on_click=on_back,
                    tooltip="Back to main page"
                ),
                ft.Text(
                    "Known Issues & Bugs",
                    size=28,
                    weight="bold",
                    color=ft.Colors.BLUE_900
                )
            ], spacing=10),

            ft.Divider(height=20, thickness=2),

            # Introduction
            ft.Text(
                "This page tracks known issues, bugs, and limitations in ZORA. "
                "If you encounter an issue not listed here, please report it "
                "on Discord in the #z1r-chat channel on the Next Gen Discord\n"
                ,
                size=14,
                color=ft.Colors.GREY_800
            ),

            ft.Container(height=10),

            # Critical Issues
            ft.Text("Critical Issues", size=20, weight="bold", color=ft.Colors.RED_800),
            ft.Container(
                content=ft.Column([
                    ft.Text("• Some seed and flag combinations may cause a \"pop from empty list\" error when randomizing.", size=14),
                    ft.Text("• The code displayed in the UI when generating a seed may not match the code displayed in the player select menu.", size=14),
                    ft.Text("• Seeds may be unbeatable due to item placement logic still under development", size=14),
                    ft.Text("• When shuffling shop items, progression items in stores may be unreasonably expensive ", size=14),
                ], spacing=8),
                padding=10,
                border=ft.border.all(2, ft.Colors.RED_200),
                border_radius=5
            ),

            ft.Container(height=15),

            # Known Bugs
            ft.Text("Known Bugs", size=20, weight="bold", color=ft.Colors.ORANGE_800),
            ft.Container(
                content=ft.Column([
                    ft.Text("• Hints that are supposed to be truthful may not be accurate.", size=14),
                    ft.Text("  - Workaround: Select Community or Blank Hints in Zelda Randomizer", size=14, italic=True),
                    ft.Text("• An important item may be randomized next to the Wood Sword in the Wood Sword Cave .", size=14),
                    ft.Text("  - Workaround: Turn off the \"Add extra candles \" setting in Zelda Randomizer", size=14, italic=True),
                    ft.Text("• Important items may appear in level 9 even if the setting is turned off in Zelda Randomizer.", size=14),
                    ft.Text("• The new L4 sword may not always deal double Magical Sword damage.", size=14),
                    ft.Text("• Some of the options that shouldn't change the flagstring do change the flagstring.", size=14),                    
                ], spacing=8),
                padding=10,
                border=ft.border.all(2, ft.Colors.ORANGE_200),
                border_radius=5
            ),

            ft.Container(height=15),

            # Limitations
            ft.Text("Current Limitations", size=20, weight="bold", color=ft.Colors.BLUE_800),
            ft.Container(
                content=ft.Column([
                    ft.Text("• Not all feature combinations have been tested together", size=14),
                    ft.Text("• Books sold in shop (for boomstick seeds) will not be randomized.", size=14),
                    ft.Text("• Red potions randomized to dungeons may be downgraded to blue potions", size=14, italic=True),
                ], spacing=8),
                padding=10,
                border=ft.border.all(2, ft.Colors.BLUE_200),
                border_radius=5
            ),

            ft.Container(height=20),

            # How to Report
            ft.Text("How to Report Issues", size=20, weight="bold"),
            ft.Text(
                "When reporting an issue, please include:\n"
                "• The ZORA seed and flagstring\n"
                "• The base ROM type (vanilla or ZR-randomized)\n"
                "• Steps to reproduce the issue",
                size=14
            ),

            ft.Container(height=20),

            # Back button
            ft.ElevatedButton(
                "Back to Main Page",
                icon=ft.Icons.ARROW_BACK,
                on_click=on_back
            )
        ], spacing=5, scroll=ft.ScrollMode.AUTO),
        padding=20,
        expand=True
    )
