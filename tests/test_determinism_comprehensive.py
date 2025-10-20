"""
Comprehensive determinism test - runs same seed multiple times to catch any non-determinism
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


def test_determinism_multiple_runs(seed, flags, num_runs=5):
    """Test that the same seed produces the same hash multiple times"""

    print(f"\n{'=' * 70}")
    print(f"Testing seed {seed} with {num_runs} runs")
    print(f"{'=' * 70}")

    rom_data = load_rom()
    if rom_data is None:
        return False

    hashes = []
    patches_data = []

    # Run multiple times
    for run_num in range(num_runs):
        print(f"\nRun {run_num + 1}/{num_runs}...", end=" ")
        rom_bytes = io.BytesIO(rom_data)
        randomizer = Z1Randomizer(rom_bytes, seed, flags)
        patch = randomizer.GetPatch()
        hash_val = patch.GetHashCode()
        hashes.append(hash_val)

        # Also store all patch addresses and data for deep comparison
        patch_addresses = sorted(patch.GetAddresses())
        patch_dict = {addr: patch._data[addr] for addr in patch_addresses}
        patches_data.append(patch_dict)

        print(f"Hash: {hash_val}")

    # Check if all hashes match
    first_hash = hashes[0]
    all_match = all(h == first_hash for h in hashes)

    if all_match:
        print(f"\n✓ SUCCESS: All {num_runs} runs produced the same hash")
        return True
    else:
        print(f"\n✗ FAILURE: Hashes differ across runs!")
        for i, h in enumerate(hashes):
            print(f"  Run {i + 1}: {h}")

        # Deep comparison to find differences
        print("\nComparing patch data...")
        first_patch = patches_data[0]
        for i, patch_dict in enumerate(patches_data[1:], start=2):
            if patch_dict != first_patch:
                print(f"\nDifferences found between run 1 and run {i}:")
                all_addrs = set(first_patch.keys()) | set(patch_dict.keys())
                diff_count = 0
                for addr in sorted(all_addrs):
                    val1 = first_patch.get(addr)
                    val2 = patch_dict.get(addr)
                    if val1 != val2:
                        diff_count += 1
                        if diff_count <= 10:  # Show first 10 differences
                            print(f"  Address 0x{addr:04X}: {val1} vs {val2}")
                if diff_count > 10:
                    print(f"  ... and {diff_count - 10} more differences")

        return False


def main():
    """Test multiple seeds with various flag configurations"""

    print("=" * 70)
    print("COMPREHENSIVE DETERMINISM TEST")
    print("=" * 70)

    # Test with a specific seed and various flag configurations
    test_seed = 592843  # Use the seed from the user's issue

    # Test configurations
    test_configs = []

    # Default flags
    test_configs.append(("Default flags", Flags()))

    # With maze randomization (this triggers HintWriter reseeding)
    flags_mazes = Flags()
    flags_mazes.set('randomize_lost_hills', True)
    flags_mazes.set('randomize_dead_woods', True)
    test_configs.append(("Maze randomization", flags_mazes))

    # With community hints (this uses random.shuffle in HintWriter)
    flags_hints = Flags()
    flags_hints.set('community_hints', True)
    test_configs.append(("Community hints", flags_hints))

    # With both mazes and hints
    flags_both = Flags()
    flags_both.set('randomize_lost_hills', True)
    flags_both.set('randomize_dead_woods', True)
    flags_both.set('community_hints', True)
    test_configs.append(("Mazes + hints", flags_both))

    # With many flags
    flags_many = Flags()
    flags_many.set('progressive_items', True)
    flags_many.set('randomize_level_text', True)
    flags_many.set('community_hints', True)
    flags_many.set('randomize_lost_hills', True)
    flags_many.set('randomize_dead_woods', True)
    flags_many.set('shuffle_shop_arrows', True)
    flags_many.set('shuffle_shop_candle', True)
    test_configs.append(("Many flags", flags_many))

    all_passed = True

    for config_name, flags in test_configs:
        print(f"\n{'#' * 70}")
        print(f"Configuration: {config_name}")
        print(f"{'#' * 70}")

        try:
            result = test_determinism_multiple_runs(test_seed, flags, num_runs=5)
            if not result:
                all_passed = False
        except Exception as e:
            print(f"\n✗ ERROR testing configuration '{config_name}':")
            print(f"  {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    # Summary
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
