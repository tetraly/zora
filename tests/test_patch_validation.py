"""
Test script to verify patch expected data validation
"""
import io
import logging
import os
import sys

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.patch import Patch

# Set up logging to capture warnings
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s - %(message)s'
)


def test_patch_without_expected_data():
    """Test that patches work normally without expected data"""
    print("Test 1: Patch without expected data")

    patch = Patch()
    patch.AddData(0x100, [0xFF, 0xEE, 0xDD])

    # Create mock ROM data
    rom_data = bytearray(0x200)
    rom_data[0x100] = 0x00
    rom_data[0x101] = 0x00
    rom_data[0x102] = 0x00

    # Apply patch
    for address in patch.GetAddresses():
        patch_data = patch.GetData(address)
        expected_data = patch.GetExpectedData(address)

        assert expected_data is None, "Expected no expected data"

        for offset, byte in enumerate(patch_data):
            rom_data[address + offset] = byte

    # Verify patch was applied
    assert rom_data[0x100] == 0xFF
    assert rom_data[0x101] == 0xEE
    assert rom_data[0x102] == 0xDD

    print("  ✓ Patch applied successfully without expected data")


def test_patch_with_matching_expected_data():
    """Test that patches work when expected data matches"""
    print("\nTest 2: Patch with matching expected data")

    patch = Patch()
    patch.AddData(0x100, [0xFF, 0xEE], expected_original_data=[0x12, 0x34])

    # Create mock ROM data with matching expected data
    rom_data = bytearray(0x200)
    rom_data[0x100] = 0x12
    rom_data[0x101] = 0x34

    # Apply patch (simulating cli.py logic)
    for address in patch.GetAddresses():
        patch_data = patch.GetData(address)
        expected_data = patch.GetExpectedData(address)

        assert expected_data == [0x12, 0x34], "Expected data should be [0x12, 0x34]"

        # Validate expected data if provided
        if expected_data is not None:
            actual_data = []
            for offset in range(len(expected_data)):
                if address + offset < len(rom_data):
                    actual_data.append(rom_data[address + offset])

            if actual_data != expected_data:
                logging.warning(
                    f"Expected data mismatch at address 0x{address:04X}:\n"
                    f"  Expected: {' '.join(f'{b:02X}' for b in expected_data)}\n"
                    f"  Actual:   {' '.join(f'{b:02X}' for b in actual_data)}"
                )
            else:
                print(f"  ✓ Expected data matched at address 0x{address:04X}")

        for offset, byte in enumerate(patch_data):
            rom_data[address + offset] = byte

    # Verify patch was applied
    assert rom_data[0x100] == 0xFF
    assert rom_data[0x101] == 0xEE

    print("  ✓ Patch applied successfully with matching expected data")


def test_patch_with_mismatched_expected_data():
    """Test that warnings are logged when expected data doesn't match"""
    print("\nTest 3: Patch with mismatched expected data (should log warning)")

    patch = Patch()
    patch.AddData(0x100, [0xFF, 0xEE], expected_original_data=[0xAA, 0xBB])

    # Create mock ROM data with different data
    rom_data = bytearray(0x200)
    rom_data[0x100] = 0x12
    rom_data[0x101] = 0x34

    # Apply patch (simulating cli.py logic)
    for address in patch.GetAddresses():
        patch_data = patch.GetData(address)
        expected_data = patch.GetExpectedData(address)

        # Validate expected data if provided
        if expected_data is not None:
            actual_data = []
            for offset in range(len(expected_data)):
                if address + offset < len(rom_data):
                    actual_data.append(rom_data[address + offset])

            if actual_data != expected_data:
                print(f"  ✓ Expected mismatch detected!")
                logging.warning(
                    f"Expected data mismatch at address 0x{address:04X}:\n"
                    f"  Expected: {' '.join(f'{b:02X}' for b in expected_data)}\n"
                    f"  Actual:   {' '.join(f'{b:02X}' for b in actual_data)}\n"
                    f"  Patching with: {' '.join(f'{b:02X}' for b in patch_data)}"
                )

        for offset, byte in enumerate(patch_data):
            rom_data[address + offset] = byte

    # Verify patch was still applied despite mismatch
    assert rom_data[0x100] == 0xFF
    assert rom_data[0x101] == 0xEE

    print("  ✓ Warning logged and patch still applied")


def test_hex_string_with_expected_data():
    """Test that AddDataFromHexString works with expected data"""
    print("\nTest 4: AddDataFromHexString with expected data")

    patch = Patch()
    patch.AddDataFromHexString(0x100, "FF EE DD", expected_original_data="12 34 56")

    expected_data = patch.GetExpectedData(0x100)
    assert expected_data == [0x12, 0x34, 0x56], "Expected data should be [0x12, 0x34, 0x56]"

    patch_data = patch.GetData(0x100)
    assert patch_data == [0xFF, 0xEE, 0xDD], "Patch data should be [0xFF, 0xEE, 0xDD]"

    print("  ✓ AddDataFromHexString with expected data works correctly")


def test_patch_combination():
    """Test that expected data is preserved when combining patches"""
    print("\nTest 5: Patch combination preserves expected data")

    patch1 = Patch()
    patch1.AddData(0x100, [0xFF], expected_original_data=[0x11])

    patch2 = Patch()
    patch2.AddData(0x200, [0xEE], expected_original_data=[0x22])

    combined = patch1 + patch2

    assert combined.GetExpectedData(0x100) == [0x11]
    assert combined.GetExpectedData(0x200) == [0x22]

    print("  ✓ Expected data preserved when combining patches")


def main():
    """Run all tests"""
    print("=" * 70)
    print("PATCH VALIDATION TESTS")
    print("=" * 70)

    try:
        test_patch_without_expected_data()
        test_patch_with_matching_expected_data()
        test_patch_with_mismatched_expected_data()
        test_hex_string_with_expected_data()
        test_patch_combination()

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED ✓")
        print("=" * 70)
        return True
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
