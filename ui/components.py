"""UI component builders for the ZORA application."""

import flet as ft
import os
import sys
from typing import Callable


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logic.flags import FlagsEnum, FlagCategory
from ui.dialogs import info_row
from ui.state import RomInfo, FlagState

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

    return ft.Card(content=ft.Container(content=ft.Column([
        ft.Row([
            ft.Text("Loaded Base ROM", size=18, weight="bold"),
            ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Remove ROM", on_click=on_close)],
               alignment="spaceBetween"),
        info_row("ROM Type", rom_type_display),
        info_row("Filename", rom_info.filename),
        info_row("ZR Flag String", flagstring_display),
        info_row("ZR Seed", seed_display),
        info_row("ZR Code", code_display)],
                                                          spacing=5),
                                        padding=10,
                                        margin=0,
                                        border=ft.border.all(2, ft.Colors.BLUE_200),
                                        border_radius=10),
                   elevation=4)


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

    return ft.Card(content=ft.Container(content=ft.Column([
        ft.Text("ZORA Settings", size=18, weight="bold"),
        ft.Container(height=5),
        info_row("ZORA Flag String", flagstring, label_width=140),
        info_row("ZORA Seed", seed, label_width=140),
        ft.Container(height=10),
        ft.Text("Enabled Flags:", weight="w500", size=14),
        ft.Text(enabled_text, selectable=True),
        ft.Container(height=10),
        ft.Text("Disabled Flags:", weight="w500", size=14),
        ft.Text(disabled_text, selectable=True)],
                                                          spacing=5),
                                        padding=10,
                                        margin=0,
                                        border=ft.border.all(2, ft.Colors.PURPLE_200),
                                        border_radius=10),
                   elevation=4)


def build_step1_container(choose_vanilla_button,
                          choose_randomized_button,
                          choose_generate_vanilla_button,
                          gen_flagstring_input,
                          gen_seed_input,
                          gen_random_seed_button,
                          generate_rom_button,
                          platform: str = "web") -> ft.Column:
    """Build Step 1: Upload Base ROM section.

    Args:
        platform: Platform type - "windows", "macos", or "web"
    """

    # Panel A: Select Vanilla ROM
    vanilla_panel = ft.Container(content=ft.Column(
        [ft.Text("Option A: Select Vanilla ROM from disk", weight="bold"), choose_vanilla_button],
        spacing=10),
                                 padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
                                 border=ft.border.all(2, ft.Colors.BLUE_200),
                                 border_radius=10,
                                 expand=True)

    # Panel B: Select Randomized ROM
    randomized_panel = ft.Container(content=ft.Column([
        ft.Text("Option B: Select a ROM that was already randomized using Zelda Randomizer",
                weight="bold"), choose_randomized_button],
                                                      spacing=10),
                                    padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
                                    border=ft.border.all(2, ft.Colors.PURPLE_200),
                                    border_radius=10,
                                    expand=True)

    # Panel C: Generate ROM with Zelda Randomizer
    # Only enabled for Windows platform
    is_windows = platform == "windows"

    # Wrap seed input and random seed button together
    gen_seed_with_button = ft.Row([gen_seed_input, gen_random_seed_button], spacing=10, tight=True)

    generate_panel_content = ft.Column([
        ft.Text("Option C: Generate a new Base ROM using Zelda Randomizer", weight="bold"),
        choose_generate_vanilla_button,
        ft.Row([gen_flagstring_input, gen_seed_with_button], spacing=20), generate_rom_button],
                                       spacing=10)

    # Add platform restriction note if not Windows
    if not is_windows:
        generate_panel_content.controls.insert(
            1,
            ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.ORANGE_700),
                ft.Text(
                    "Integration with Zelda Randomizer is only available in the Windows version",
                    size=12,
                    color=ft.Colors.ORANGE_700,
                    italic=True)],
                                        spacing=5),
                         padding=ft.padding.only(top=5, bottom=5)))

    generate_panel = ft.Container(content=generate_panel_content,
                                  padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
                                  border=ft.border.all(2, ft.Colors.GREEN_200),
                                  border_radius=10,
                                  disabled=not is_windows,
                                  opacity=1.0 if is_windows else 0.5)

    # Wrap generate_panel to match width of the row above
    generate_panel_row = ft.Container(content=generate_panel, expand=True)

    return ft.Column([
        ft.Text("Step 1: Select Base ROM", size=20, weight="bold"),
        ft.Row([vanilla_panel, randomized_panel], spacing=15), generate_panel_row],
                     spacing=15)


def build_step2_container(categorized_flag_rows: dict,
                          flagstring_input: ft.TextField,
                          seed_input: ft.TextField,
                          random_seed_button: ft.ElevatedButton,
                          on_randomize: Callable,
                          on_expand_all: Callable,
                          on_collapse_all: Callable,
                          expansion_panels_ref: list = None) -> ft.Container:
    """Build Step 2: Configure Flags & Seed section with categorized accordions.

    Args:
        categorized_flag_rows: Dict mapping FlagCategory -> list of flag rows
        flagstring_input: TextField for flagstring
        seed_input: TextField for seed
        random_seed_button: Button for random seed
        on_randomize: Callback for randomize button
        on_expand_all: Callback for expand all button
        on_collapse_all: Callback for collapse all button
        expansion_panels_ref: Optional list to populate with expansion panel references
    """
    # Wrap seed input and button together
    seed_with_button = ft.Row([seed_input, random_seed_button], spacing=10, tight=True)

    flag_seed_row = ft.Row([flagstring_input, seed_with_button], spacing=20, wrap=True)

    randomize_button = ft.ElevatedButton("Randomize", on_click=on_randomize)

    # Create expand/collapse buttons
    expand_collapse_buttons = ft.Row([
        ft.ElevatedButton(
            "Expand All", icon=ft.Icons.UNFOLD_MORE, on_click=on_expand_all, height=35),
        ft.ElevatedButton(
            "Collapse All", icon=ft.Icons.UNFOLD_LESS, on_click=on_collapse_all, height=35)],
                                     spacing=8)

    # Define border colors for category headers
    category_border_colors = {
        FlagCategory.ITEM_SHUFFLE: ft.Colors.BLUE_600,
        FlagCategory.ITEM_CHANGES: ft.Colors.PURPLE_600,
        FlagCategory.OVERWORLD_RANDOMIZATION: ft.Colors.GREEN_600,
        FlagCategory.LOGIC_AND_DIFFICULTY: ft.Colors.ORANGE_600,
        FlagCategory.QUALITY_OF_LIFE: ft.Colors.CYAN_600}

    # Build expansion panels for each category
    expansion_panels = []
    for category in FlagCategory:
        if categorized_flag_rows[category]:  # Only show categories with flags
            # Split flags in this category into two columns
            flags_in_category = categorized_flag_rows[category]
            mid = (len(flags_in_category) + 1) // 2
            left_flags = flags_in_category[:mid]
            right_flags = flags_in_category[mid:]

            category_content = ft.Row([
                ft.Column(left_flags, spacing=3, expand=True),
                ft.Column(right_flags, spacing=3, expand=True)],
                                      spacing=10)

            # Create colored header with border
            header = ft.Container(
                content=ft.ListTile(title=ft.Text(category.display_name, weight="bold"),
                                    dense=True,
                                    content_padding=ft.padding.symmetric(horizontal=10,
                                                                         vertical=2)),
                border=ft.border.all(2, category_border_colors.get(category, ft.Colors.GREY_600)),
                border_radius=5,
                padding=0)

            panel = ft.ExpansionPanel(
                header=header,
                content=ft.Container(content=category_content,
                                     padding=ft.padding.only(left=5, right=5, top=5, bottom=2)),
                can_tap_header=True,
                expanded=True  # Start expanded
            )
            expansion_panels.append(panel)

            # Populate reference list if provided
            if expansion_panels_ref is not None:
                expansion_panels_ref.append(panel)

    expansion_panel_list = ft.ExpansionPanelList(controls=expansion_panels,
                                                 elevation=2,
                                                 divider_color=ft.Colors.PURPLE_100,
                                                 expand_icon_color=ft.Colors.PURPLE_700)

    content = ft.Column([
        ft.Text("Step 2: Configure ZORA Flags and Seed Number", size=20, weight="bold"),
        ft.Container(height=3), flag_seed_row,
        ft.Divider(height=1), expand_collapse_buttons,
        ft.Container(height=3), expansion_panel_list,
        ft.Container(randomize_button, alignment=ft.alignment.center, padding=5)],
                        spacing=5)

    return ft.Container(content=content,
                        padding=15,
                        border=ft.border.all(2, ft.Colors.PURPLE_200),
                        border_radius=10,
                        margin=10,
                        disabled=True,
                        opacity=0.4)


def build_step3_container(randomized_rom_data: bytes, output_filename: str, flagstring: str,
                          seed: str, code: str, platform: str, on_download: Callable,
                          on_randomize_another: Callable) -> ft.Container:
    """Build Step 3: Download Randomized ROM section.

    Args:
        randomized_rom_data: The randomized ROM bytes
        output_filename: Name of the output file
        flagstring: The ZORA flagstring used
        seed: The seed used
        code: The ROM code
        platform: Platform type - "windows", "macos", or "web"
        on_download: Download button click handler
        on_randomize_another: Handler for randomizing another game
    """
    download_button = ft.ElevatedButton("Download Randomized ROM",
                                        icon=ft.Icons.DOWNLOAD,
                                        on_click=on_download)

    randomize_another_button = ft.ElevatedButton("Randomize Another Game",
                                                 icon=ft.Icons.RESTART_ALT,
                                                 on_click=on_randomize_another)

    content = ft.Column([
        ft.Text("Step 3: Download Randomized ROM", size=20, weight="bold"),
        ft.Container(height=10),
        ft.Row([
            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=40),
            ft.Text("Randomization Complete!", size=16, weight="bold", color=ft.Colors.GREEN)],
               spacing=10),
        ft.Container(height=10),
        info_row("Output File", output_filename, label_width=150, value_width=400),
        info_row("ZORA Flag String", flagstring, label_width=150, value_width=400),
        info_row("ZORA Seed", seed, label_width=150),
        info_row("ZORA Code", code, label_width=150),
        info_row("ROM Size", f"{len(randomized_rom_data) / 1024:.1f} KB", label_width=150),
        ft.Container(height=15),
        ft.Row([download_button, randomize_another_button], spacing=10)],
                        spacing=5)

    return ft.Container(content=content,
                        padding=20,
                        border=ft.border.all(2, ft.Colors.GREEN_200),
                        border_radius=10,
                        margin=10)


def build_flag_checkboxes(flag_state: FlagState, on_change_callback) -> tuple[dict, dict]:
    """Build flag checkboxes grouped by category from FlagsEnum.

    Args:
        flag_state: FlagState instance containing complex_flags list
        on_change_callback: Callback function for checkbox changes (flag_key, value)

    Returns:
        tuple: (flag_checkboxes dict, categorized_flag_rows dict)
            - flag_checkboxes: flat dict of all checkboxes by flag key
            - categorized_flag_rows: dict mapping FlagCategory -> list of flag rows
    """
    flag_checkboxes = {}
    categorized_flag_rows = {}

    # Initialize categories
    for category in FlagCategory:
        categorized_flag_rows[category] = []

    # Build checkboxes and organize by category
    for flag in FlagsEnum:
        if flag.value not in flag_state.complex_flags:
            checkbox = ft.Checkbox(
                label=flag.display_name,
                value=False,
                on_change=lambda e, key=flag.value: on_change_callback(key, e.control.value))
            flag_checkboxes[flag.value] = checkbox

            # Create row with checkbox and help icon
            flag_row = ft.Row([
                checkbox,
                ft.IconButton(icon=ft.Icons.HELP_OUTLINE,
                              icon_size=16,
                              tooltip=flag.help_text,
                              style=ft.ButtonStyle(padding=2))],
                              spacing=0,
                              tight=True)

            # Add to appropriate category
            categorized_flag_rows[flag.category].append(flag_row)

    return flag_checkboxes, categorized_flag_rows


def build_header(on_view_known_issues) -> ft.Container:
    """Build the application header with logo and title.

    Args:
        on_view_known_issues: Callback function to navigate to known issues page
    """
    return ft.Container(content=ft.Column([
        ft.Row([
            ft.Image(src="zora.png", width=96, height=96, fit=ft.ImageFit.CONTAIN),
            ft.Column([
                ft.Text("Zelda One Randomizer Add-Ons (ZORA) beta v0.2",
                        size=28,
                        weight="bold",
                        color=ft.Colors.BLUE_900),
                ft.Container(height=5),
                ft.Text(spans=[
                    ft.TextSpan("ZORA is an add-on randomizer for "),
                    ft.TextSpan("Zelda Randomizer",
                                style=ft.TextStyle(color=ft.Colors.BLUE_700),
                                url="https://sites.google.com/site/zeldarandomizer/"),
                    ft.TextSpan(
                        " introducing several new features. "
                        "It works by re-randomizing a ROM that has already "
                        "been randomized using the original Zelda Randomizer. "
                        "It can also randomize an unrandomized (vanilla) Legend of Zelda ROM.")],
                        size=14,
                        width=700),
                ft.Container(height=8),
                ft.Column([
                    ft.Text(spans=[
                        ft.TextSpan("WARNING: ", style=ft.TextStyle(weight=ft.FontWeight.BOLD)),
                        ft.TextSpan(
                            "As of October 2025, ZORA is still an experimental product in early testing. "
                            "While everyone is welcomed and encouraged to try it out, please be aware that "
                            "any seeds you generate may contain bugs, unexpected glitches, softlocks, "
                            "and may be completely unbeatable. Please proceed at your own risk! ")],
                            size=13,
                            color=ft.Colors.RED_800,
                            width=700),
                    ft.TextButton("Please click here to view the Known Issues & Bugs page.",
                                  on_click=on_view_known_issues,
                                  style=ft.ButtonStyle(padding=0, color=ft.Colors.WHITE))],
                          spacing=5)],
                      spacing=0)],
               spacing=20,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Divider(height=20, thickness=2)],
                                          spacing=10),
                        padding=ft.padding.only(bottom=10))
