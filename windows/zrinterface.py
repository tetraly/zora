import tempfile
import time
import os


def main():
    """Read ZR parameters from temp file and process them.

    Expects zrinterface.txt in system temp directory with three lines:
    1. Vanilla ROM full filepath
    2. ZR flagstring
    3. ZR seed number
    """
    # Get system temp directory
    temp_dir = tempfile.gettempdir()
    input_file = os.path.join(temp_dir, "zrinterface.txt")

    # Read the file
    with open(input_file, 'r') as f:
        lines = f.readlines()

    vanilla_rom_path = lines[0].strip()
    zr_flagstring = lines[1].strip()
    zr_seed = lines[2].strip()

    # Print what we read
    print(f"Vanilla ROM Path: {vanilla_rom_path}")
    print(f"ZR Flagstring: {zr_flagstring}")
    print(f"ZR Seed: {zr_seed}")

    # For now, just wait 5 seconds
    time.sleep(5)

    return


if __name__ == "__main__":
    main()
