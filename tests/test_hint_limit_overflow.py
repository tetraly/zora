"""
Test that HintWriter safeguard prevents overflow by using very long hints
"""
import random
import sys
import os

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.hint_writer import HintWriter
from logic.randomizer_constants import HintType


def test_hint_overflow_protection():
    """Test that HintWriter replaces hints with blanks when space runs out."""
    print("=" * 80)
    print("Testing Hint Overflow Protection")
    print("=" * 80)

    # Create writer and fill with very long hints to force overflow
    random.seed(42)
    writer = HintWriter()

    # Create maximum length hints (3 lines of 20 chars each)
    long_hint = [
        "ABCDEFGHIJKLMNOPQRST",
        "ABCDEFGHIJKLMNOPQRST",
        "ABCDEFGHIJKLMNOPQRST"
    ]

    # Try to set all 38 hints to max length
    for hint_num in range(1, HintWriter.NUM_HINT_SLOTS + 1):
        hint_type = HintType(hint_num)
        writer.SetHint(hint_type, long_hint)

    # Generate patch (should replace some with blanks)
    print("\nGenerating patch with 38 maximum-length hints...")
    patch = writer.GetPatch()

    # Find the maximum address written
    addresses = patch.GetAddresses()
    data_addresses = [addr for addr in addresses if addr >= 0x405C]

    if data_addresses:
        max_data_start = max(data_addresses)
        max_data_bytes = patch.GetData(max_data_start)
        max_data_end = max_data_start + len(max_data_bytes)
    else:
        max_data_end = 0x405C

    print(f"\nHint data range: 0x{HintWriter.HINT_DATA_START:04X} - 0x{max_data_end:04X}")
    print(f"Maximum allowed end: 0x{HintWriter.MAX_HINT_DATA_END:04X}")
    print(f"Space used: {max_data_end - HintWriter.HINT_DATA_START} bytes")

    # Verify we didn't exceed the limit
    print(f"\n✓ PASSED: Safeguard worked! Data ends at 0x{max_data_end:04X}")
    print("=" * 80)

    # Use assert instead of return for pytest
    assert max_data_end < HintWriter.MAX_HINT_DATA_END, \
        f"Hint data extends to 0x{max_data_end:04X}, exceeds limit 0x{HintWriter.MAX_HINT_DATA_END:04X}!"


if __name__ == "__main__":
    try:
        test_hint_overflow_protection()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
