"""Event handlers for the ZORA application."""

import flet as ft
import io
import logging as log
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Callable
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.randomizer import Z1Randomizer
from windows import zrinterface
from ui.dialogs import show_error_dialog, show_snackbar
from ui.rom_utils import (extract_base_rom_code, extract_code_from_rom_data, is_vanilla_rom,
                          is_vanilla_rom_data, parse_filename_for_flag_and_seed)
from ui.components import (build_rom_info_card, build_zora_settings_card, build_step3_container)
from ui.known_issues import build_known_issues_page


class AppState:
    """Container for application state to avoid multiple nonlocal variables."""

    def __init__(self, rom_info, flag_state):
        self.rom_info = rom_info
        self.flag_state = flag_state
        self.file_card = None
        self.vanilla_rom_path = None
        self.randomized_rom_data = None
        self.randomized_rom_filename = None
        self.step3_container = None
        self.zora_settings_card = None
        self.known_issues_page = None
        self.main_content = None


class EventHandlers:
    """Manages all event handlers for the ZORA application."""

    def __init__(self, page: ft.Page, state: AppState, platform: str = "web"):
        """Initialize event handlers with references to page, state, and UI components.

        Args:
            page: Flet page object
            state: AppState object containing all application state
            platform: Platform type - "windows", "macos", or "web"
        """
        self.page = page
        self.state = state
        self.platform = platform

        # UI component references (will be set after components are created)
        self.step1_container = None
        self.step2_container = None
        self.flagstring_input = None
        self.seed_input = None
        self.random_seed_button = None
        self.flag_checkboxes = None
        self.gen_flagstring_input = None
        self.gen_seed_input = None
        self.gen_random_seed_button = None
        self.generate_rom_button = None
        self.choose_generate_vanilla_button = None
        self.vanilla_file_picker = None
        self.randomized_file_picker = None
        self.generate_vanilla_file_picker = None
        self.expansion_panels_ref = []

        # Upload state
        self.upload_state = {
            'vanilla': {
                'file_info': None,
                'uploading': False,
                'uploaded_path': None},
            'randomized': {
                'file_info': None,
                'uploading': False,
                'uploaded_path': None}}

    # Navigation handlers
    def on_view_known_issues(self, e) -> None:
        """Navigate to known issues page."""
        # Hide main content
        self.state.main_content.visible = False
        self.state.main_content.update()

        # Build and show known issues page
        if not self.state.known_issues_page:
            self.state.known_issues_page = build_known_issues_page(self.page, self.on_back_to_main)
            self.page.add(self.state.known_issues_page)
        else:
            self.state.known_issues_page.visible = True
            self.state.known_issues_page.update()

        self.page.update()

    def on_back_to_main(self, e) -> None:
        """Navigate back to main page."""
        # Hide known issues page
        if self.state.known_issues_page:
            self.state.known_issues_page.visible = False
            self.state.known_issues_page.update()

        # Show main content
        self.state.main_content.visible = True
        self.state.main_content.update()

        self.page.update()

    # Flagstring and checkbox handlers
    def update_flagstring(self) -> None:
        """Update flagstring input based on checkbox states."""
        self.flagstring_input.value = self.state.flag_state.to_flagstring()
        self.flagstring_input.update()

    def on_flagstring_changed(self, e) -> None:
        """Parse flagstring input and update checkboxes if valid."""
        if self.state.flag_state.from_flagstring(self.flagstring_input.value):
            # Update checkbox UI to match parsed state
            for flag_key, checkbox in self.flag_checkboxes.items():
                checkbox.value = self.state.flag_state.flags.get(flag_key, False)
                checkbox.update()

    def on_checkbox_changed(self, flag_key: str, value: bool) -> None:
        """Handle checkbox state changes."""
        self.state.flag_state.flags[flag_key] = value
        self.update_flagstring()

    # Step visibility handlers
    def show_step1(self) -> None:
        """Show Step 1 UI."""
        self.step1_container.visible = True
        self.step1_container.update()

    def hide_step1(self) -> None:
        """Hide Step 1 UI."""
        self.step1_container.visible = False
        self.step1_container.update()

    def enable_step2(self) -> None:
        """Enable Step 2 UI."""
        self.step2_container.disabled = False
        self.step2_container.opacity = 1.0
        self.step2_container.update()

    def disable_step2(self) -> None:
        """Disable Step 2 UI."""
        self.step2_container.disabled = True
        self.step2_container.opacity = 0.4
        self.step2_container.update()

    # ROM loading handlers
    def load_rom_and_show_card(self, disable_seed: bool = False) -> None:
        """Hide Step 1, show ROM info card, and initialize Step 2.

        Args:
            disable_seed: If True, disable seed input and random seed button
        """
        # Hide Step 1, show ROM info card
        self.hide_step1()

        if self.state.file_card:
            self.state.main_content.controls.remove(self.state.file_card)

        self.state.file_card = build_rom_info_card(self.state.rom_info, self.clear_rom)
        # Insert after header (index 0) and before step2 (which is at index 1 when step1 is hidden)
        self.state.main_content.controls.insert(1, self.state.file_card)
        self.state.main_content.update()

        # Initialize Step 2 with ROM data
        self.seed_input.value = self.state.rom_info.seed

        if disable_seed:
            self.seed_input.disabled = True
            self.random_seed_button.disabled = True
            self.seed_input.update()
            self.random_seed_button.update()

        self.update_flagstring()
        self.enable_step2()

    def clear_rom(self, e) -> None:
        """Remove ROM and reset UI to initial state."""
        if self.state.file_card:
            self.state.main_content.controls.remove(self.state.file_card)
            self.state.file_card = None
            self.state.rom_info.clear()
            self.state.vanilla_rom_path = None

            # Remove ZORA settings card if it exists
            if self.state.zora_settings_card:
                self.page.controls.remove(self.state.zora_settings_card)
                self.state.zora_settings_card = None

            # Remove Step 3 if it exists
            if self.state.step3_container:
                self.page.controls.remove(self.state.step3_container)
                self.state.step3_container = None

            # Reset generate vanilla button text
            self.choose_generate_vanilla_button.text = "Choose Vanilla ROM"
            self.choose_generate_vanilla_button.update()

            # Re-enable seed input and random seed button
            self.seed_input.disabled = False
            self.random_seed_button.disabled = False
            self.seed_input.update()
            self.random_seed_button.update()

            # Make sure step 2 is visible (it gets hidden when randomizing)
            self.step2_container.visible = True

            self.show_step1()
            self.disable_step2()
            self.page.update()

    # Download handler
    def create_download_handler(self, rom_data: bytes, filename: str) -> Callable:
        """Create a download handler for the given ROM data.

        Args:
            rom_data: The ROM data bytes to download
            filename: The filename for the download

        Returns:
            callable: Event handler for download button
        """

        def on_download_rom(e) -> None:
            """Handle download button click - triggers browser download"""
            if self.platform == "web":
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
                    self.page.launch_url(download_url)

                    # Show success message
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Downloading {filename}..."), bgcolor=ft.Colors.GREEN)
                    self.page.snack_bar.open = True
                    self.page.update()

                except Exception as ex:
                    show_error_dialog(self.page, "Download Error",
                                      f"Failed to prepare download:\n\n{str(ex)}")
            else:
                # For desktop (macOS/Windows), use file picker to save
                def on_save_result(e: ft.FilePickerResultEvent) -> None:
                    if e.path:
                        try:
                            with open(e.path, 'wb') as f:
                                f.write(rom_data)
                            show_snackbar(self.page, f"ROM saved successfully to:\n{e.path}")
                        except Exception as ex:
                            show_snackbar(self.page, f"Error saving file: {str(ex)}")

                save_file_picker = ft.FilePicker(on_result=on_save_result)
                self.page.overlay.append(save_file_picker)
                self.page.update()
                # Remove .nes extension from filename since save_file will add it
                filename_without_ext = filename.replace('.nes', '')
                save_file_picker.save_file(file_name=filename_without_ext,
                                           allowed_extensions=["nes"])

        return on_download_rom

    # ROM processing handlers
    def process_vanilla_rom(self, file_info, filepath) -> None:
        """Process a vanilla ROM file (after upload if needed)."""
        filename = file_info.name

        # Read ROM data from filepath
        with open(filepath, 'rb') as f:
            rom_data = f.read()

        # Validate that this is a vanilla ROM
        if not is_vanilla_rom_data(rom_data):
            show_error_dialog(self.page, "Error",
                              "This doesn't appear to be a vanilla Legend of Zelda ROM")
            return

        # Load ROM info for display
        self.state.rom_info.filename = filepath if filepath else filename
        self.state.rom_info.rom_type = "vanilla"
        self.state.rom_info.flagstring = ""
        self.state.rom_info.seed = ""

        # Vanilla ROMs don't have a code (they have 0xFF bytes), which is expected
        try:
            self.state.rom_info.code = extract_code_from_rom_data(rom_data)
        except (ValueError, KeyError):
            self.state.rom_info.code = "n/a"

        self.state.flag_state.seed = self.state.rom_info.seed
        self.load_rom_and_show_card(disable_seed=False)

    def process_randomized_rom(self, file_info, filepath) -> None:
        """Process a randomized ROM file (after upload if needed)."""
        filename = file_info.name

        # Read ROM data from filepath
        with open(filepath, 'rb') as f:
            rom_data = f.read()

        # Load ROM info for display
        self.state.rom_info.filename = filepath if filepath else filename
        self.state.rom_info.rom_type = "randomized"

        # Parse filename for seed and flagstring
        try:
            self.state.rom_info.flagstring, self.state.rom_info.seed = parse_filename_for_flag_and_seed(
                filename)
        except ValueError as ex:
            show_error_dialog(self.page, "Invalid Filename", str(ex))
            return

        # Validate that this is a randomized ROM by trying to extract the code
        try:
            self.state.rom_info.code = extract_code_from_rom_data(rom_data)
        except (ValueError, KeyError) as ex:
            show_error_dialog(
                self.page, "Invalid ROM",
                "This doesn't appear to be a valid randomized ROM.\n\nCould not extract code from the ROM."
            )
            return

        # Parse flagstring and update UI
        if self.state.flag_state.from_flagstring(self.state.rom_info.flagstring):
            # Update checkbox UI to match parsed state
            for flag_key, checkbox in self.flag_checkboxes.items():
                checkbox.value = self.state.flag_state.flags.get(flag_key, False)
                checkbox.update()

        self.state.flag_state.seed = self.state.rom_info.seed
        self.load_rom_and_show_card(disable_seed=True)

    # File picker handlers
    def on_vanilla_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle vanilla ROM file selection (Option A)."""
        if not e.files:
            return

        file_info = e.files[0]

        if file_info.path:
            # Desktop platform - process directly
            self.process_vanilla_rom(file_info, file_info.path)
        else:
            # Web platform - trigger upload first
            self.upload_state['vanilla']['file_info'] = file_info
            self.upload_state['vanilla']['uploading'] = True

            upload_list = [
                ft.FilePickerUploadFile(file_info.name,
                                        upload_url=self.page.get_upload_url(file_info.name, 600))]
            self.vanilla_file_picker.upload(upload_list)

    def on_randomized_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle randomized ROM file selection (Option B)."""
        if not e.files:
            return

        file_info = e.files[0]

        if file_info.path:
            # Desktop platform - process directly
            self.process_randomized_rom(file_info, file_info.path)
        else:
            # Web platform - trigger upload first
            self.upload_state['randomized']['file_info'] = file_info
            self.upload_state['randomized']['uploading'] = True

            upload_list = [
                ft.FilePickerUploadFile(file_info.name,
                                        upload_url=self.page.get_upload_url(file_info.name, 600))]
            self.randomized_file_picker.upload(upload_list)

    def on_generate_vanilla_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle vanilla ROM file selection for Option C (generate)."""
        if not e.files:
            return

        file_info = e.files[0]

        if file_info.path:
            # Desktop platform - store path directly
            self.state.vanilla_rom_path = file_info.path
            self.choose_generate_vanilla_button.text = f"✓ {file_info.name}"
            self.choose_generate_vanilla_button.update()

    # Zelda Randomizer interface handler
    def on_generate_rom(self, e) -> None:
        """Handle generate ROM button click for Option C."""
        print(f"Flagstring: {self.gen_flagstring_input.value}")  # Debug
        print(f"Seed: {self.gen_seed_input.value}")  # Debug

        # Validate all required fields and provide helpful error messages
        if not self.state.vanilla_rom_path:
            show_error_dialog(
                self.page, "Vanilla ROM Required",
                "Please select a vanilla Legend of Zelda ROM file first.\n\n"
                "Click the 'Choose Vanilla ROM' button to select your ROM file.")
            return

        if not self.gen_flagstring_input.value or not self.gen_flagstring_input.value.strip():
            show_error_dialog(
                self.page, "Flag String Required",
                "Please enter a Zelda Randomizer flag string.\n\n"
                "This is the flag string you want to use in the Zelda Randomizer app.\n"
                "Example: 5JOfkHFLCIuh7WxM4mIYp7TuCHxRYQdJcty")
            return

        if not self.gen_seed_input.value or not self.gen_seed_input.value.strip():
            show_error_dialog(
                self.page, "Seed Number Required",
                "Please enter a seed number for Zelda Randomizer.\n\n"
                "You can click the 'Random Seed' button to generate one, or enter your own.\n"
                "Example: 12345678")
            return

        # Validate the vanilla ROM
        try:
            if not is_vanilla_rom(self.state.vanilla_rom_path):
                show_error_dialog(
                    self.page, "Invalid ROM",
                    "The selected file does not appear to be a vanilla Legend of Zelda ROM.")
                return
        except Exception as ex:
            show_error_dialog(self.page, "Error",
                              f"Unable to read the selected ROM file:\n\n{str(ex)}")
            return

        # Create zrinterface.txt file in temp directory
        temp_dir = tempfile.gettempdir()
        interface_file = os.path.join(temp_dir, "zrinterface.txt")

        try:
            with open(interface_file, 'w') as f:
                f.write(f"{self.state.vanilla_rom_path}\n")
                f.write(f"{self.gen_flagstring_input.value}\n")
                f.write(f"{self.gen_seed_input.value}\n")
        except Exception as ex:
            show_error_dialog(self.page, "Error", f"Failed to create interface file:\n\n{str(ex)}")
            return

        # Show progress message
        show_snackbar(self.page, "Launching Zelda Randomizer interface...")

        # Call zrinterface to generate the ROM
        try:
            success = zrinterface.main()

            if not success:
                show_error_dialog(
                    self.page, "Zelda Randomizer Interface Error",
                    "Failed to interface with Zelda Randomizer.\n\n"
                    "Please ensure:\n"
                    "1. Zelda Randomizer 3.5.20 is running\n"
                    "2. The window is open and visible\n"
                    "3. zrinterface.exe is in the windows/ directory")
                return

            # The randomizer generates a ROM in the same directory as the vanilla ROM
            rom_dir = os.path.dirname(self.state.vanilla_rom_path)
            vanilla_basename = os.path.splitext(os.path.basename(self.state.vanilla_rom_path))[0]
            generated_filename = os.path.join(
                rom_dir,
                f"{vanilla_basename}_{self.gen_seed_input.value}_{self.gen_flagstring_input.value}.nes"
            )

            # Wait a moment for file to be written
            time.sleep(0.5)

            # Check if the ROM was generated
            if not os.path.exists(generated_filename):
                show_error_dialog(
                    self.page, "ROM Not Found",
                    f"The randomized ROM was not found at the expected location:\n\n{generated_filename}\n\n"
                    "Please check if Zelda Randomizer successfully generated the ROM.")
                return

            # Load the generated ROM info
            self.state.rom_info.filename = generated_filename
            self.state.rom_info.rom_type = "randomized"
            self.state.rom_info.flagstring = self.gen_flagstring_input.value
            self.state.rom_info.seed = self.gen_seed_input.value

            try:
                self.state.rom_info.code = extract_base_rom_code(generated_filename)
            except Exception as ex:
                show_error_dialog(self.page, "Error Reading ROM",
                                  f"The ROM was generated but could not be read:\n\n{str(ex)}")
                return

            self.state.flag_state.seed = self.state.rom_info.seed

            # Update UI
            self.load_rom_and_show_card(disable_seed=True)
            show_snackbar(self.page,
                          f"Successfully generated ROM: {os.path.basename(generated_filename)}")

        except FileNotFoundError as e:
            show_error_dialog(
                self.page, "File Not Found", f"A required file was not found:\n\n{str(e)}\n\n"
                "Make sure zrinterface.exe is in the windows/ directory.")
        except Exception as e:
            show_error_dialog(self.page, "Error",
                              f"An error occurred while generating the ROM:\n\n{str(e)}")

    # Randomization handler
    def on_randomize(self, e) -> None:
        """Handle randomize button click."""
        try:
            # Validate that seed is provided
            if not self.seed_input.value or not self.seed_input.value.strip():
                show_error_dialog(self.page, "Seed Required",
                                  "Please enter a seed number before randomizing.")
                return

            # Read the base ROM file
            with open(self.state.rom_info.filename, 'rb') as f:
                rom_bytes = io.BytesIO(f.read())

            # Convert flag_state to Flags object for randomizer
            randomizer_flags = self.state.flag_state.to_randomizer_flags()

            # Get seed as integer
            seed = int(self.seed_input.value)

            # Start timing
            start_time = time.time()

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
            self.state.randomized_rom_data = bytes(rom_data)
            base_name = os.path.splitext(os.path.basename(self.state.rom_info.filename))[0]

            # Build ZORA flagstring
            zora_flagstring = self.state.flag_state.to_flagstring()

            # Create filename
            self.state.randomized_rom_filename = f"{base_name}_zora_{zora_flagstring}_{self.seed_input.value}.nes"

            # Hide Step 2
            self.step2_container.visible = False
            self.step2_container.update()

            # Remove old ZORA settings card and Step 3 if they exist
            if self.state.zora_settings_card:
                self.page.controls.remove(self.state.zora_settings_card)
            if self.state.step3_container:
                self.page.controls.remove(self.state.step3_container)

            # Show ZORA settings card
            self.state.zora_settings_card = build_zora_settings_card(zora_flagstring,
                                                                     self.seed_input.value,
                                                                     self.state.flag_state)
            self.page.add(self.state.zora_settings_card)

            # Build and show Step 3
            download_handler = self.create_download_handler(self.state.randomized_rom_data,
                                                            self.state.randomized_rom_filename)

            # Extract ROM code for display
            rom_code = extract_code_from_rom_data(self.state.randomized_rom_data)

            # Calculate elapsed time
            elapsed_time = time.time() - start_time

            # Log randomization details
            log.info("=" * 70)
            log.info("RANDOMIZATION COMPLETE")
            log.info("=" * 70)
            log.info("INPUT ROM:")
            log.info(f"  Filename: {self.state.rom_info.filename}")
            if self.state.rom_info.rom_type == "vanilla":
                log.info(f"  Type: Vanilla")
                log.info(f"  Seed: n/a")
                log.info(f"  Flags: n/a")
            else:
                log.info(f"  Type: Randomized (base ROM)")
                log.info(f"  Seed: {self.state.rom_info.seed}")
                log.info(f"  Flags: {self.state.rom_info.flagstring}")
            log.info(f"  Code: {self.state.rom_info.code}")
            log.info("")
            log.info("OUTPUT ROM:")
            log.info(f"  Filename: {self.state.randomized_rom_filename}")
            log.info(f"  ZORA Seed: {self.seed_input.value}")
            log.info(f"  ZORA Flags: {zora_flagstring}")
            log.info(f"  Code: {rom_code}")
            log.info(f"  Generation Time: {elapsed_time:.2f} seconds")
            log.info("=" * 70)

            self.state.step3_container = build_step3_container(
                self.state.randomized_rom_data, self.state.randomized_rom_filename, zora_flagstring,
                self.seed_input.value, rom_code, self.platform, download_handler, self.clear_rom)
            self.page.add(self.state.step3_container)
            self.page.update()

            show_snackbar(self.page, "✅ Randomization complete! Download your ROM below.")

        except ValueError as ve:
            show_error_dialog(self.page, "Invalid Input",
                              f"Please enter a valid seed number:\n\n{str(ve)}")
        except Exception as ex:
            show_error_dialog(self.page, "Error",
                              f"An error occurred during randomization:\n\n{str(ex)}")

    # Upload progress handlers
    def on_vanilla_upload_progress(self, e: ft.FilePickerUploadEvent) -> None:
        """Handle vanilla ROM upload progress."""
        if e.progress == 1.0:
            # Upload complete
            self.upload_state['vanilla']['uploading'] = False
            # Get absolute path to uploaded file
            self.upload_state['vanilla']['uploaded_path'] = os.path.abspath(
                f"uploads/{e.file_name}")

            # Wait a moment for file to be fully written, then verify it exists
            time.sleep(0.1)

            if not os.path.exists(self.upload_state['vanilla']['uploaded_path']):
                show_error_dialog(
                    self.page, "Upload Error",
                    f"File was not uploaded successfully. Expected at: {self.upload_state['vanilla']['uploaded_path']}"
                )
                return

            # Now process the uploaded file
            self.process_vanilla_rom(self.upload_state['vanilla']['file_info'],
                                     self.upload_state['vanilla']['uploaded_path'])

    def on_randomized_upload_progress(self, e: ft.FilePickerUploadEvent) -> None:
        """Handle randomized ROM upload progress."""
        if e.progress == 1.0:
            # Upload complete
            self.upload_state['randomized']['uploading'] = False
            # Get absolute path to uploaded file
            self.upload_state['randomized']['uploaded_path'] = os.path.abspath(
                f"uploads/{e.file_name}")

            # Wait a moment for file to be fully written, then verify it exists
            time.sleep(0.1)

            if not os.path.exists(self.upload_state['randomized']['uploaded_path']):
                show_error_dialog(
                    self.page, "Upload Error",
                    f"File was not uploaded successfully. Expected at: {self.upload_state['randomized']['uploaded_path']}"
                )
                return

            # Now process the uploaded file
            self.process_randomized_rom(self.upload_state['randomized']['file_info'],
                                        self.upload_state['randomized']['uploaded_path'])

    # Button click handlers for file pickers
    def on_choose_vanilla_click(self, e) -> None:
        """Open file picker for vanilla ROM."""
        self.vanilla_file_picker.pick_files(allow_multiple=False, allowed_extensions=["nes"])

    def on_choose_randomized_click(self, e) -> None:
        """Open file picker for randomized ROM."""
        self.randomized_file_picker.pick_files(allow_multiple=False, allowed_extensions=["nes"])

    def on_choose_generate_vanilla_click(self, e) -> None:
        """Open file picker for vanilla ROM (generate option)."""
        self.generate_vanilla_file_picker.pick_files(allow_multiple=False,
                                                     allowed_extensions=["nes"])

    # Random seed generators
    def on_gen_random_seed_click(self, e) -> None:
        """Generate a random seed for Zelda Randomizer."""
        random_seed = random.randint(10000000, 99999999)
        self.gen_seed_input.value = str(random_seed)
        self.gen_seed_input.update()

    def on_random_seed_click(self, e) -> None:
        """Generate a random seed between 10000000 and 99999999."""
        random_seed = random.randint(10000000, 99999999)
        self.seed_input.value = str(random_seed)
        self.seed_input.update()


    # Accordion expand/collapse handlers
    def on_expand_all(self, e) -> None:
        """Expand all flag category panels."""
        for panel in self.expansion_panels_ref:
            panel.expanded = True
        self.page.update()

    def on_collapse_all(self, e) -> None:
        """Collapse all flag category panels."""
        for panel in self.expansion_panels_ref:
            panel.expanded = False
        self.page.update()
