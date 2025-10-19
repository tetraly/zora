"""
Test that HintWriter safeguard actually replaces hints with blanks
by temporarily reducing the limit
"""
import sys
import os

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.hint_writer import HintWriter
from logic.randomizer_constants import HintType


def test_safeguard_triggers():
    """Test that the safeguard actually triggers by using a small limit."""
    print("=" * 80)
    print("Testing Safeguard Trigger")
    print("=" * 80)

    # Create writer
    writer = HintWriter(seed=42)

    # Temporarily reduce the limit to force the safeguard to trigger
    original_limit = HintWriter.MAX_HINT_DATA_END
    HintWriter.MAX_HINT_DATA_END = 0x4100  # Very small limit

    print(f"\nTemporarily set limit to: 0x{HintWriter.MAX_HINT_DATA_END:04X}")

    # Fill with community hints
    writer.FillWithCommunityHints()

    # Generate patch
    print("Generating patch with reduced limit...")
    import logging
    logging.basicConfig(level=logging.WARNING)
    patch = writer.GetPatch()

    # Restore original limit
    HintWriter.MAX_HINT_DATA_END = original_limit

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
    print(f"Test limit was: 0x4100")
    print(f"Actual limit: 0x{original_limit:04X}")

    # Verify we didn't exceed the test limit
    if max_data_end >= 0x4100:
        print(f"\n❌ FAILED: Safeguard didn't trigger! Data extends to 0x{max_data_end:04X}")
        return False
    else:
        print(f"\n✓ PASSED: Safeguard triggered correctly! Data ends at 0x{max_data_end:04X}")

    print("=" * 80)
    return True


if __name__ == "__main__":
    success = test_safeguard_triggers()
    sys.exit(0 if success else 1)
