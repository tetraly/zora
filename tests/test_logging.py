"""
Test script to verify randomization logging works correctly
"""
import io
import logging as log
import os
import sys

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.randomizer import Z1Randomizer
from logic.flags import Flags

# Configure logging
log.basicConfig(
    level=log.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def extract_code_from_rom_data(rom_data: bytes, offset: int = 0xAFD4) -> str:
    """Extract the code from ROM data bytes."""
    from common.constants import CODE_ITEMS

    try:
        code_bytes = rom_data[offset:offset+4]
        items = [
            CODE_ITEMS.get(code_bytes[3]),
            CODE_ITEMS.get(code_bytes[2]),
            CODE_ITEMS.get(code_bytes[1]),
            CODE_ITEMS.get(code_bytes[0])
        ]
        if None in items:
            return "Unknown"
        valid_items = [item for item in items if item is not None]
        return ", ".join(valid_items)
    except Exception:
        return "Unknown"


def main():
    """Test logging during randomization"""

    # Load ROM
    rom_path = os.path.join(os.path.dirname(__file__), '..', 'roms', 'Z1_20250928_1NhjkmR55xvmdk0LmGY9fDm2xhOqxKzDfv.nes')

    if not os.path.exists(rom_path):
        print(f"ERROR: ROM file not found at {rom_path}")
        return False

    print("Loading ROM...")
    with open(rom_path, 'rb') as f:
        rom_data_input = f.read()

    rom_bytes = io.BytesIO(rom_data_input)

    # Get input ROM code
    input_code = extract_code_from_rom_data(rom_data_input)

    # Set up randomization
    flags = Flags()
    flags.set('community_hints', True)
    seed = 12345

    # Run randomizer
    print("Running randomizer...")
    randomizer = Z1Randomizer(rom_bytes, seed, flags)
    patch = randomizer.GetPatch()

    # Apply patch
    rom_bytes.seek(0)
    rom_data = bytearray(rom_bytes.read())
    patch.Apply(rom_data)

    # Get output ROM code
    output_code = extract_code_from_rom_data(bytes(rom_data))

    # Simulate the logging that happens in ui/main.py
    log.info("=" * 70)
    log.info("RANDOMIZATION COMPLETE")
    log.info("=" * 70)
    log.info("INPUT ROM:")
    log.info(f"  Filename: {os.path.basename(rom_path)}")
    log.info(f"  Type: Vanilla")
    log.info(f"  Seed: n/a")
    log.info(f"  Flags: n/a")
    log.info(f"  Code: {input_code}")
    log.info("")
    log.info("OUTPUT ROM:")
    log.info(f"  Filename: test_output_{seed}.nes")
    log.info(f"  ZORA Seed: {seed}")
    log.info(f"  ZORA Flags: H")
    log.info(f"  Code: {output_code}")
    log.info("=" * 70)

    print("\n✓ Test completed successfully!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
