"""
Test script to verify that the same seed produces deterministic results
(i.e., the same hash every time)
"""
import io
import sys
import os

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.randomizer import Z1Randomizer
from logic.flags import Flags


def load_rom():
    """Load ROM file into BytesIO"""
    rom_path = os.path.join(os.path.dirname(__file__), '..', 'roms', 'Z1_20250928_1NhjkmR55xvmdk0LmGY9fDm2xhOqxKzDfv.nes')

    if not os.path.exists(rom_path):
        print(f"ERROR: ROM file not found at {rom_path}")
        return None

    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    return rom_data


def test_determinism_with_seed(seed, flags):
    """Test that the same seed produces the same hash twice"""

    print(f"\n{'=' * 70}")
    print(f"Testing seed: {seed}")
    print(f"{'=' * 70}")

    rom_data = load_rom()
    if rom_data is None:
        return False

    # First run
    print("\nFirst randomization...")
    rom_bytes_1 = io.BytesIO(rom_data)
    randomizer_1 = Z1Randomizer(rom_bytes_1, seed, flags)
    patch_1 = randomizer_1.GetPatch()
    hash_1 = patch_1.GetHashCode()
    print(f"Hash 1: {hash_1}")

    # Second run with same seed
    print("\nSecond randomization with same seed...")
    rom_bytes_2 = io.BytesIO(rom_data)
    randomizer_2 = Z1Randomizer(rom_bytes_2, seed, flags)
    patch_2 = randomizer_2.GetPatch()
    hash_2 = patch_2.GetHashCode()
    print(f"Hash 2: {hash_2}")

    # Compare
    if hash_1 == hash_2:
        print(f"\n✓ SUCCESS: Hashes match! Seed {seed} is deterministic.")
        return True
    else:
        print(f"\n✗ FAILURE: Hashes differ! Seed {seed} is NOT deterministic.")
        print(f"  Hash 1: {hash_1}")
        print(f"  Hash 2: {hash_2}")
        return False


def main():
    """Test multiple seeds with different flag configurations"""

    print("=" * 70)
    print("DETERMINISM TEST - Same Seed Should Produce Same Hash")
    print("=" * 70)

    # Test with multiple seeds
    test_seeds = [12345, 42, 99999]

    # Test configurations
    test_configs = [
        ("Default flags (all off)", Flags()),
    ]

    # Test with progressive items
    flags_progressive = Flags()
    flags_progressive.set('progressive_items', True)
    test_configs.append(("With progressive items", flags_progressive))

    # Test with text randomization (often a source of non-determinism)
    flags_with_text = Flags()
    flags_with_text.set('randomize_level_text', True)
    test_configs.append(("With text randomization", flags_with_text))

    # Test with hints (another potential source of non-determinism)
    flags_with_hints = Flags()
    flags_with_hints.set('community_hints', True)
    test_configs.append(("With community hints", flags_with_hints))

    # Test with Lost Hills/Dead Woods (uses randomization)
    flags_with_mazes = Flags()
    flags_with_mazes.set('randomize_lost_hills', True)
    flags_with_mazes.set('randomize_dead_woods', True)
    test_configs.append(("With maze randomization", flags_with_mazes))

    # Test with multiple flags
    flags_many = Flags()
    flags_many.set('progressive_items', True)
    flags_many.set('randomize_level_text', True)
    flags_many.set('community_hints', True)
    flags_many.set('shuffle_shop_arrows', True)
    test_configs.append(("With multiple flags", flags_many))

    all_results = []

    for config_name, flags in test_configs:
        print(f"\n{'#' * 70}")
        print(f"Testing configuration: {config_name}")
        print(f"{'#' * 70}")

        results = []
        for seed in test_seeds:
            try:
                result = test_determinism_with_seed(seed, flags)
                results.append((seed, result))
            except Exception as e:
                print(f"\n✗ ERROR testing seed {seed}:")
                print(f"  {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                results.append((seed, False))

        all_results.append((config_name, results))

    # Summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)

    all_passed = True
    for config_name, results in all_results:
        print(f"\n{config_name}:")
        for seed, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  Seed {seed:6d}: {status}")
            if not result:
                all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ ALL TESTS PASSED - Randomizer is deterministic!")
    else:
        print("✗ SOME TESTS FAILED - Randomizer has non-deterministic behavior!")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
