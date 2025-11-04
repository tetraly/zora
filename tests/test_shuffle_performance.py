"""Performance comparison between simple shuffle and constraint-based shuffle."""

import pytest
import io
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.randomizer import Z1Randomizer
from logic.flags import Flags


def test_shuffle_performance_comparison():
    """Compare runtime of simple shuffle vs constraint-based shuffle."""
    pytest.skip("TODO")

    print("\n" + "="*80)
    print("Cave Shuffle Performance Comparison")
    print("="*80)

    # Test with multiple seeds
    test_seeds = [12345, 99999, 42, 777, 592843]

    for seed in test_seeds:
        print(f"\nSeed: {seed}")

        # Load ROM
        with open('roms/z1-prg1.nes', 'rb') as f:
            rom_bytes = io.BytesIO(f.read())

        # Create flags with cave shuffling enabled
        flags = Flags()
        flags.overworld_quest = 'first_quest'
        flags.extra_raft_blocks = False
        

        # Generate ROM and capture timing from logs
        start_time = time.time()
        randomizer = Z1Randomizer(rom_bytes, seed, flags)

        # Enable debug logging to see timing
        import logging
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')

        patch = randomizer.GetPatch()
        total_time = time.time() - start_time

        print(f"  Total generation time: {total_time*1000:.2f}ms")

    print("\n" + "="*80)
    print("Note: Check debug output above for 'Simple shuffle took X.XXms'")
    print("="*80)


if __name__ == "__main__":
    test_shuffle_performance_comparison()
