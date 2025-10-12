import tempfile
import os
import subprocess
import sys


def main():
    """Interface with Zelda Randomizer via zrinterface.exe.

    Expects ZeldaMessage.tmp in system temp directory with three lines:
    1. Vanilla ROM full filepath
    2. ZR flagstring
    3. ZR seed number

    This function writes the temp file and calls zrinterface.exe to automate
    the Zelda Randomizer application.
    """
    # Get system temp directory
    temp_dir = tempfile.gettempdir()
    input_file = os.path.join(temp_dir, "zrinterface.txt")

    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        return False

    # Read the parameters from the input file
    with open(input_file, 'r') as f:
        lines = f.readlines()

    if len(lines) < 3:
        print("Error: Input file must contain 3 lines (ROM path, flagstring, seed)")
        return False

    vanilla_rom_path = lines[0].strip()
    zr_flagstring = lines[1].strip()
    zr_seed = lines[2].strip()

    # Validate vanilla ROM exists
    if not os.path.exists(vanilla_rom_path):
        print(f"Error: Vanilla ROM not found: {vanilla_rom_path}")
        return False

    # Print what we're processing
    print(f"Vanilla ROM Path: {vanilla_rom_path}")
    print(f"ZR Flagstring: {zr_flagstring}")
    print(f"ZR Seed: {zr_seed}")

    # Write the temp file that zrinterface.exe expects (ZeldaMessage.tmp)
    temp_file = os.path.join(temp_dir, "ZeldaMessage.tmp")
    with open(temp_file, 'w') as f:
        f.write(f"{vanilla_rom_path}\n")
        f.write(f"{zr_flagstring}\n")
        f.write(f"{zr_seed}\n")

    print(f"Created temp file: {temp_file}")

    # Get the directory where this script is located
    # When running as PyInstaller bundle, use sys._MEIPASS
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        script_dir = sys._MEIPASS
    else:
        # Running in normal Python environment
        script_dir = os.path.dirname(os.path.abspath(__file__))

    zrinterface_exe = os.path.join(script_dir, "zrinterface.exe")

    # Check if zrinterface.exe exists
    if not os.path.exists(zrinterface_exe):
        print(f"Error: zrinterface.exe not found at: {zrinterface_exe}")
        return False

    print(f"Launching zrinterface.exe...")

    # Call zrinterface.exe
    try:
        result = subprocess.run([zrinterface_exe], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print("Successfully executed zrinterface.exe")
            print(result.stdout)
            return True
        else:
            print(f"zrinterface.exe returned error code: {result.returncode}")
            if result.stderr:
                print(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("Error: zrinterface.exe timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Error executing zrinterface.exe: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
