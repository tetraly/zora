"""UI component builders for the ZORA application."""

import flet as ft
import os
import sys
from typing import Callable


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from version import __version_display__
from logic.flags import FlagsEnum, FlagCategory, FlagRegistry, BooleanFlag, EnumFlag, IntegerFlag
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
        rom_type_display = "Randomized using Zelda Randomizer"
        flagstring_display = rom_info.flagstring
        seed_display = rom_info.seed
        code_display = rom_info.code

    # Extract just the filename from the full path
    filename_display = os.path.basename(rom_info.filename)

    return ft.Card(content=ft.Container(content=ft.Column([
        ft.Row([
            ft.Text("Loaded Base ROM", size=18, weight="bold"),
            ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Remove ROM", on_click=on_close)],
               alignment="spaceBetween"),
        info_row("ROM Type", rom_type_display),
        info_row("Filename", filename_display),
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
    # Generate lists of enabled/non-default flags and disabled/default flags
    enabled_flags = []
    disabled_flags = []

    all_flags = FlagRegistry.get_all_flags()
    for flag_key, flag_def in all_flags.items():
        flag_value = flag_state.flags.get(flag_key, flag_def.get_default())
        default_value = flag_def.get_default()

        # Check if flag is at non-default value
        if isinstance(flag_def, BooleanFlag):
            if flag_value:
                enabled_flags.append(flag_def.display_name)
            else:
                disabled_flags.append(flag_def.display_name)
        elif isinstance(flag_def, EnumFlag):
            if flag_value != default_value:
                enabled_flags.append(f"{flag_def.display_name}: {flag_def.get_option_display_name(flag_value)}")
            else:
                disabled_flags.append(f"{flag_def.display_name}: {flag_def.get_option_display_name(flag_value)}")
        elif isinstance(flag_def, IntegerFlag):
            if flag_value != default_value:
                enabled_flags.append(f"{flag_def.display_name}: {flag_value}")
            else:
                disabled_flags.append(f"{flag_def.display_name}: {flag_value}")

    # Create flag list displays
    enabled_text = ", ".join(enabled_flags) if enabled_flags else "None"
    disabled_text = ", ".join(disabled_flags) if disabled_flags else "None"

    return ft.Card(content=ft.Container(content=ft.Column([
        ft.Text("ZORA Settings", size=18, weight="bold"),
        ft.Container(height=5),
        info_row("ZORA Flag String", flagstring, label_width=140),
        info_row("ZORA Seed", seed, label_width=140),
        ft.Container(height=10),
        ft.Text("Non-Default Flags:", weight="w500", size=14),
        ft.Text(enabled_text, selectable=True),
        ft.Container(height=10),
        ft.Text("Default Flags:", weight="w500", size=14),
        ft.Text(disabled_text, selectable=True)],
                                                          spacing=5),
                                        padding=10,
                                        margin=0,
                                        border=ft.border.all(2, ft.Colors.PURPLE_200),
                                        border_radius=10),
                   elevation=4)


def build_step1_container(choose_rom_button,
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

    # Merged Panel: Select ROM (vanilla or randomized with auto-detection)
    rom_select_panel = ft.Container(content=ft.Column([
        ft.Text("Select a vanilla Legend of Zelda ROM or a randomized ROM from Zelda Randomizer",
                weight="bold"),
        ft.Container(content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.WHITE),
            ft.Text(
                "Don't forget to uncheck the \"Race ROM\" flag in Zelda Randomizer as Race ROMs are not supported.",
                size=12,
                color=ft.Colors.WHITE,
                italic=True)],
                                    spacing=5),
                     padding=ft.padding.only(top=5, bottom=5)),
        choose_rom_button],
                                                      spacing=10),
                                    padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
                                    border=ft.border.all(2, ft.Colors.BLUE_200),
                                    border_radius=10,
                                    expand=True)

    # Alternate Option: Generate ROM with Zelda Randomizer
    # Only enabled for Windows platform
    is_windows = platform == "windows"

    # Wrap seed input and random seed button together
    gen_seed_with_button = ft.Row([gen_seed_input, gen_random_seed_button], spacing=10, tight=True)

    generate_panel_content = ft.Column([
        ft.Text("Alternate Option: Integrate with Zelda Randomizer to generate a new Base ROM", weight="bold"),
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

    # Wrap generate_panel to match width
    generate_panel_row = ft.Container(content=generate_panel, expand=True)

    return ft.Column([
        ft.Text("Step 1: Select Base ROM", size=20, weight="bold"),
        rom_select_panel, generate_panel_row],
                     spacing=15)


def build_step2_container(categorized_flag_rows: dict,
                          flagstring_input: ft.TextField,
                          seed_input: ft.TextField,
                          random_seed_button: ft.ElevatedButton,
                          on_randomize: Callable,
                          on_expand_all: Callable,
                          on_collapse_all: Callable,
                          expansion_panels_ref: list = None,
                          legacy_note_ref: list = None) -> ft.Container:
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
        legacy_note_ref: Optional list to store reference to legacy note container
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
        # Skip hidden category entirely
        if category == FlagCategory.HIDDEN:
            continue
        if categorized_flag_rows[category]:  # Only show categories with flags
            # Build content with subcategories
            subcategory_sections = []

            # Get all subcategories for this category
            subcategories_dict = categorized_flag_rows[category]

            # Process each subcategory
            for subcategory, flags_in_subcategory in subcategories_dict.items():
                if not flags_in_subcategory:
                    continue

                # Split flags in this subcategory into two columns
                mid = (len(flags_in_subcategory) + 1) // 2
                left_flags = flags_in_subcategory[:mid]
                right_flags = flags_in_subcategory[mid:]

                # Create flag rows
                flag_content = ft.Row([
                    ft.Column(left_flags, spacing=3, expand=True),
                    ft.Column(right_flags, spacing=3, expand=True)],
                                          spacing=10)

                # If there's a subcategory name, add a header
                if subcategory:
                    subcategory_section = ft.Column([
                        ft.Container(
                            content=ft.Text(subcategory, size=14, weight="w600", color=ft.Colors.BLUE_800),
                            padding=ft.padding.only(top=5, bottom=5, left=5)
                        ),
                        flag_content
                    ], spacing=0)
                else:
                    subcategory_section = flag_content

                subcategory_sections.append(subcategory_section)

            # Combine all subcategory sections
            if len(subcategory_sections) == 1:
                category_content = subcategory_sections[0]
            else:
                category_content = ft.Column(subcategory_sections, spacing=10)

            # Add a note for LEGACY flags
            if category == FlagCategory.LEGACY:
                legacy_note = ft.Container(
                    content=ft.Text(
                        "⚠️ Legacy flags are only available for use with vanilla ROMs.",
                        color=ft.Colors.ORANGE_700,
                        size=12,
                        weight="bold"),
                    padding=ft.padding.only(bottom=10),
                    visible=False)  # Hidden by default, shown when randomized ROM loaded
                category_content = ft.Column([legacy_note, category_content], spacing=5)

                # Store reference if provided
                if legacy_note_ref is not None:
                    legacy_note_ref.append(legacy_note)

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
                          on_randomize_another: Callable, generation_time: float = None) -> ft.Container:
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
        generation_time: Time taken to generate the ROM in seconds (optional)
    """
    download_button = ft.ElevatedButton("Download Randomized ROM",
                                        icon=ft.Icons.DOWNLOAD,
                                        on_click=on_download)

    randomize_another_button = ft.ElevatedButton("Randomize Another Game",
                                                 icon=ft.Icons.RESTART_ALT,
                                                 on_click=on_randomize_another)

    # Build info rows list
    info_rows = [
        ft.Text("Step 3: Download Randomized ROM", size=20, weight="bold"),
        ft.Container(height=10),
        ft.Row([
            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=40),
            ft.Text("Randomization Complete!", size=16, weight="bold", color=ft.Colors.GREEN)],
               spacing=10),
        ft.Container(height=10),
        info_row("Output File", output_filename, label_width=150),
        info_row("ZORA Flag String", flagstring, label_width=150),
        info_row("ZORA Seed", seed, label_width=150),
        info_row("ZORA Code", code, label_width=150),
        info_row("ROM Size", f"{len(randomized_rom_data) / 1024:.1f} KB", label_width=150),
    ]

    # Add generation time if provided
    if generation_time is not None:
        info_rows.append(info_row("Generation Time", f"{generation_time:.2f} seconds", label_width=150))

    info_rows.extend([
        ft.Container(height=15),
        ft.Row([download_button, randomize_another_button], spacing=10)
    ])

    content = ft.Column(info_rows, spacing=5)

    return ft.Container(content=content,
                        padding=20,
                        border=ft.border.all(2, ft.Colors.GREEN_200),
                        border_radius=10,
                        margin=10)


def build_flag_checkboxes(flag_state: FlagState, on_change_callback) -> tuple[dict, dict]:
    """Build flag controls (checkboxes, dropdowns, number inputs) grouped by category and subcategory.

    Args:
        flag_state: FlagState instance containing complex_flags list
        on_change_callback: Callback function for control changes (flag_key, value)

    Returns:
        tuple: (flag_controls dict, categorized_flag_rows dict)
            - flag_controls: flat dict of all controls by flag key
            - categorized_flag_rows: dict mapping FlagCategory -> dict of subcategory -> list of flag rows
    """
    flag_controls = {}
    categorized_flag_rows = {}

    # Initialize categories with empty dicts for subcategories
    for category in FlagCategory:
        categorized_flag_rows[category] = {}

    # Build controls from FlagRegistry and organize by category and subcategory
    all_flags = FlagRegistry.get_all_flags()

    for flag_key, flag_def in all_flags.items():
        # Skip hidden flags and complex flags
        if flag_def.category == FlagCategory.HIDDEN:
            continue
        if flag_key in flag_state.complex_flags:
            continue

        # Create appropriate control based on flag type
        control = None

        if isinstance(flag_def, BooleanFlag):
            # Boolean flag -> Checkbox
            checkbox = ft.Checkbox(
                label=flag_def.display_name,
                value=flag_def.get_default(),
                on_change=lambda e, key=flag_key: on_change_callback(key, e.control.value))
            control = checkbox
            flag_controls[flag_key] = checkbox

        elif isinstance(flag_def, EnumFlag):
            # Enum flag -> Dropdown
            dropdown = ft.Dropdown(
                label=flag_def.display_name,
                options=[ft.dropdown.Option(opt.value, opt.display_name) for opt in flag_def.options],
                value=flag_def.get_default(),
                on_change=lambda e, key=flag_key: on_change_callback(key, e.control.value),
                width=300)
            control = dropdown
            flag_controls[flag_key] = dropdown

        elif isinstance(flag_def, IntegerFlag):
            # Integer flag -> TextField with number input
            text_field = ft.TextField(
                label=flag_def.display_name,
                value=str(flag_def.get_default()),
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e, key=flag_key, defn=flag_def: on_change_callback(
                    key,
                    int(e.control.value) if e.control.value.isdigit() else defn.get_default()
                ),
                width=200,
                hint_text=f"{flag_def.min_value}-{flag_def.max_value}" if flag_def.min_value is not None else None)
            control = text_field
            flag_controls[flag_key] = text_field

        # Create row with control and help icon
        if control:
            flag_row = ft.Row([
                control,
                ft.IconButton(icon=ft.Icons.HELP_OUTLINE,
                              icon_size=16,
                              tooltip=flag_def.help_text,
                              style=ft.ButtonStyle(padding=2))],
                              spacing=0,
                              tight=True)

            # Add to appropriate category and subcategory
            subcategory = flag_def.subcategory if flag_def.subcategory else None
            if subcategory not in categorized_flag_rows[flag_def.category]:
                categorized_flag_rows[flag_def.category][subcategory] = []
            categorized_flag_rows[flag_def.category][subcategory].append(flag_row)

    return flag_controls, categorized_flag_rows


def build_header(on_view_known_issues) -> ft.Container:
    """Build the application header with logo and title.

    Args:
        on_view_known_issues: Callback function to navigate to known issues page
    """
    return ft.Container(content=ft.Column([
        ft.Row([
            ft.Image(src="zora.png", width=96, height=96, fit=ft.ImageFit.CONTAIN),
            ft.Column([
                ft.Text(f"Zelda One Randomizer Add-Ons (ZORA) {__version_display__}",
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
                            "As of late October 2025, ZORA is becoming increasingly stable and nearing "
                            "a full release. However, like with any beta software, please be aware that "
                            "any seeds you generate may contain bugs, unexpected glitches, softlocks, "
                            "and may be completely unbeatable. Please proceed at your own risk! ")],
                            size=13,
                            color=ft.Colors.RED_800,
                            width=700),
                    ft.TextButton("Please click here to view the Known Issues & Bugs page.",
                                  on_click=on_view_known_issues,
                                  style=ft.ButtonStyle(padding=0, color=ft.Colors.WHITE)),
                    ft.Container(height=5),
                    ft.ElevatedButton(
                        "Join the ZORA Discord Server",
                        icon=ft.Icons.DISCORD if hasattr(ft.Icons, 'DISCORD') else ft.Icons.CHAT,
                        on_click=lambda _: _.page.launch_url("https://discord.gg/PQ8udvrMJ9"),
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.with_opacity(0.9, "#5865F2"),
                            color=ft.Colors.WHITE,
                        ),
                    )],
                          spacing=5)],
                      spacing=0)],
               spacing=20,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Divider(height=20, thickness=2)],
                                          spacing=10),
                        padding=ft.padding.only(bottom=10))
