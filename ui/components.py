"""UI component builders for the ZORA application."""

import flet as ft
import os
import sys
from typing import Callable


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from version import __version_display__
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
                          on_randomize: Callable) -> ft.Container:
    """Build Step 2: Configure Flags & Seed section with categorized tabs.

    Args:
        categorized_flag_rows: Dict mapping FlagCategory -> list of flag rows
        flagstring_input: TextField for flagstring
        seed_input: TextField for seed
        random_seed_button: Button for random seed
        on_randomize: Callback for randomize button
    """
    # Wrap seed input and button together
    seed_with_button = ft.Row([seed_input, random_seed_button], spacing=10, tight=True)

    flag_seed_row = ft.Row([flagstring_input, seed_with_button], spacing=20, wrap=True)

    randomize_button = ft.ElevatedButton("Randomize", on_click=on_randomize)

    # Define border colors for category tabs
    category_border_colors = {
        FlagCategory.ITEM_SHUFFLE: ft.Colors.BLUE_600,
        FlagCategory.ITEM_CHANGES: ft.Colors.PURPLE_600,
        FlagCategory.OVERWORLD_RANDOMIZATION: ft.Colors.GREEN_600,
        FlagCategory.LOGIC_AND_DIFFICULTY: ft.Colors.ORANGE_600,
        FlagCategory.QUALITY_OF_LIFE: ft.Colors.CYAN_600,
        FlagCategory.SHUFFLE_WITHIN_DUNGEONS: ft.Colors.TEAL_600,
        FlagCategory.LEGACY: ft.Colors.GREY_600}

    # Build tabs for each category
    tabs = []
    for category in FlagCategory:
        # Skip hidden category entirely
        if category == FlagCategory.HIDDEN:
            continue
        if categorized_flag_rows[category]:  # Only show categories with flags
            flags_in_category = categorized_flag_rows[category]

            # Special layout for Item Shuffle tab
            if category == FlagCategory.ITEM_SHUFFLE:
                # Separate flags into shuffle pool, constraints, and master toggle
                shuffle_pool_flags = []
                constraint_flags = []
                master_toggle = None

                for flag_row in flags_in_category:
                    # Extract flag key from the row's data attribute
                    flag_key = flag_row.data if hasattr(flag_row, 'data') else None

                    # Master toggle (major_item_shuffle)
                    if flag_key == 'major_item_shuffle':
                        master_toggle = flag_row
                    # Constraint flags (force/allow)
                    elif flag_key and (flag_key.startswith('force_') or flag_key.startswith('allow_important')):
                        constraint_flags.append(flag_row)
                    # Everything else goes in shuffle pool
                    else:
                        shuffle_pool_flags.append(flag_row)

                # Split shuffle pool into two sub-columns
                mid = (len(shuffle_pool_flags) + 1) // 2
                shuffle_left = shuffle_pool_flags[:mid]
                shuffle_right = shuffle_pool_flags[mid:]

                # Left side: Shuffle pool (no header text)
                left_container = ft.Container(
                    content=ft.Row([
                        ft.Column(shuffle_left, spacing=3, expand=True),
                        ft.Column(shuffle_right, spacing=3, expand=True)
                    ], spacing=10),
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLUE_300),
                    border_radius=5,
                    expand=True
                )

                # Right side: Constraints (no internal header)
                right_container = ft.Container(
                    content=ft.Column(constraint_flags, spacing=3),
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLUE_300),
                    border_radius=5,
                    expand=True
                )

                # Build layout: master toggle above, then two containers side by side
                # Right side has header text above the container
                # Wrap the panels in a container that can be disabled
                panels_container = ft.Container(
                    content=ft.Row([
                        left_container,
                        ft.Column([
                            ft.Text("... with these constraints:", weight="bold", size=14),
                            right_container
                        ], spacing=5)
                    ], spacing=15),
                    data="item_shuffle_panels",  # Identifier for handlers
                    disabled=True,  # Start disabled (master toggle is unchecked by default)
                    opacity=0.4
                )

                category_content = ft.Column([
                    master_toggle,
                    panels_container
                ], spacing=0)
            else:
                # Default two-column layout for other categories
                mid = (len(flags_in_category) + 1) // 2
                left_flags = flags_in_category[:mid]
                right_flags = flags_in_category[mid:]

                # Create flag rows
                category_content = ft.Row([
                    ft.Column(left_flags, spacing=3, expand=True),
                    ft.Column(right_flags, spacing=3, expand=True)],
                                          spacing=10)

            # Create tab with colored border around content
            tab = ft.Tab(
                text=category.display_name,
                content=ft.Container(
                    content=category_content,
                    padding=15,
                    border=ft.border.all(2, category_border_colors.get(category, ft.Colors.GREY_600)),
                    border_radius=5
                )
            )
            tabs.append(tab)
            print(f"DEBUG: Added tab for {category.display_name}")

    print(f"DEBUG: Total tabs created: {len(tabs)}")

    # Create Tabs widget with explicit height constraint
    # IMPORTANT: ft.Tabs widget REQUIRES explicit height when nested in containers,
    # especially when the parent container has disabled=True initially. Without
    # explicit height, the Tabs widget may collapse to 0 height and become invisible
    # in Flet web. This is a critical layout constraint - do not remove the height!
    tabs_widget = ft.Container(
        content=ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=tabs,
        ),
        height=500,  # Explicit height - REQUIRED for Tabs to render properly
    )

    content = ft.Column([
        ft.Text("Step 2: Configure ZORA Flags and Seed Number", size=20, weight="bold"),
        ft.Container(height=3), flag_seed_row,
        ft.Divider(height=1),
        ft.Container(height=5),
        tabs_widget,
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
        # Skip hidden flags and complex flags
        if flag.category == FlagCategory.HIDDEN:
            continue
        if flag.value not in flag_state.complex_flags:
            checkbox = ft.Checkbox(
                label=flag.display_name,
                value=False,
                data=flag.value,  # Store flag key for identification
                disabled=False,  # Will be updated based on dependencies
                on_change=lambda e, key=flag.value: on_change_callback(key, e.control.value))
            flag_checkboxes[flag.value] = checkbox

            # Store dependency info on checkbox for later reference
            if hasattr(flag, 'depends_on'):
                checkbox.data = (flag.value, flag.depends_on)
            else:
                checkbox.data = (flag.value, None)

            # Create row with checkbox and help icon
            flag_row = ft.Row([
                checkbox,
                ft.IconButton(icon=ft.Icons.HELP_OUTLINE,
                              icon_size=16,
                              tooltip=flag.help_text,
                              style=ft.ButtonStyle(padding=2))],
                              spacing=0,
                              tight=True,
                              data=flag.value)  # Store flag key on row too

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
