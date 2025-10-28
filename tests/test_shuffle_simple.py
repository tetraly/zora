#!/usr/bin/env python3
"""
Simple test script to demonstrate item shuffling using Z1Randomizer.
"""
import io
from logic.randomizer import Z1Randomizer
from logic.flags import Flags

def load_rom(rom_path):
    """Load ROM file into bytes"""
    with open(rom_path, 'rb') as f:
        return f.read()

def main():
    print("=" * 80)
    print("ITEM SHUFFLE DEMONSTRATION")
    print("=" * 80)

    # Load ROM
    rom_path = './uploads/Legend of Zelda, The (USA) (Rev 1).nes'
    print(f"\nLoading ROM: {rom_path}")
    rom_data = load_rom(rom_path)

    # Set up flags
    print("\nConfiguring flags:")
    flags = Flags()
    flags.set('full_major_item_shuffle', True)
    flags.set('allow_important_items_in_level_nine', True)  # Allow all items in L9
    # flags.set('heart_container_in_each_level_1_8', True)  # Disable for now to test basic shuffle
    print("  ✓ full_major_item_shuffle = True")
    print("  ✓ allow_important_items_in_level_nine = True")

    # Set seed
    seed = 12345
    print(f"\nUsing seed: {seed}")

    # Create randomizer and run - this should work since the UI uses it successfully
    print("\nRunning randomization (this creates and shuffles items)...")
    rom_bytes = io.BytesIO(rom_data)
    randomizer = Z1Randomizer(rom_bytes, seed, flags)
    patch = randomizer.GetPatch()

    print("✓ Randomization complete!")
    print(f"\nGenerated patch hash: {patch.GetHashCode()}")

    print("\n" + "=" * 80)
    print("Note: The shuffle happened internally during Z1Randomizer construction.")
    print("To see item locations, we would need to hook into the ItemRandomizer")
    print("before and after the shuffle occurs.")
    print("=" * 80)

if __name__ == "__main__":
    main()
