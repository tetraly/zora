import flet as ft
import io
import logging as log
import os
import random
import tempfile
import sys
from pathlib import Path
from typing import Callable


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from version import __version__
from logic.randomizer import Z1Randomizer
from windows import zrinterface
from ui.known_issues import build_known_issues_page
from ui.rom_utils import (extract_base_rom_code, extract_code_from_rom_data, is_vanilla_rom,
                          is_vanilla_rom_data, parse_filename_for_flag_and_seed)
from ui.dialogs import show_error_dialog, show_snackbar
from ui.state import FlagState, RomInfo
from ui.handlers import AppState, EventHandlers
from ui.components import (build_rom_info_card, build_zora_settings_card, build_step1_container,
                           build_step2_container, build_step3_container, build_flag_checkboxes,
                           build_header)

# ============================================================================
# MAIN APPLICATION
# ============================================================================


def main(page: ft.Page, platform: str = "web") -> None:
    """Main application entry point.

    Args:
        page: Flet page object
        platform: Platform type - "windows", "macos", or "web"
    """
    page.title = f"ZORA (Zelda One Randomizer Add-ons) v{__version__}"
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
    state = AppState(rom_info, flag_state)

    # Event handlers
    handlers = EventHandlers(page, state, platform)

    # ========================================================================
    # UI Components
    # ========================================================================

    # File pickers with upload handlers
    vanilla_file_picker = ft.FilePicker(on_result=handlers.on_vanilla_file_picked,
                                        on_upload=handlers.on_vanilla_upload_progress)
    randomized_file_picker = ft.FilePicker(on_result=handlers.on_randomized_file_picked,
                                           on_upload=handlers.on_randomized_upload_progress)
    generate_vanilla_file_picker = ft.FilePicker(on_result=handlers.on_generate_vanilla_file_picked)

    # Store file picker references in handlers
    handlers.vanilla_file_picker = vanilla_file_picker
    handlers.randomized_file_picker = randomized_file_picker
    handlers.generate_vanilla_file_picker = generate_vanilla_file_picker
    page.overlay.append(vanilla_file_picker)
    page.overlay.append(randomized_file_picker)
    page.overlay.append(generate_vanilla_file_picker)
    page.update()

    # Step 1: Create buttons for file picking
    choose_vanilla_button = ft.ElevatedButton("Choose ROM",
                                              on_click=handlers.on_choose_vanilla_click)

    choose_randomized_button = ft.ElevatedButton("Choose ROM",
                                                 on_click=handlers.on_choose_randomized_click)

    choose_generate_vanilla_button = ft.ElevatedButton(
        "Choose Vanilla ROM", on_click=handlers.on_choose_generate_vanilla_click)

    # Store button reference in handlers
    handlers.choose_generate_vanilla_button = choose_generate_vanilla_button

    # Step 1: Generate ROM inputs
    gen_flagstring_input = ft.TextField(label="Zelda Randomizer Flag String",
                                        hint_text="e.g., 5JOfkHFLCIuh7WxM4mIYp7TuCHxRYQdJcty",
                                        width=350)
    gen_seed_input = ft.TextField(label="Zelda Randomizer Seed Number",
                                  hint_text="e.g., 12345",
                                  width=300)

    gen_random_seed_button = ft.ElevatedButton("Random Seed",
                                               on_click=handlers.on_gen_random_seed_click,
                                               icon=ft.Icons.SHUFFLE)

    # Create generate button (always enabled - validation happens on click)
    generate_rom_button = ft.ElevatedButton(
        "Generate Base ROM with Zelda Randomizer",
        on_click=handlers.on_generate_rom,
        disabled=False
    )

    # Store references in handlers
    handlers.gen_flagstring_input = gen_flagstring_input
    handlers.gen_seed_input = gen_seed_input
    handlers.gen_random_seed_button = gen_random_seed_button
    handlers.generate_rom_button = generate_rom_button

    # Step 1: Upload ROM
    step1_container = build_step1_container(choose_vanilla_button, choose_randomized_button,
                                            choose_generate_vanilla_button, gen_flagstring_input,
                                            gen_seed_input, gen_random_seed_button,
                                            generate_rom_button, platform)

    # Store step1 container reference in handlers
    handlers.step1_container = step1_container

    # Step 2: Flag checkboxes - dynamically create from FlagsEnum
    flag_checkboxes, categorized_flag_rows = build_flag_checkboxes(flag_state,
                                                                   handlers.on_checkbox_changed)

    # Store flag checkboxes reference in handlers
    handlers.flag_checkboxes = flag_checkboxes

    # Step 2: Inputs
    flagstring_input = ft.TextField(label="ZORA Flag String",
                                    value="",
                                    on_change=handlers.on_flagstring_changed,
                                    width=250)
    seed_input = ft.TextField(label="ZORA Seed Number", value="12345", width=200)

    random_seed_button = ft.ElevatedButton("Random Seed",
                                           on_click=handlers.on_random_seed_click,
                                           icon=ft.Icons.SHUFFLE)

    # Store references in handlers
    handlers.flagstring_input = flagstring_input
    handlers.seed_input = seed_input
    handlers.random_seed_button = random_seed_button

    # Step 2: Container
    step2_container = build_step2_container(categorized_flag_rows, flagstring_input, seed_input,
                                            random_seed_button, handlers.on_randomize,
                                            handlers.on_expand_all, handlers.on_collapse_all,
                                            handlers.expansion_panels_ref)

    # Store step2 container reference in handlers
    handlers.step2_container = step2_container

    # Build header
    header = build_header(handlers.on_view_known_issues)

    # Build main content container
    main_content = ft.Column([header, step1_container, step2_container], spacing=0)

    # Store main content reference in state
    state.main_content = main_content

    # Add to page
    page.add(main_content)
    page.update()
