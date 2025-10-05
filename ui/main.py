import flet as ft
import io
import os
import re
import tempfile
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logic.flags import FlagsEnum, Flags
from logic.randomizer import Z1Randomizer
from common.constants import CODE_ITEMS
from windows import zrinterface


# ============================================================================
# ROM UTILITIES
# ============================================================================

def generate_base_rom_with_randomizer(vanilla_rom_path: str, flagstring: str, seed: str) -> str:
    """Generate a base ROM using Zelda Randomizer.

    Args:
        vanilla_rom_path: Path to vanilla Zelda ROM
        flagstring: Randomizer flag string
        seed: Seed number for randomization

    Returns:
        str: Filename of generated base ROM
    """
    # TODO: Implement actual randomizer logic
    return f"zelda_randomized_{seed}_{flagstring}.nes"


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

    return ", ".join(items)


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


def is_vanilla_rom(filename: str) -> bool:
    try:
        with open(filename, 'rb') as f:
            f.seek(0xAFD4)
            return f.read(4) == b'\xff\xff\xff\xff'
    except Exception as e:
        return False

def parse_filename_for_flag_and_seed(filename: str) -> tuple[str, str]:
    """Extract flagstring and seed from ROM filename.

    Returns:
        tuple: (flagstring, seed)
    """
    name = os.path.splitext(filename)[0]
    parts = name.split("_")

    # Extract seed (first numeric part)
    seed = ""
    for part in parts:
        if part.isdigit():
            seed = part
            break

    # Extract flagstring (last alphanumeric non-digit part)
    flagstring = ""
    for part in reversed(parts):
        if re.fullmatch(r"[A-Za-z0-9]+", part) and not part.isdigit():
            flagstring = part
            break

    return flagstring, seed


# ============================================================================
# FLAG STATE MANAGEMENT
# ============================================================================

class FlagState:
    """Manages the state of randomizer flags."""

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
        # Mapping: octal value -> letter
        LETTER_MAP = ['B', 'C', 'D', 'F', 'G', 'H', 'K', 'L']

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
            letters.append(LETTER_MAP[octal_value])

        return ''.join(letters)

    def from_flagstring(self, flagstring: str) -> bool:
        """Parse a flagstring and update state.

        Returns:
            bool: True if valid flagstring, False otherwise
        """
        # Mapping: letter -> octal value
        VALID_LETTERS = {'B': 0, 'C': 1, 'D': 2, 'F': 3, 'G': 4, 'H': 5, 'K': 6, 'L': 7}

        s = flagstring.strip().upper()

        # Check if all characters are valid letters
        if not all(c in VALID_LETTERS for c in s):
            return False

        # Convert letters to binary string
        binary_str = ''
        for letter in s:
            octal_value = VALID_LETTERS[letter]
            binary_str += format(octal_value, '03b')

        # Apply to flags
        non_complex_flags = [f for f in FlagsEnum if f.value not in self.complex_flags]
        for i, flag in enumerate(non_complex_flags):
            if i < len(binary_str):
                self.flags[flag.value] = binary_str[i] == '1'

        return True


class BaseROM:
    """Represents a base ROM file (vanilla or randomized)."""

    def __init__(self, filepath: str, rom_type: str):
        """Initialize BaseROM.

        Args:
            filepath: Full path to the ROM file
            rom_type: Either 'vanilla' or 'randomized'
        """
        self.filepath = filepath
        self.rom_type = rom_type

    def get_full_filename(self) -> str:
        """Return the full filename including path."""
        return self.filepath

    def get_rom_type(self) -> str:
        """Return the ROM type (vanilla or randomized)."""
        return self.rom_type

    def get_flag_string(self) -> str:
        """Return the flag string if applicable.

        Extracts flag string from filename for randomized ROMs.
        Returns empty string for vanilla ROMs.
        """
        if self.rom_type == 'randomized':
            flagstring, _ = parse_filename_for_flag_and_seed(os.path.basename(self.filepath))
            return flagstring
        return ""

    def get_seed_number(self) -> str:
        """Return the seed number if applicable.

        Extracts seed number from filename for randomized ROMs.
        Returns empty string for vanilla ROMs.
        """
        if self.rom_type == 'randomized':
            _, seed = parse_filename_for_flag_and_seed(os.path.basename(self.filepath))
            return seed
        return ""

    def get_code(self) -> str:
        """Return the ROM code.

        Reads bytes at ROM addresses 0xAFD3, 0xAFD2, 0xAFD1, 0xAFD0
        and returns the item names as a space-separated string.
        """
        return extract_base_rom_code(self.filepath)


class RomInfo:
    """Stores information about the loaded ROM."""

    def __init__(self):
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""

    def clear(self):
        """Reset all ROM info."""
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""

    def load_from_file(self, filepath: str):
        """Load ROM info from a file path."""
        self.filename = os.path.basename(filepath)
        self.flagstring, self.seed = parse_filename_for_flag_and_seed(self.filename)
        self.code = extract_base_rom_code(filepath)


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

    def info_row(label: str, value: str):
        """Create a row with aligned label and value."""
        return ft.Row([
            ft.Container(
                ft.Text(f"{label}:", weight="w500"),
                width=120
            ),
            ft.Text(value, selectable=True)
        ], spacing=10)

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
            margin=0
        ),
        elevation=4
    )


def build_step1_container(vanilla_file_picker, randomized_file_picker, generate_vanilla_file_picker, choose_generate_vanilla_button, gen_flagstring_input, gen_seed_input, on_generate_rom, platform: str = "web") -> ft.Column:
    """Build Step 1: Upload Base ROM section.

    Args:
        platform: Platform type - "windows", "macos", or "web"
    """
    choose_vanilla_button = ft.ElevatedButton(
        "Choose ROM",
        on_click=lambda _: vanilla_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )
    )

    choose_randomized_button = ft.ElevatedButton(
        "Choose ROM",
        on_click=lambda _: randomized_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )
    )

    generate_rom_button = ft.ElevatedButton(
        "Generate Base ROM with Zelda Randomizer",
        on_click=on_generate_rom
    )

    # Panel A: Select Vanilla ROM
    vanilla_panel = ft.Container(
        content=ft.Column([
            ft.Text("Option A: Select Vanilla ROM", weight="bold"),
            choose_vanilla_button
        ], spacing=10),
        padding=15,
        border=ft.border.all(2, ft.Colors.BLUE_200),
        border_radius=10,
        expand=True
    )

    # Panel B: Select Randomized ROM
    randomized_panel = ft.Container(
        content=ft.Column([
            ft.Text("Option B: Select Randomized ROM", weight="bold"),
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

    generate_panel_content = ft.Column([
        ft.Text("Option C: Generate Base ROM with Zelda Randomizer", weight="bold"),
        choose_generate_vanilla_button,
        ft.Row([gen_flagstring_input, gen_seed_input], spacing=20),
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

    return ft.Column([
        ft.Text("Step 1: Select Base ROM", size=20, weight="bold"),
        ft.Row([vanilla_panel, randomized_panel], spacing=15),
        generate_panel
    ], spacing=15)


def build_step2_container(
    flag_checkbox_rows: dict,
    flagstring_input: ft.TextField,
    seed_input: ft.TextField,
    on_randomize
) -> ft.Container:
    """Build Step 2: Configure Flags & Seed section."""
    flag_seed_row = ft.Row(
        [flagstring_input, seed_input],
        alignment="spaceBetween",
        spacing=20
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
        ft.Text("Step 2: Configure ZORA Flags and Seed", size=20, weight="bold"),
        ft.Container(height=5),
        flag_seed_row,
        ft.Divider(),
        checkbox_row,
        ft.Container(randomize_button, alignment=ft.alignment.center, padding=10)
    ], spacing=10)

    return ft.Container(
        content=content,
        padding=20,
        border=ft.border.all(1),
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
    on_download
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
    def info_row(label: str, value: str):
        """Create a row with aligned label and value."""
        return ft.Row([
            ft.Container(
                ft.Text(f"{label}:", weight="w500"),
                width=120
            ),
            ft.Text(value, selectable=True)
        ], spacing=10)

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
        info_row("Output File", output_filename),
        info_row("ZORA Flagstring", flagstring),
        info_row("Seed", seed),
        info_row("Code", code),
        info_row("ROM Size", f"{len(randomized_rom_data):,} bytes"),
        ft.Container(height=15),
        download_button
    ], spacing=5)

    return ft.Container(
        content=content,
        padding=20,
        border=ft.border.all(1),
        margin=10
    )


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main(page: ft.Page, platform: str = "web"):
    """Main application entry point.

    Args:
        page: Flet page object
        platform: Platform type - "windows", "macos", or "web"
    """
    page.title = "ZORA (Zelda One Randomizer Add-ons) v0.01"
    page.scroll = "hidden"
    page.padding = ft.padding.only(left=20, right=20, top=20, bottom=20)

    # State
    rom_info = RomInfo()
    flag_state = FlagState()
    file_card = None
    vanilla_rom_path = None
    randomized_rom_data = None
    randomized_rom_filename = None
    step3_container = None

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def update_flagstring():
        """Update flagstring input based on checkbox states."""
        flagstring_input.value = flag_state.to_flagstring()
        flagstring_input.update()

    def on_flagstring_changed(e):
        """Parse flagstring input and update checkboxes if valid."""
        if flag_state.from_flagstring(flagstring_input.value):
            # Update checkbox UI to match parsed state
            for flag_key, checkbox in flag_checkboxes.items():
                checkbox.value = flag_state.flags.get(flag_key, False)
                checkbox.update()

    def on_checkbox_changed(flag_key: str, value: bool):
        """Handle checkbox state changes."""
        flag_state.flags[flag_key] = value
        update_flagstring()

    def enable_step2():
        """Enable Step 2 UI."""
        step2_container.disabled = False
        step2_container.opacity = 1.0
        step2_container.update()

    def disable_step2():
        """Disable Step 2 UI."""
        step2_container.disabled = True
        step2_container.opacity = 0.4
        step2_container.update()

    def clear_rom(e):
        """Remove ROM and reset UI to initial state."""
        nonlocal file_card, vanilla_rom_path

        if file_card:
            page.controls.remove(file_card)
            file_card = None
            rom_info.clear()
            vanilla_rom_path = None

            # Reset generate vanilla button text
            choose_generate_vanilla_button.text = "Choose Vanilla ROM"
            choose_generate_vanilla_button.update()

            # Re-enable seed input
            seed_input.disabled = False
            seed_input.update()

            step1_container.visible = True
            step1_container.update()

            disable_step2()
            page.update()

    def on_vanilla_file_picked(e: ft.FilePickerResultEvent):
        """Handle vanilla ROM file selection (Option A)."""
        nonlocal file_card

        if not e.files:
            return

        filepath = e.files[0].path

        # Validate that this is a vanilla ROM
        if not is_vanilla_rom(filepath):
            def close_dlg(e):
                page.close(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Error"),
                content=ft.Text("This doesn't appear to be a vanilla Legend of Zelda ROM"),
                actions=[
                    ft.TextButton("OK", on_click=close_dlg),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            page.open(dialog)
            return

        # Create BaseROM instance for vanilla ROM
        base_rom = BaseROM(filepath, 'vanilla')

        # Load ROM info for display
        rom_info.filename = filepath
        rom_info.rom_type = "vanilla"
        rom_info.flagstring = base_rom.get_flag_string()
        rom_info.seed = base_rom.get_seed_number()

        # Vanilla ROMs don't have a code (they have 0xFF bytes), which is expected
        try:
            rom_info.code = base_rom.get_code()
        except (ValueError, KeyError):
            rom_info.code = "n/a"

        flag_state.seed = rom_info.seed

        # Hide Step 1, show ROM info card
        step1_container.visible = False
        step1_container.update()

        if file_card:
            page.controls.remove(file_card)

        file_card = build_rom_info_card(rom_info, clear_rom)
        page.controls.insert(1, file_card)
        page.update()

        # Initialize Step 2 with ROM data
        seed_input.value = rom_info.seed
        update_flagstring()
        enable_step2()

    def on_randomized_file_picked(e: ft.FilePickerResultEvent):
        """Handle randomized ROM file selection (Option B)."""
        nonlocal file_card

        if not e.files:
            return

        filepath = e.files[0].path

        # Create BaseROM instance for randomized ROM
        base_rom = BaseROM(filepath, 'randomized')

        # Load ROM info for display
        rom_info.filename = filepath
        rom_info.rom_type = "randomized"
        rom_info.flagstring = base_rom.get_flag_string()
        rom_info.seed = base_rom.get_seed_number()

        # Validate that this is a randomized ROM by trying to extract the code
        try:
            rom_info.code = base_rom.get_code()
        except Exception:
            def close_dlg(e):
                page.close(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Error"),
                content=ft.Text("This does not appear to be a ROM randomized using Zelda Randomizer"),
                actions=[
                    ft.TextButton("OK", on_click=close_dlg),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            page.open(dialog)
            return

        flag_state.seed = rom_info.seed

        # Hide Step 1, show ROM info card
        step1_container.visible = False
        step1_container.update()

        if file_card:
            page.controls.remove(file_card)

        file_card = build_rom_info_card(rom_info, clear_rom)
        page.controls.insert(1, file_card)
        page.update()

        # Initialize Step 2 with ROM data
        seed_input.value = rom_info.seed
        seed_input.disabled = True  # Disable seed input for randomized ROMs
        seed_input.update()
        update_flagstring()
        enable_step2()

    def on_generate_vanilla_file_picked(e: ft.FilePickerResultEvent):
        """Handle vanilla ROM file selection for Option C."""
        nonlocal vanilla_rom_path

        if not e.files:
            return

        vanilla_rom_path = e.files[0].path
        choose_generate_vanilla_button.text = f"Vanilla ROM: {os.path.basename(vanilla_rom_path)}"
        choose_generate_vanilla_button.update()

    def on_generate_rom(e):
        """Handle generate ROM button click."""
        nonlocal file_card

        if not vanilla_rom_path:
            page.snack_bar = ft.SnackBar(
                ft.Text("Please select a vanilla ROM first"),
                open=True
            )
            page.snack_bar.open = True
            page.update()
            return

        if not gen_flagstring_input.value or not gen_seed_input.value:
            page.snack_bar = ft.SnackBar(
                ft.Text("Please enter both flagstring and seed number"),
                open=True
            )
            page.snack_bar.open = True
            page.update()
            return

        # Create zrinterface.txt file in temp directory
        temp_dir = tempfile.gettempdir()
        interface_file = os.path.join(temp_dir, "zrinterface.txt")

        with open(interface_file, 'w') as f:
            f.write(f"{vanilla_rom_path}\n")
            f.write(f"{gen_flagstring_input.value}\n")
            f.write(f"{gen_seed_input.value}\n")

        # Call zrinterface to generate the ROM
        try:
            zrinterface.main()

            # Generate the base ROM
            generated_filename = generate_base_rom_with_randomizer(
                vanilla_rom_path,
                gen_flagstring_input.value,
                gen_seed_input.value
            )

            # Load the generated ROM as if it was picked
            rom_info.filename = generated_filename
            rom_info.rom_type = "randomized"
            rom_info.flagstring = gen_flagstring_input.value
            rom_info.seed = gen_seed_input.value
            rom_info.code = extract_base_rom_code(generated_filename)
            flag_state.seed = rom_info.seed

            # Hide Step 1, show ROM info card
            step1_container.visible = False
            step1_container.update()

            if file_card:
                page.controls.remove(file_card)

            file_card = build_rom_info_card(rom_info, clear_rom)
            page.controls.insert(1, file_card)
            page.update()

            # Initialize Step 2 with ROM data
            seed_input.value = rom_info.seed
            seed_input.disabled = True  # Disable seed input for generated ROMs
            seed_input.update()
            update_flagstring()
            enable_step2()

        except FileNotFoundError as e:
            def close_dlg(e):
                page.close(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Error Generating ROM"),
                content=ft.Text(f"Failed to generate or find the randomized ROM file.\n\nError: {str(e)}"),
                actions=[
                    ft.TextButton("OK", on_click=close_dlg),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dialog)
        except Exception as e:
            def close_dlg(e):
                page.close(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Error"),
                content=ft.Text(f"An error occurred while generating the ROM:\n\n{str(e)}"),
                actions=[
                    ft.TextButton("OK", on_click=close_dlg),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dialog)

    def on_randomize(e):
        """Handle randomize button click."""
        try:
            # Read the base ROM file
            with open(rom_info.filename, 'rb') as f:
                rom_bytes = io.BytesIO(f.read())

            # Convert flag_state to Flags object for randomizer
            randomizer_flags = Flags()
            for flag_key, flag_value in flag_state.flags.items():
                if flag_value:  # Only set flags that are True
                    setattr(randomizer_flags, flag_key, True)

            # Get seed as integer
            seed = int(seed_input.value) if seed_input.value else 0

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
            nonlocal randomized_rom_data, randomized_rom_filename, step3_container
            randomized_rom_data = bytes(rom_data)
            base_name = os.path.splitext(os.path.basename(rom_info.filename))[0]
            randomized_rom_filename = f"{base_name}_zora_{flagstring_input.value}_{seed_input.value}.nes"

            # Disable Step 2
            step2_container.disabled = True
            step2_container.opacity = 0.4
            step2_container.update()

            # Show Step 3
            def on_download_rom(e):
                """Handle download button click."""
                if platform == "web":
                    # For web, trigger browser download
                    page.download(randomized_rom_data, randomized_rom_filename)
                else:
                    # For desktop (macOS/Windows), use file picker to save
                    def on_save_result(e: ft.FilePickerResultEvent):
                        if e.path:
                            try:
                                with open(e.path, 'wb') as f:
                                    f.write(randomized_rom_data)
                                page.snack_bar = ft.SnackBar(
                                    ft.Text(f"ROM saved successfully to:\n{e.path}"),
                                    open=True
                                )
                                page.snack_bar.open = True
                                page.update()
                            except Exception as ex:
                                page.snack_bar = ft.SnackBar(
                                    ft.Text(f"Error saving file: {str(ex)}"),
                                    open=True
                                )
                                page.snack_bar.open = True
                                page.update()

                    save_file_picker = ft.FilePicker(on_result=on_save_result)
                    page.overlay.append(save_file_picker)
                    page.update()
                    # Remove .nes extension from filename since save_file will add it
                    filename_without_ext = randomized_rom_filename.replace('.nes', '')
                    save_file_picker.save_file(
                        file_name=filename_without_ext,
                        allowed_extensions=["nes"]
                    )

            # Extract code from randomized ROM
            rom_code = "Unknown"
            try:
                # Read code from addresses 0xAFD0-0xAFD3 (with 0x10 NES header offset = 0xAFE0-0xAFE3)
                code_bytes = randomized_rom_data[0xAFE0:0xAFE4]
                rom_code = extract_code_from_bytes(code_bytes)
            except Exception:
                pass

            step3_container = build_step3_container(
                randomized_rom_data,
                randomized_rom_filename,
                flagstring_input.value,
                seed_input.value,
                rom_code,
                platform,
                on_download_rom
            )
            page.add(step3_container)
            page.update()

        except Exception as ex:
            def close_dlg(e):
                page.close(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Randomization Error"),
                content=ft.Text(f"An error occurred while randomizing the ROM:\n\n{str(ex)}"),
                actions=[
                    ft.TextButton("OK", on_click=close_dlg),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dialog)

    # ========================================================================
    # UI Components
    # ========================================================================

    # File pickers
    vanilla_file_picker = ft.FilePicker(on_result=on_vanilla_file_picked)
    randomized_file_picker = ft.FilePicker(on_result=on_randomized_file_picked)
    generate_vanilla_file_picker = ft.FilePicker(on_result=on_generate_vanilla_file_picked)
    page.overlay.append(vanilla_file_picker)
    page.overlay.append(randomized_file_picker)
    page.overlay.append(generate_vanilla_file_picker)

    # Step 1: Generate ROM inputs
    gen_flagstring_input = ft.TextField(
        label="Zelda Randomizer Flag String",
        hint_text="e.g., 5JOfkHFLCIuh7WxM4mIYp7TuCHxRYQdJcty",
        width=300
    )
    gen_seed_input = ft.TextField(
        label="Zelda Randomizer Seed Number",
        hint_text="e.g., 12345",
        width=300
    )
    choose_generate_vanilla_button = ft.ElevatedButton(
        "Choose Vanilla ROM",
        on_click=lambda _: generate_vanilla_file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["nes"]
        )
    )

    # Step 1: Upload ROM
    step1_container = build_step1_container(
        vanilla_file_picker,
        randomized_file_picker,
        generate_vanilla_file_picker,
        choose_generate_vanilla_button,
        gen_flagstring_input,
        gen_seed_input,
        on_generate_rom,
        platform
    )

    # Step 2: Flag checkboxes - dynamically create from FlagsEnum
    flag_checkboxes = {}
    flag_checkbox_rows = {}

    for flag in FlagsEnum:
        if flag.value not in flag_state.complex_flags:
            checkbox = ft.Checkbox(
                label=flag.display_name,
                value=False,
                on_change=lambda e, key=flag.value: on_checkbox_changed(key, e.control.value)
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

    # Step 2: Inputs
    flagstring_input = ft.TextField(
        label="ZORA Flag String",
        value="",
        on_change=on_flagstring_changed,
        width=300
    )
    seed_input = ft.TextField(
        label="ZORA Seed Number",
        value="",
        width=300
    )

    # Step 2: Container
    step2_container = build_step2_container(
        flag_checkbox_rows,
        flagstring_input,
        seed_input,
        on_randomize
    )

    # Add to page
    page.add(step1_container, step2_container)
    page.update()
