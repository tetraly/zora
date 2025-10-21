import flet as ft
import io
import logging as log
import os
import random
import re
import tempfile
import sys
from pathlib import Path
from typing import Callable, Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logic.flags import FlagsEnum, Flags
from logic.randomizer import Z1Randomizer
from common.constants import CODE_ITEMS
from windows import zrinterface
from ui.known_issues import build_known_issues_page


# ============================================================================
# ROM UTILITIES
# ============================================================================

def extract_code_from_bytes(code_bytes: bytes) -> str:
    """Extract the code from ROM code bytes.

    Args:
        code_bytes: 4 bytes from ROM addresses 0xAFD0-0xAFD3

    Returns:
        str: Comma-separated item names

    Raises:
        ValueError: If code bytes are invalid
    """
    # Look up in CODE_ITEMS and join (reverse byte order)
    items = [
        CODE_ITEMS.get(code_bytes[3]),
        CODE_ITEMS.get(code_bytes[2]),
        CODE_ITEMS.get(code_bytes[1]),
        CODE_ITEMS.get(code_bytes[0])
    ]

    # Check if any items are None (invalid code bytes)
    if None in items:
        raise ValueError("Unable to determine ROM code - invalid code bytes")

    # Filter out None values for type checker (already verified no None above)
    valid_items: list[str] = [item for item in items if item is not None]
    return ", ".join(valid_items)


def extract_base_rom_code(filename: str) -> str:
    """Extract the code from a ROM file.

    Reads bytes at ROM addresses 0xAFD0-0xAFD3 (file offset 0xAFE0-0xAFE3)
    and returns the item names as a comma-separated string.

    Raises:
        Exception: If the file cannot be read or code items cannot be determined
    """
    with open(filename, 'rb') as f:
        # Seek to 0xAFD4 (0xAFD0 + 4 to read backwards)
        f.seek(0xAFD4)
        code_bytes = f.read(4)

    return extract_code_from_bytes(code_bytes)


def extract_code_from_rom_data(rom_data: bytes, offset: int = 0xAFD4) -> str:
    """Extract the code from ROM data bytes.

    Args:
        rom_data: The ROM data bytes
        offset: Offset to code bytes (default 0xAFD4)

    Returns:
        str: Comma-separated item names, or "Unknown" if extraction fails
    """
    try:
        code_bytes = rom_data[offset:offset+4]
        return extract_code_from_bytes(code_bytes)
    except Exception:
        return "Unknown"


def is_vanilla_rom(filename: str) -> bool:
    try:
        with open(filename, 'rb') as f:
            f.seek(0xAFD4)
            return f.read(4) == b'\xff\xff\xff\xff'
    except Exception:
        return False

def is_vanilla_rom_data(rom_data: bytes) -> bool:
    """Check if ROM data is from a vanilla ROM by checking for 0xFF bytes at code location."""
    try:
        return rom_data[0xAFD4:0xAFD4+4] == b'\xff\xff\xff\xff'
    except Exception:
        return False

def parse_filename_for_flag_and_seed(filename: str) -> tuple[str, str]:
    """Extract flagstring and seed from ROM filename.

    Expects pattern: [basename]_[seed]_[flagstring].nes

    Returns:
        tuple: (flagstring, seed)

    Raises:
        ValueError: If the filename doesn't match the expected pattern
    """
    # Match pattern: _[digits]_[flagstring].nes
    # Flagstring can contain uppercase, lowercase, digits, and "!"
    match = re.search(r'_(\d+)_([A-Za-z0-9!]{23,36})\.nes$', filename)

    if match:
        seed = match.group(1)
        flagstring = match.group(2)
        return flagstring, seed

    # If pattern doesn't match, raise an error
    raise ValueError(
        f"Invalid ROM filename format.\n\n"
        f"Expected pattern: [basename]_[seed]_[flagstring].nes\n\n"
        f"Your filename: {os.path.basename(filename)}"
    )


def info_row(label: str, value: str, label_width: int = 120, value_width: Optional[int] = None) -> ft.Row:
    """Create a row with aligned label and value.

    Args:
        label: The label text
        value: The value text
        label_width: Width of the label container (default: 120)
        value_width: Width of the value container (default: None for auto)

    Returns:
        ft.Row: A Flet row with aligned label and value
    """
    value_text = ft.Text(value, selectable=True)
    if value_width:
        value_container = ft.Container(value_text, width=value_width)
    else:
        value_container = value_text

    return ft.Row([
        ft.Container(
            ft.Text(f"{label}:", weight="w500"),
            width=label_width
        ),
        value_container
    ], spacing=10)


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
            ft.TextButton("OK", on_click=close_dlg),
        ],
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


# ============================================================================
# FLAG STATE MANAGEMENT
# ============================================================================

class FlagState:
    """Manages the state of randomizer flags."""

    # Class-level constants for flagstring encoding
    LETTER_MAP = ['B', 'C', 'D', 'F', 'G', 'H', 'K', 'L']
    VALID_LETTERS = {'B': 0, 'C': 1, 'D': 2, 'F': 3, 'G': 4, 'H': 5, 'K': 6, 'L': 7}

    def __init__(self):
        # Create a dictionary to store flag states, excluding complex flags
        self.flags = {}
        self.complex_flags = {'starting_items', 'skip_items'}

        for flag in FlagsEnum:
            if flag.value not in self.complex_flags:
                self.flags[flag.value] = False

        self.seed = ""

    def to_flagstring(self) -> str:
        """Convert flag state to a 5-letter flagstring.

        Each letter represents 3 flags in octal format:
        B=000, C=001, D=010, F=011, G=100, H=101, K=110, L=111
        (Avoiding A, E, I, O, U vowels)
        """

        # Get all non-complex flags in order
        non_complex_flags = [f for f in FlagsEnum if f.value not in self.complex_flags]

        # Build binary string from flags
        binary_str = ''.join('1' if self.flags.get(f.value, False) else '0' for f in non_complex_flags)

        # Pad to multiple of 3 if needed
        while len(binary_str) % 3 != 0:
            binary_str += '0'

        # Convert to letter format (3 bits per letter)
        letters = []
        for i in range(0, len(binary_str), 3):
            chunk = binary_str[i:i+3]
            octal_value = int(chunk, 2)
            letters.append(self.LETTER_MAP[octal_value])

        return ''.join(letters)

    def from_flagstring(self, flagstring: str) -> bool:
        """Parse a flagstring and update state.

        Returns:
            bool: True if valid flagstring, False otherwise
        """
        s = flagstring.strip().upper()

        # Check if all characters are valid letters
        if not all(c in self.VALID_LETTERS for c in s):
            return False

        # Convert letters to binary string
        binary_str = ''
        for letter in s:
            octal_value = self.VALID_LETTERS[letter]
            binary_str += format(octal_value, '03b')

        # Apply to flags
        non_complex_flags = [f for f in FlagsEnum if f.value not in self.complex_flags]
        for i, flag in enumerate(non_complex_flags):
            if i < len(binary_str):
                self.flags[flag.value] = binary_str[i] == '1'

        return True

    def to_randomizer_flags(self):
        """Convert FlagState to a Flags object for the randomizer.

        Returns:
            Flags: A Flags object with all enabled flags set
        """
        randomizer_flags = Flags()
        for flag_key, flag_value in self.flags.items():
            if flag_value:  # Only set flags that are True
                setattr(randomizer_flags, flag_key, True)
        return randomizer_flags


class RomInfo:
    """Stores information about the loaded ROM."""

    def __init__(self):
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""

    def clear(self) -> None:
        """Reset all ROM info."""
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""


# ============================================================================
# UI COMPONENT BUILDERS
# ============================================================================

def build_rom_info_card(rom_info: RomInfo, on_close) -> ft.Card:
    """Build the card displaying ROM information."""
    # Determine display values based on ROM type
    if rom_info.rom_type == "vanilla":
        rom_type_display = "Vanilla"
        flagstring_display = "n/a"
        seed_display = "n/a"
        code_display = "n/a"
    else:  # randomized
        rom_type_display = "Randomized using Zelda Randomizer (ZR)"
        flagstring_display = rom_info.flagstring
        seed_display = rom_info.seed
        code_display = rom_info.code

    return ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Row(
                    [
                        ft.Text("Loaded Base ROM", size=18, weight="bold"),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            tooltip="Remove ROM",
                            on_click=on_close
                        )
                    ],
                    alignment="spaceBetween"
                ),
                info_row("ROM Type", rom_type_display),
                info_row("Filename", rom_info.filename),
                info_row("ZR Flag String", flagstring_display),
                info_row("ZR Seed", seed_display),
                info_row("ZR Code", code_display)
            ], spacing=5),
            padding=10,
            margin=0,
            border=ft.border.all(2, ft.Colors.BLUE_200),
            border_radius=10
        ),
        elevation=4
    )


def build_zora_settings_card(flagstring: str, seed: str, flag_state) -> ft.Card:
    """Build the card displaying ZORA settings used for randomization.

    Args:
        flagstring: The ZORA flagstring
        seed: The ZORA seed number
        flag_state: The FlagState object containing all flag values
    """
    # Generate lists of enabled and disabled flags
    enabled_flags = []
    disabled_flags = []

    for flag in FlagsEnum:
        if flag_state.flags.get(flag.value, False):
            enabled_flags.append(flag.display_name)
        else:
            disabled_flags.append(flag.display_name)

    # Create flag list displays
    enabled_text = ", ".join(enabled_flags) if enabled_flags else "None"
    disabled_text = ", ".join(disabled_flags) if disabled_flags else "None"

    return ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("ZORA Settings", size=18, weight="bold"),
                ft.Container(height=5),
                info_row("ZORA Flag String", flagstring, label_width=140),
                info_row("ZORA Seed", seed, label_width=140),
                ft.Container(height=10),
                ft.Text("Enabled Flags:", weight="w500", size=14),
                ft.Text(enabled_text, selectable=True),
                ft.Container(height=10),
                ft.Text("Disabled Flags:", weight="w500", size=14),
                ft.Text(disabled_text, selectable=True)
            ], spacing=5),
            padding=10,
            margin=0,
            border=ft.border.all(2, ft.Colors.PURPLE_200),
            border_radius=10
        ),
        elevation=4
    )


def build_step1_container(choose_vanilla_button, choose_randomized_button, choose_generate_vanilla_button, gen_flagstring_input, gen_seed_input, gen_random_seed_button, generate_rom_button, platform: str = "web") -> ft.Column:
    """Build Step 1: Upload Base ROM section.

    Args:
        platform: Platform type - "windows", "macos", or "web"
    """

    # Panel A: Select Vanilla ROM
    vanilla_panel = ft.Container(
        content=ft.Column([
            ft.Text("Option A: Select Vanilla ROM from disk", weight="bold"),
            choose_vanilla_button
        ], spacing=10),
        padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
        border=ft.border.all(2, ft.Colors.BLUE_200),
        border_radius=10,
        expand=True
    )

    # Panel B: Select Randomized ROM
    randomized_panel = ft.Container(
        content=ft.Column([
            ft.Text("Option B: Select a ROM that was already randomized using Zelda Randomizer", weight="bold"),
            choose_randomized_button
        ], spacing=10),
        padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
        border=ft.border.all(2, ft.Colors.PURPLE_200),
        border_radius=10,
        expand=True
    )

    # Panel C: Generate ROM with Zelda Randomizer
    # Only enabled for Windows platform
    is_windows = platform == "windows"

    # Wrap seed input and random seed button together
    gen_seed_with_button = ft.Row(
        [gen_seed_input, gen_random_seed_button],
        spacing=10,
        tight=True
    )

    generate_panel_content = ft.Column([
        ft.Text("Option C: Generate a new Base ROM using Zelda Randomizer", weight="bold"),
        choose_generate_vanilla_button,
        ft.Row([gen_flagstring_input, gen_seed_with_button], spacing=20),
        generate_rom_button
    ], spacing=10)

    # Add platform restriction note if not Windows
    if not is_windows:
        generate_panel_content.controls.insert(1, ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.ORANGE_700),
                ft.Text(
                    "Integration with Zelda Randomizer is only available in the Windows version",
                    size=12,
                    color=ft.Colors.ORANGE_700,
                    italic=True
                )
            ], spacing=5),
            padding=ft.padding.only(top=5, bottom=5)
        ))

    generate_panel = ft.Container(
        content=generate_panel_content,
        padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
        border=ft.border.all(2, ft.Colors.GREEN_200),
        border_radius=10,
        disabled=not is_windows,
        opacity=1.0 if is_windows else 0.5
    )

    # Wrap generate_panel to match width of the row above
    generate_panel_row = ft.Container(
        content=generate_panel,
        expand=True
    )

    return ft.Column([
        ft.Text("Step 1: Select Base ROM", size=20, weight="bold"),
        ft.Row([vanilla_panel, randomized_panel], spacing=15),
        generate_panel_row
    ], spacing=15)


def build_step2_container(
    flag_checkbox_rows: dict,
    flagstring_input: ft.TextField,
    seed_input: ft.TextField,
    random_seed_button: ft.ElevatedButton,
    on_randomize: Callable
) -> ft.Container:
    """Build Step 2: Configure Flags & Seed section."""
    # Wrap seed input and button together
    seed_with_button = ft.Row(
        [seed_input, random_seed_button],
        spacing=10,
        tight=True
    )

    flag_seed_row = ft.Row(
        [flagstring_input, seed_with_button],
        spacing=20,
        wrap=True
    )

    randomize_button = ft.ElevatedButton("Randomize", on_click=on_randomize)

    # Build list of checkbox row controls and split into two columns
    checkbox_controls = list(flag_checkbox_rows.values())
    mid = (len(checkbox_controls) + 1) // 2
    left_checkboxes = checkbox_controls[:mid]
    right_checkboxes = checkbox_controls[mid:]

    checkbox_row = ft.Row([
        ft.Column(left_checkboxes, spacing=10, expand=True),
        ft.Column(right_checkboxes, spacing=10, expand=True)
    ], spacing=20)

    content = ft.Column([
        ft.Text("Step 2: Configure ZORA Flags and Seed Number", size=20, weight="bold"),
        ft.Container(height=5),
        flag_seed_row,
        ft.Divider(),
        checkbox_row,
        ft.Container(randomize_button, alignment=ft.alignment.center, padding=10)
    ], spacing=10)

    return ft.Container(
        content=content,
        padding=20,
        border=ft.border.all(2, ft.Colors.PURPLE_200),
        border_radius=10,
        margin=10,
        disabled=True,
        opacity=0.4
    )


def build_step3_container(
    randomized_rom_data: bytes,
    output_filename: str,
    flagstring: str,
    seed: str,
    code: str,
    platform: str,
    on_download: Callable
) -> ft.Container:
    """Build Step 3: Download Randomized ROM section.

    Args:
        randomized_rom_data: The randomized ROM bytes
        output_filename: Name of the output file
        flagstring: The ZORA flagstring used
        seed: The seed used
        code: The ROM code
        platform: Platform type - "windows", "macos", or "web"
        on_download: Download button click handler
    """
    download_button = ft.ElevatedButton(
        "Download Randomized ROM",
        icon=ft.Icons.DOWNLOAD,
        on_click=on_download
    )

    content = ft.Column([
        ft.Text("Step 3: Download Randomized ROM", size=20, weight="bold"),
        ft.Container(height=10),
        ft.Row([
            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=40),
            ft.Text("Randomization Complete!", size=16, weight="bold", color=ft.Colors.GREEN)
        ], spacing=10),
        ft.Container(height=10),
        info_row("Output File", output_filename, label_width=150, value_width=400),
        info_row("ZORA Flag String", flagstring, label_width=150, value_width=400),
        info_row("ZORA Seed", seed, label_width=150),
        info_row("ZORA Code", code, label_width=150),
        info_row("ROM Size", f"{len(randomized_rom_data) / 1024:.1f} KB", label_width=150),
        ft.Container(height=15),
        download_button
    ], spacing=5)

    return ft.Container(
        content=content,
        padding=20,
        border=ft.border.all(2, ft.Colors.GREEN_200),
        border_radius=10,
        margin=10
    )


def build_flag_checkboxes(flag_state: FlagState, on_change_callback) -> tuple[dict, dict]:
    """Build flag checkboxes and checkbox rows from FlagsEnum.

    Args:
        flag_state: FlagState instance containing complex_flags list
        on_change_callback: Callback function for checkbox changes (flag_key, value)

    Returns:
        tuple: (flag_checkboxes dict, flag_checkbox_rows dict)
    """
    flag_checkboxes = {}
    flag_checkbox_rows = {}

    for flag in FlagsEnum:
        if flag.value not in flag_state.complex_flags:
            checkbox = ft.Checkbox(
                label=flag.display_name,
                value=False,
                on_change=lambda e, key=flag.value: on_change_callback(key, e.control.value)
            )
            flag_checkboxes[flag.value] = checkbox

            # Create row with checkbox and help icon
            flag_checkbox_rows[flag.value] = ft.Row([
                checkbox,
                ft.IconButton(
                    icon=ft.Icons.HELP_OUTLINE,
                    icon_size=16,
                    tooltip=flag.help_text
                )
            ], spacing=0)

    return flag_checkboxes, flag_checkbox_rows


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def build_header(on_view_known_issues) -> ft.Container:
    """Build the application header with logo and title.

    Args:
        on_view_known_issues: Callback function to navigate to known issues page
    """
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Image(
                    src="zora.png",
                    width=96,
                    height=96,
                    fit=ft.ImageFit.CONTAIN
                ),
                ft.Column([
                    ft.Text(
                        "Zelda One Randomizer Add-Ons (ZORA) beta v0.1",
                        size=28,
                        weight="bold",
                        color=ft.Colors.BLUE_900
                    ),
                    ft.Container(height=5),
                    ft.Text(
                        spans=[
                            ft.TextSpan("ZORA is an add-on randomizer for "),
                            ft.TextSpan(
                                "Zelda Randomizer",
                                style=ft.TextStyle(color=ft.Colors.BLUE_700),
                                url="https://sites.google.com/site/zeldarandomizer/"
                            ),
                            ft.TextSpan(
                                " introducing several new features. "
                                "It works by re-randomizing a ROM that has already "
                                "been randomized using the original Zelda Randomizer. "
                                "It can also randomize an unrandomized (vanilla) Legend of Zelda ROM."
                            )
                        ],
                        size=14,
                        width=700
                    ),
                    ft.Container(height=8),
                    ft.Column([
                        ft.Text(
                            spans=[
                                ft.TextSpan(
                                    "WARNING: ",
                                    style=ft.TextStyle(weight=ft.FontWeight.BOLD)
                                ),
                                ft.TextSpan(
                                    "As of October 2025, ZORA is still an experimental product in early testing. "
                                    "While everyone is welcomed and encouraged to try it out, please be aware that "
                                    "any seeds you generate may contain bugs, unexpected glitches, softlocks, "
                                    "and may be completely unbeatable. Please proceed at your own risk! "
                                )
                            ],
                            size=13,
                            color=ft.Colors.RED_800,
                            width=700
                        ),
                        ft.TextButton(
                            "Please click here to view the Known Issues & Bugs page.",
                            on_click=on_view_known_issues,
                            style=ft.ButtonStyle(
                                padding=0,
                                color=ft.Colors.WHITE
                            )
                        )
                    ], spacing=5)
                ], spacing=0)
            ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=20, thickness=2)
        ], spacing=10),
        padding=ft.padding.only(bottom=10)
    )


def main(page: ft.Page, platform: str = "web") -> None:
    """Main application entry point.

    Args:
        page: Flet page object
        platform: Platform type - "windows", "macos", or "web"
    """
    page.title = "ZORA (Zelda One Randomizer Add-ons) v0.01"
    page.scroll = "auto"
    page.padding = ft.padding.only(left=20, right=20, top=20, bottom=20)

    # Set window size and icon for desktop platforms
    if platform in ["windows", "macos"]:
        page.window.width = 1000
        page.window.height = 900
        page.window.icon = "zora.png"

    # State
    rom_info = RomInfo()
    flag_state = FlagState()
    file_card = None
    vanilla_rom_path = None
    randomized_rom_data = None
    randomized_rom_filename = None
    step3_container = None
    zora_settings_card = None
    known_issues_page = None
    main_content = None

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def on_view_known_issues(e) -> None:
        """Navigate to known issues page."""
        nonlocal known_issues_page, main_content

        # Hide main content
        main_content.visible = False
        main_content.update()

        # Build and show known issues page
        if not known_issues_page:
            known_issues_page = build_known_issues_page(page, on_back_to_main)
            page.add(known_issues_page)
        else:
            known_issues_page.visible = True
            known_issues_page.update()

        page.update()

    def on_back_to_main(e) -> None:
        """Navigate back to main page."""
        nonlocal known_issues_page, main_content

        # Hide known issues page
        if known_issues_page:
            known_issues_page.visible = False
            known_issues_page.update()

        # Show main content
        main_content.visible = True
        main_content.update()

        page.update()

    def update_flagstring() -> None:
        """Update flagstring input based on checkbox states."""
        flagstring_input.value = flag_state.to_flagstring()
        flagstring_input.update()

    def on_flagstring_changed(e) -> None:
        """Parse flagstring input and update checkboxes if valid."""
        if flag_state.from_flagstring(flagstring_input.value):
            # Update checkbox UI to match parsed state
            for flag_key, checkbox in flag_checkboxes.items():
                checkbox.value = flag_state.flags.get(flag_key, False)
                checkbox.update()

    def on_checkbox_changed(flag_key: str, value: bool) -> None:
        """Handle checkbox state changes."""
        flag_state.flags[flag_key] = value
        update_flagstring()

    def show_step1() -> None:
        """Show Step 1 UI."""
        step1_container.visible = True
        step1_container.update()

    def hide_step1() -> None:
        """Hide Step 1 UI."""
        step1_container.visible = False
        step1_container.update()

    def enable_step2() -> None:
        """Enable Step 2 UI."""
        step2_container.disabled = False
        step2_container.opacity = 1.0
        step2_container.update()

    def disable_step2() -> None:
        """Disable Step 2 UI."""
        step2_container.disabled = True
        step2_container.opacity = 0.4
        step2_container.update()

    def load_rom_and_show_card(disable_seed: bool = False) -> None:
        """Hide Step 1, show ROM info card, and initialize Step 2.

        Args:
            disable_seed: If True, disable seed input and random seed button
        """
        nonlocal file_card

        # Hide Step 1, show ROM info card
        hide_step1()

        if file_card:
            main_content.controls.remove(file_card)

        file_card = build_rom_info_card(rom_info, clear_rom)
        # Insert after header (index 0) and before step2 (which is at index 1 when step1 is hidden)
        main_content.controls.insert(1, file_card)
        main_content.update()

        # Initialize Step 2 with ROM data
        seed_input.value = rom_info.seed

        if disable_seed:
            seed_input.disabled = True
            random_seed_button.disabled = True
            seed_input.update()
            random_seed_button.update()

        update_flagstring()
        enable_step2()

    def clear_rom(e) -> None:
        """Remove ROM and reset UI to initial state."""
        nonlocal file_card, vanilla_rom_path, zora_settings_card, step3_container

        if file_card:
            main_content.controls.remove(file_card)
            file_card = None
            rom_info.clear()
            vanilla_rom_path = None

            # Remove ZORA settings card if it exists
            if zora_settings_card:
                page.controls.remove(zora_settings_card)
                zora_settings_card = None

            # Remove Step 3 if it exists
            if step3_container:
                page.controls.remove(step3_container)
                step3_container = None

            # Reset generate vanilla button text
            choose_generate_vanilla_button.text = "Choose Vanilla ROM"
            choose_generate_vanilla_button.update()

            # Re-enable seed input and random seed button
            seed_input.disabled = False
            random_seed_button.disabled = False
            seed_input.update()
            random_seed_button.update()

            # Make sure step 2 is visible (it gets hidden when randomizing)
            step2_container.visible = True

            show_step1()
            disable_step2()
            page.update()

    def create_download_handler(rom_data: bytes, filename: str) -> Callable:
        """Create a download handler for the given ROM data.

        Args:
            rom_data: The ROM data bytes to download
            filename: The filename for the download

        Returns:
            callable: Event handler for download button
        """
        def on_download_rom(e) -> None:
            """Handle download button click - triggers browser download"""
            if platform == "web":
                try:
                    # Copy file to assets/downloads directory so it can be accessed
                    assets_download_dir = Path("assets") / "downloads"
                    assets_download_dir.mkdir(parents=True, exist_ok=True)

                    dest_path = assets_download_dir / filename

                    # Write the ROM data to the assets/downloads directory
                    with open(dest_path, 'wb') as f:
                        f.write(rom_data)

                    # Use the FastAPI download endpoint which sets proper headers
                    download_url = f"/download/{filename}"
                    page.launch_url(download_url)

                    # Show success message
                    page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Downloading {filename}..."),
                        bgcolor=ft.Colors.GREEN
                    )
                    page.snack_bar.open = True
                    page.update()

                except Exception as ex:
                    show_error_dialog(page, "Download Error", f"Failed to prepare download:\n\n{str(ex)}")
            else:
                # For desktop (macOS/Windows), use file picker to save
                def on_save_result(e: ft.FilePickerResultEvent) -> None:
                    if e.path:
                        try:
                            with open(e.path, 'wb') as f:
                                f.write(rom_data)
                            show_snackbar(page, f"ROM saved successfully to:\n{e.path}")
                        except Exception as ex:
                            show_snackbar(page, f"Error saving file: {str(ex)}")

                save_file_picker = ft.FilePicker(on_result=on_save_result)
                page.overlay.append(save_file_picker)
                page.update()
                # Remove .nes extension from filename since save_file will add it
                filename_without_ext = filename.replace('.nes', '')
                save_file_picker.save_file(
                    file_name=filename_without_ext,
                    allowed_extensions=["nes"]
                )

        return on_download_rom

    def process_vanilla_rom(file_info, filepath) -> None:
        """Process a vanilla ROM file (after upload if needed)."""
        nonlocal file_card

        filename = file_info.name

        # Read ROM data from filepath
        with open(filepath, 'rb') as f:
            rom_data = f.read()

        # Validate that this is a vanilla ROM
        if not is_vanilla_rom_data(rom_data):
            show_error_dialog(page, "Error", "This doesn't appear to be a vanilla Legend of Zelda ROM")
            return

        # Load ROM info for display
        rom_info.filename = filepath if filepath else filename
        rom_info.rom_type = "vanilla"
        rom_info.flagstring = ""
        rom_info.seed = ""

        # Vanilla ROMs don't have a code (they have 0xFF bytes), which is expected
        try:
            rom_info.code = extract_code_from_rom_data(rom_data)
        except (ValueError, KeyError):
            rom_info.code = "n/a"

        flag_state.seed = rom_info.seed
        load_rom_and_show_card(disable_seed=False)

    def on_vanilla_file_picked(e: ft.FilePickerResultEvent) -> None:
        """Handle vanilla ROM file selection (Option A)."""
        if not e.files:
            return

        file_info = e.files[0]

        if file_info.path:
            # Desktop platform - process directly
            process_vanilla_rom(file_info, file_info.path)
        else:
            # Web platform - trigger upload first
            upload_state['vanilla']['file_info'] = file_info
            upload_state['vanilla']['uploading'] = True

            upload_list = [
                ft.FilePickerUploadFile(
                    file_info.name,
                    upload_url=page.get_upload_url(file_info.name, 600)
                )
            ]
            vanilla_file_picker.upload(upload_list)

    def process_randomized_rom(file_info, filepath) -> None:
        """Process a randomized ROM file (after upload if needed)."""
        nonlocal file_card

        filename = file_info.name

        # Read ROM data from filepath
        with open(filepath, 'rb') as f:
            rom_data = f.read()

        # Load ROM info for display
        rom_info.filename = filepath if filepath else filename
        rom_info.rom_type = "randomized"

        # Parse filename for seed and flagstring
        try:
            rom_info.flagstring, rom_info.seed = parse_filename_for_flag_and_seed(filename)
        except ValueError as ex:
            show_error_dialog(page, "Invalid Filename", str(ex))
            return

        # Validate that this is a randomized ROM by trying to extract the code
        try:
            rom_info.code = extract_code_from_rom_data(rom_data)
        except Exception:
            show_error_dialog(page, "Error", "This does not appear to be a ROM randomized using Zelda Randomizer")
            return

        flag_state.seed = rom_info.seed
        load_rom_and_show_card(disable_seed=True)

    def on_randomized_file_picked(e: ft.FilePickerResultEvent) -> None:
        """Handle randomized ROM file selection (Option B)."""
        if not e.files:
            return

        file_info = e.files[0]

        if file_info.path:
            # Desktop platform - process directly
            process_randomized_rom(file_info, file_info.path)
        else:
            # Web platform - trigger upload first
            upload_state['randomized']['file_info'] = file_info
            upload_state['randomized']['uploading'] = True

            upload_list = [
                ft.FilePickerUploadFile(
                    file_info.name,
                    upload_url=page.get_upload_url(file_info.name, 600)
                )
            ]
            randomized_file_picker.upload(upload_list)

    def on_generate_vanilla_file_picked(e: ft.FilePickerResultEvent) -> None:
        """Handle vanilla ROM file selection for Option C."""
        nonlocal vanilla_rom_path

        if not e.files:
            return

        vanilla_rom_path = e.files[0].path
        choose_generate_vanilla_button.text = f"Vanilla ROM: {os.path.basename(vanilla_rom_path)}"
        choose_generate_vanilla_button.update()
        update_generate_button_state()

    def on_generate_rom(e) -> None:
        """Handle generate ROM button click."""
        nonlocal file_card

        print("Generate ROM button clicked!")  # Debug
        print(f"Vanilla ROM path: {vanilla_rom_path}")  # Debug
        print(f"Flagstring: {gen_flagstring_input.value}")  # Debug
        print(f"Seed: {gen_seed_input.value}")  # Debug

        if not vanilla_rom_path:
            show_snackbar(page, "Please select a vanilla ROM first")
            return

        if not gen_flagstring_input.value or not gen_seed_input.value:
            show_snackbar(page, "Please enter both flagstring and seed number")
            return

        # Validate the vanilla ROM
        try:
            if not is_vanilla_rom(vanilla_rom_path):
                show_error_dialog(page, "Invalid ROM", "The selected file does not appear to be a vanilla Legend of Zelda ROM.")
                return
        except Exception as ex:
            show_error_dialog(page, "Error", f"Unable to read the selected ROM file:\n\n{str(ex)}")
            return

        # Create zrinterface.txt file in temp directory
        temp_dir = tempfile.gettempdir()
        interface_file = os.path.join(temp_dir, "zrinterface.txt")

        try:
            with open(interface_file, 'w') as f:
                f.write(f"{vanilla_rom_path}\n")
                f.write(f"{gen_flagstring_input.value}\n")
                f.write(f"{gen_seed_input.value}\n")
        except Exception as ex:
            show_error_dialog(page, "Error", f"Failed to create interface file:\n\n{str(ex)}")
            return

        # Show progress message
        show_snackbar(page, "Launching Zelda Randomizer interface...")

        # Call zrinterface to generate the ROM
        try:
            # Call zrinterface.main() which will:
            # 1. Read the zrinterface.txt file
            # 2. Write ZeldaMessage.tmp for zrinterface.exe
            # 3. Launch zrinterface.exe to automate Zelda Randomizer
            success = zrinterface.main()

            if not success:
                show_error_dialog(
                    page,
                    "Zelda Randomizer Interface Error",
                    "Failed to interface with Zelda Randomizer.\n\n"
                    "Please ensure:\n"
                    "1. Zelda Randomizer 3.5.20 is running\n"
                    "2. The window is open and visible\n"
                    "3. zrinterface.exe is in the windows/ directory"
                )
                return

            # The randomizer generates a ROM in the same directory as the vanilla ROM
            # Zelda Randomizer naming: <original_basename>_<seed>_<flagstring>.nes
            rom_dir = os.path.dirname(vanilla_rom_path)
            vanilla_basename = os.path.splitext(os.path.basename(vanilla_rom_path))[0]
            generated_filename = os.path.join(
                rom_dir,
                f"{vanilla_basename}_{gen_seed_input.value}_{gen_flagstring_input.value}.nes"
            )

            # Wait a moment for file to be written
            import time
            time.sleep(0.5)

            # Check if the ROM was generated
            if not os.path.exists(generated_filename):
                show_error_dialog(
                    page,
                    "ROM Not Found",
                    f"The randomized ROM was not found at the expected location:\n\n{generated_filename}\n\n"
                    "Please check if Zelda Randomizer successfully generated the ROM."
                )
                return

            # Load the generated ROM info
            rom_info.filename = generated_filename
            rom_info.rom_type = "randomized"
            rom_info.flagstring = gen_flagstring_input.value
            rom_info.seed = gen_seed_input.value

            try:
                rom_info.code = extract_base_rom_code(generated_filename)
            except Exception as ex:
                show_error_dialog(
                    page,
                    "Error Reading ROM",
                    f"The ROM was generated but could not be read:\n\n{str(ex)}"
                )
                return

            flag_state.seed = rom_info.seed

            # Update UI
            load_rom_and_show_card(disable_seed=True)
            show_snackbar(page, f"Successfully generated ROM: {os.path.basename(generated_filename)}")

        except FileNotFoundError as e:
            show_error_dialog(
                page,
                "File Not Found",
                f"A required file was not found:\n\n{str(e)}\n\n"
                "Make sure zrinterface.exe is in the windows/ directory."
            )
        except Exception as e:
            show_error_dialog(
                page,
                "Error",
                f"An error occurred while generating the ROM:\n\n{str(e)}"
            )

    def on_randomize(e) -> None:
        """Handle randomize button click."""
        try:
            # Validate that seed is provided
            if not seed_input.value or not seed_input.value.strip():
                show_error_dialog(page, "Seed Required", "Please enter a seed number before randomizing.")
                return

            # Read the base ROM file
            with open(rom_info.filename, 'rb') as f:
                rom_bytes = io.BytesIO(f.read())

            # Convert flag_state to Flags object for randomizer
            randomizer_flags = flag_state.to_randomizer_flags()

            # Get seed as integer
            seed = int(seed_input.value)

            # Run the randomizer
            randomizer = Z1Randomizer(rom_bytes, seed, randomizer_flags)
            patch = randomizer.GetPatch()

            # Apply patch to ROM
            rom_bytes.seek(0)
            rom_data = bytearray(rom_bytes.read())

            for address in patch.GetAddresses():
                patch_data = patch.GetData(address)
                for i, byte in enumerate(patch_data):
                    rom_data[address + i] = byte

            # Store the randomized ROM data
            nonlocal randomized_rom_data, randomized_rom_filename, step3_container, zora_settings_card
            randomized_rom_data = bytes(rom_data)
            base_name = os.path.splitext(os.path.basename(rom_info.filename))[0]

            # Generate filename based on ROM type
            # For vanilla ROM: [base]_[ZORA seed]_[ZORA flags].nes
            # For randomized ROM (B/C): [base]_[ZORA flags].nes (just append ZORA flags)
            if rom_info.rom_type == "vanilla":
                randomized_rom_filename = f"{base_name}_{seed_input.value}_{flagstring_input.value}.nes"
            else:  # randomized
                randomized_rom_filename = f"{base_name}_{flagstring_input.value}.nes"

            # Extract output ROM code
            output_rom_code = extract_code_from_rom_data(randomized_rom_data)

            # Log randomization details
            log.info("=" * 70)
            log.info("RANDOMIZATION COMPLETE")
            log.info("=" * 70)
            log.info("INPUT ROM:")
            log.info(f"  Filename: {rom_info.filename}")
            if rom_info.rom_type == "vanilla":
                log.info(f"  Type: Vanilla")
                log.info(f"  Seed: n/a")
                log.info(f"  Flags: n/a")
            else:
                log.info(f"  Type: Randomized (base ROM)")
                log.info(f"  Seed: {rom_info.seed}")
                log.info(f"  Flags: {rom_info.flagstring}")
            log.info(f"  Code: {rom_info.code}")
            log.info("")
            log.info("OUTPUT ROM:")
            log.info(f"  Filename: {randomized_rom_filename}")
            log.info(f"  ZORA Seed: {seed_input.value}")
            log.info(f"  ZORA Flags: {flagstring_input.value}")
            log.info(f"  Code: {output_rom_code}")
            log.info("=" * 70)

            # Hide Step 2 and show ZORA settings card
            step2_container.visible = False
            step2_container.update()

            # Create and show ZORA settings card
            zora_settings_card = build_zora_settings_card(
                flagstring_input.value,
                seed_input.value,
                flag_state
            )
            page.add(zora_settings_card)
            page.update()

            # Show Step 3
            rom_code = extract_code_from_rom_data(randomized_rom_data)
            download_handler = create_download_handler(randomized_rom_data, randomized_rom_filename)

            step3_container = build_step3_container(
                randomized_rom_data,
                randomized_rom_filename,
                flagstring_input.value,
                seed_input.value,
                rom_code,
                platform,
                download_handler
            )
            page.add(step3_container)
            page.update()

        except ValueError as ex:
            # Handle validation errors (like progressive items + extra candles, or power bracelet blocks + any roads)
            print(f"\n!!! VALIDATION ERROR !!!")
            print(f"Error type: {type(ex).__name__}")
            print(f"Error message: {str(ex)}")
            print("!!!\n")

            if "is not compatible" in str(ex):
                # This covers both "Progressive Items is not compatible" and "Extra Power Bracelet Blocks is not compatible"
                show_error_dialog(
                    page,
                    "Incompatible Flag Combination",
                    str(ex)
                )
            else:
                show_error_dialog(page, "Validation Error", f"An error occurred during validation:\n\n{str(ex)}")

        except IndexError as ex:
            # This usually indicates a Race ROM, which has a different format
            print(f"\n!!! RANDOMIZATION ERROR !!!")
            print(f"Error type: {type(ex).__name__}")
            print(f"Error message: {str(ex)}")
            import traceback
            print("Full traceback:")
            traceback.print_exc()
            print("!!!\n")

            # Check if this looks like a Race ROM error
            if "list index out of range" in str(ex):
                show_error_dialog(
                    page, "Randomization Error",
                    "This ROM appears to be a Zelda Randomizer Race ROM, which is not supported.\n\n"
                    "ZORA can only randomize:\n"
                    "• Vanilla Legend of Zelda ROMs\n"
                    "• ROMs from Zelda Randomizer with the Race ROM flag turned off."
                )
            else:
                show_error_dialog(page, "Randomization Error", f"An error occurred while reading the ROM:\n\n{str(ex)}")

        except Exception as ex:
            print(f"\n!!! RANDOMIZATION ERROR !!!")
            print(f"Error type: {type(ex).__name__}")
            print(f"Error message: {str(ex)}")
            import traceback
            print("Full traceback:")
            traceback.print_exc()
            print("!!!\n")
            show_error_dialog(page, "Randomization Error", f"An error occurred while randomizing the ROM:\n\n{str(ex)}")

    # ========================================================================
    # UI Components
    # ========================================================================

    # Upload state tracking
    upload_state: dict = {
        'vanilla': {'uploading': False, 'file_info': None, 'uploaded_path': ''},
        'randomized': {'uploading': False, 'file_info': None, 'uploaded_path': ''}
    }

    def on_vanilla_upload_progress(e: ft.FilePickerUploadEvent) -> None:
        """Track vanilla ROM upload progress."""
        if e.error:
            show_error_dialog(page, "Upload Error", f"Upload failed: {e.error}")
            return

        if e.progress == 1.0:
            # Upload complete - process the file
            upload_state['vanilla']['uploading'] = False
            # Get absolute path to uploaded file
            upload_state['vanilla']['uploaded_path'] = os.path.abspath(f"uploads/{e.file_name}")

            # Wait a moment for file to be fully written
            import time
            time.sleep(0.1)

            if not os.path.exists(upload_state['vanilla']['uploaded_path']):
                show_error_dialog(page, "Upload Error", f"File was not uploaded successfully. Expected at: {upload_state['vanilla']['uploaded_path']}")
                return

            # Now process the uploaded file
            process_vanilla_rom(upload_state['vanilla']['file_info'], upload_state['vanilla']['uploaded_path'])

    def on_randomized_upload_progress(e: ft.FilePickerUploadEvent) -> None:
        """Track randomized ROM upload progress."""
        if e.progress == 1.0:
            # Upload complete - process the file
            upload_state['randomized']['uploading'] = False
            # Get absolute path to uploaded file
            upload_state['randomized']['uploaded_path'] = os.path.abspath(f"uploads/{e.file_name}")

            # Wait a moment for file to be fully written, then verify it exists
            import time
            time.sleep(0.1)

            if not os.path.exists(upload_state['randomized']['uploaded_path']):
                show_error_dialog(page, "Upload Error", f"File was not uploaded successfully. Expected at: {upload_state['randomized']['uploaded_path']}")
                return

            # Now process the uploaded file
            process_randomized_rom(upload_state['randomized']['file_info'], upload_state['randomized']['uploaded_path'])

    # File pickers with upload handlers
    vanilla_file_picker = ft.FilePicker(on_result=on_vanilla_file_picked, on_upload=on_vanilla_upload_progress)
    randomized_file_picker = ft.FilePicker(on_result=on_randomized_file_picked, on_upload=on_randomized_upload_progress)
    generate_vanilla_file_picker = ft.FilePicker(on_result=on_generate_vanilla_file_picked)
    page.overlay.append(vanilla_file_picker)
    page.overlay.append(randomized_file_picker)
    page.overlay.append(generate_vanilla_file_picker)
    page.update()

    # Step 1: Create buttons for file picking
    def on_choose_vanilla_click(e) -> None:
        vanilla_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )

    def on_choose_randomized_click(e) -> None:
        randomized_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )

    def on_choose_generate_vanilla_click(e) -> None:
        generate_vanilla_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )

    choose_vanilla_button = ft.ElevatedButton(
        "Choose ROM",
        on_click=on_choose_vanilla_click
    )

    choose_randomized_button = ft.ElevatedButton(
        "Choose ROM",
        on_click=on_choose_randomized_click
    )

    choose_generate_vanilla_button = ft.ElevatedButton(
        "Choose Vanilla ROM",
        on_click=on_choose_generate_vanilla_click
    )

    # Step 1: Generate ROM inputs
    gen_flagstring_input = ft.TextField(
        label="Zelda Randomizer Flag String",
        hint_text="e.g., 5JOfkHFLCIuh7WxM4mIYp7TuCHxRYQdJcty",
        width=350
    )
    gen_seed_input = ft.TextField(
        label="Zelda Randomizer Seed Number",
        hint_text="e.g., 12345",
        width=300
    )

    def on_gen_random_seed_click(e) -> None:
        """Generate a random seed for Zelda Randomizer."""
        random_seed = random.randint(10000000, 99999999)
        gen_seed_input.value = str(random_seed)
        gen_seed_input.update()
        update_generate_button_state()

    gen_random_seed_button = ft.ElevatedButton(
        "Random Seed",
        on_click=on_gen_random_seed_click,
        icon=ft.Icons.SHUFFLE
    )

    # Create generate button
    generate_rom_button = ft.ElevatedButton(
        "Generate Base ROM with Zelda Randomizer",
        on_click=on_generate_rom,
        disabled=True  # Start disabled
    )

    def update_generate_button_state() -> None:
        """Enable/disable generate button based on form validation."""
        has_rom = vanilla_rom_path is not None
        has_flagstring = gen_flagstring_input.value and gen_flagstring_input.value.strip()
        has_seed = gen_seed_input.value and gen_seed_input.value.strip()

        generate_rom_button.disabled = not (has_rom and has_flagstring and has_seed)
        generate_rom_button.update()

    # Add onchange handlers to inputs
    def on_gen_input_changed(e) -> None:
        update_generate_button_state()

    gen_flagstring_input.on_change = on_gen_input_changed
    gen_seed_input.on_change = on_gen_input_changed

    # Step 1: Upload ROM
    step1_container = build_step1_container(
        choose_vanilla_button,
        choose_randomized_button,
        choose_generate_vanilla_button,
        gen_flagstring_input,
        gen_seed_input,
        gen_random_seed_button,
        generate_rom_button,
        platform
    )

    # Step 2: Flag checkboxes - dynamically create from FlagsEnum
    flag_checkboxes, flag_checkbox_rows = build_flag_checkboxes(flag_state, on_checkbox_changed)

    # Step 2: Inputs
    flagstring_input = ft.TextField(
        label="ZORA Flag String",
        value="",
        on_change=on_flagstring_changed,
        width=250
    )
    seed_input = ft.TextField(
        label="ZORA Seed Number",
        value="12345",
        width=200
    )

    def on_random_seed_click(e) -> None:
        """Generate a random seed between 10000000 and 99999999."""
        random_seed = random.randint(10000000, 99999999)
        seed_input.value = str(random_seed)
        seed_input.update()

    random_seed_button = ft.ElevatedButton(
        "Random Seed",
        on_click=on_random_seed_click,
        icon=ft.Icons.SHUFFLE
    )

    # Step 2: Container
    step2_container = build_step2_container(
        flag_checkbox_rows,
        flagstring_input,
        seed_input,
        random_seed_button,
        on_randomize
    )

    # Build header
    header = build_header(on_view_known_issues)

    # Build main content container
    main_content = ft.Column([
        header,
        step1_container,
        step2_container
    ], spacing=0)

    # Add to page
    page.add(main_content)
    page.update()
