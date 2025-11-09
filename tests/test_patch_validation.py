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


def test_patch_with_description():
    """Test that descriptions work correctly"""
    print("\nTest 6: Patch with description")

    patch = Patch()
    patch.AddData(0x100, [0xFF, 0xEE], description="Test recorder warp destinations")

    description = patch.GetDescription(0x100)
    assert description == "Test recorder warp destinations", f"Expected description 'Test recorder warp destinations', got '{description}'"

    print("  ✓ Description stored and retrieved correctly")


def test_patch_with_description_and_expected_data():
    """Test that both description and expected data work together"""
    print("\nTest 7: Patch with description and expected data")

    patch = Patch()
    patch.AddData(0x100, [0xFF, 0xEE],
                  expected_original_data=[0xAA, 0xBB],
                  description="Level 1 entrance patch")

    # Create mock ROM data with different data
    rom_data = bytearray(0x200)
    rom_data[0x100] = 0x12
    rom_data[0x101] = 0x34

    # Apply patch (simulating cli.py logic)
    for address in patch.GetAddresses():
        patch_data = patch.GetData(address)
        expected_data = patch.GetExpectedData(address)
        description = patch.GetDescription(address)

        # Validate expected data if provided
        if expected_data is not None:
            actual_data = []
            for offset in range(len(expected_data)):
                if address + offset < len(rom_data):
                    actual_data.append(rom_data[address + offset])

            if actual_data != expected_data:
                desc_str = f" ({description})" if description else ""
                print(f"  ✓ Mismatch detected with description: {desc_str}")
                logging.warning(
                    f"Expected data mismatch at address 0x{address:04X}{desc_str}:\n"
                    f"  Expected: {' '.join(f'{b:02X}' for b in expected_data)}\n"
                    f"  Actual:   {' '.join(f'{b:02X}' for b in actual_data)}\n"
                    f"  Patching with: {' '.join(f'{b:02X}' for b in patch_data)}"
                )

        for offset, byte in enumerate(patch_data):
            rom_data[address + offset] = byte

    print("  ✓ Description and expected data work together")


def test_hex_string_with_description():
    """Test that AddDataFromHexString works with description"""
    print("\nTest 8: AddDataFromHexString with description")

    patch = Patch()
    patch.AddDataFromHexString(0x100, "FF EE DD",
                                expected_original_data="12 34 56",
                                description="Hex patch for text speed")

    expected_data = patch.GetExpectedData(0x100)
    assert expected_data == [0x12, 0x34, 0x56], "Expected data should be [0x12, 0x34, 0x56]"

    description = patch.GetDescription(0x100)
    assert description == "Hex patch for text speed", f"Expected description 'Hex patch for text speed', got '{description}'"

    print("  ✓ AddDataFromHexString with description and expected data works correctly")


def test_patch_combination_preserves_descriptions():
    """Test that descriptions are preserved when combining patches"""
    print("\nTest 9: Patch combination preserves descriptions")

    patch1 = Patch()
    patch1.AddData(0x100, [0xFF], expected_original_data=[0x11], description="Patch 1")

    patch2 = Patch()
    patch2.AddData(0x200, [0xEE], expected_original_data=[0x22], description="Patch 2")

    combined = patch1 + patch2

    assert combined.GetExpectedData(0x100) == [0x11]
    assert combined.GetExpectedData(0x200) == [0x22]
    assert combined.GetDescription(0x100) == "Patch 1"
    assert combined.GetDescription(0x200) == "Patch 2"

    print("  ✓ Descriptions and expected data preserved when combining patches")


def test_descriptions_not_mixed_up():
    """Test that descriptions stay with their correct addresses"""
    print("\nTest 10: Descriptions stay with correct addresses")

    # Create patches with different addresses, data, expected data, and descriptions
    patch = Patch()
    patch.AddData(0x1000, [0xAA], expected_original_data=[0x10], description="Level 1 entrance")
    patch.AddData(0x2000, [0xBB], expected_original_data=[0x20], description="Level 2 entrance")
    patch.AddData(0x3000, [0xCC], expected_original_data=[0x30], description="Level 3 entrance")
    patch.AddData(0x4000, [0xDD], expected_original_data=[0x40], description="Recorder warp")

    # Verify each address has the correct data, expected data, and description
    assert patch.GetData(0x1000) == [0xAA], "0x1000 should have data [0xAA]"
    assert patch.GetExpectedData(0x1000) == [0x10], "0x1000 should have expected [0x10]"
    assert patch.GetDescription(0x1000) == "Level 1 entrance", "0x1000 should have description 'Level 1 entrance'"

    assert patch.GetData(0x2000) == [0xBB], "0x2000 should have data [0xBB]"
    assert patch.GetExpectedData(0x2000) == [0x20], "0x2000 should have expected [0x20]"
    assert patch.GetDescription(0x2000) == "Level 2 entrance", "0x2000 should have description 'Level 2 entrance'"

    assert patch.GetData(0x3000) == [0xCC], "0x3000 should have data [0xCC]"
    assert patch.GetExpectedData(0x3000) == [0x30], "0x3000 should have expected [0x30]"
    assert patch.GetDescription(0x3000) == "Level 3 entrance", "0x3000 should have description 'Level 3 entrance'"

    assert patch.GetData(0x4000) == [0xDD], "0x4000 should have data [0xDD]"
    assert patch.GetExpectedData(0x4000) == [0x40], "0x4000 should have expected [0x40]"
    assert patch.GetDescription(0x4000) == "Recorder warp", "0x4000 should have description 'Recorder warp'"

    print("  ✓ All descriptions correctly associated with their addresses")


def test_combined_patches_descriptions_not_mixed():
    """Test that when combining patches, descriptions stay with correct addresses"""
    print("\nTest 11: Combined patches maintain correct description associations")

    # Create first patch with multiple entries
    patch1 = Patch()
    patch1.AddData(0x1000, [0xAA], expected_original_data=[0x10], description="Patch1 at 0x1000")
    patch1.AddData(0x2000, [0xBB], expected_original_data=[0x20], description="Patch1 at 0x2000")

    # Create second patch with different entries
    patch2 = Patch()
    patch2.AddData(0x3000, [0xCC], expected_original_data=[0x30], description="Patch2 at 0x3000")
    patch2.AddData(0x4000, [0xDD], expected_original_data=[0x40], description="Patch2 at 0x4000")

    # Combine patches
    combined = patch1 + patch2

    # Verify all descriptions are correct
    assert combined.GetData(0x1000) == [0xAA]
    assert combined.GetExpectedData(0x1000) == [0x10]
    assert combined.GetDescription(0x1000) == "Patch1 at 0x1000", f"Expected 'Patch1 at 0x1000', got '{combined.GetDescription(0x1000)}'"

    assert combined.GetData(0x2000) == [0xBB]
    assert combined.GetExpectedData(0x2000) == [0x20]
    assert combined.GetDescription(0x2000) == "Patch1 at 0x2000", f"Expected 'Patch1 at 0x2000', got '{combined.GetDescription(0x2000)}'"

    assert combined.GetData(0x3000) == [0xCC]
    assert combined.GetExpectedData(0x3000) == [0x30]
    assert combined.GetDescription(0x3000) == "Patch2 at 0x3000", f"Expected 'Patch2 at 0x3000', got '{combined.GetDescription(0x3000)}'"

    assert combined.GetData(0x4000) == [0xDD]
    assert combined.GetExpectedData(0x4000) == [0x40]
    assert combined.GetDescription(0x4000) == "Patch2 at 0x4000", f"Expected 'Patch2 at 0x4000', got '{combined.GetDescription(0x4000)}'"

    print("  ✓ Combined patches maintain correct description associations")


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
        test_patch_with_description()
        test_patch_with_description_and_expected_data()
        test_hex_string_with_description()
        test_patch_combination_preserves_descriptions()
        test_descriptions_not_mixed_up()
        test_combined_patches_descriptions_not_mixed()

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
