"""Unit tests for validating hints in hints.py"""

import unittest
from .hints import COMMUNITY_HINTS, NUMERICAL_HINTS


class HintValidationTest(unittest.TestCase):
    """Test that all hints are properly formatted."""

    def test_all_hints_length(self):
        """Test that all parts of all hints are 22 characters or fewer."""
        # Test community hints
        for hint_type, hints in COMMUNITY_HINTS.items():
            for idx, hint in enumerate(hints):
                parts = hint.split('|')
                for part_num, part in enumerate(parts):
                    with self.subTest(source="COMMUNITY_HINTS", hint_type=hint_type, hint_idx=idx, part=part_num):
                        self.assertLessEqual(
                            len(part), 22,
                            f"{hint_type}[{idx}] part {part_num+1} too long ({len(part)} chars): '{part}'"
                        )

        # Test numerical hints
        for num, hints in NUMERICAL_HINTS.items():
            for idx, hint in enumerate(hints):
                parts = hint.split('|')
                for part_num, part in enumerate(parts):
                    with self.subTest(source="NUMERICAL_HINTS", num=num, hint_idx=idx, part=part_num):
                        self.assertLessEqual(
                            len(part), 22,
                            f"NUMERICAL_HINTS[{num}][{idx}] part {part_num+1} too long ({len(part)} chars): '{part}'"
                        )

    def test_all_hints_no_empty_parts(self):
        """Test that all hints have no empty parts."""
        # Test community hints
        for hint_type, hints in COMMUNITY_HINTS.items():
            for idx, hint in enumerate(hints):
                parts = hint.split('|')
                for part_num, part in enumerate(parts):
                    with self.subTest(source="COMMUNITY_HINTS", hint_type=hint_type, hint_idx=idx, part=part_num):
                        self.assertTrue(
                            part.strip(),
                            f"{hint_type}[{idx}] part {part_num+1} is empty or whitespace only"
                        )

        # Test numerical hints
        for num, hints in NUMERICAL_HINTS.items():
            for idx, hint in enumerate(hints):
                parts = hint.split('|')
                for part_num, part in enumerate(parts):
                    with self.subTest(source="NUMERICAL_HINTS", num=num, hint_idx=idx, part=part_num):
                        self.assertTrue(
                            part.strip(),
                            f"NUMERICAL_HINTS[{num}][{idx}] part {part_num+1} is empty or whitespace only"
                        )

    def test_all_hints_not_empty(self):
        """Test that both hint dictionaries are not empty."""
        self.assertGreater(len(COMMUNITY_HINTS), 0, "COMMUNITY_HINTS should not be empty")
        self.assertGreater(len(NUMERICAL_HINTS), 0, "NUMERICAL_HINTS should not be empty")

    def test_all_hints_uppercase(self):
        """Test that all hints use only uppercase characters."""
        # Test community hints
        for hint_type, hints in COMMUNITY_HINTS.items():
            for idx, hint in enumerate(hints):
                with self.subTest(source="COMMUNITY_HINTS", hint_type=hint_type, hint_idx=idx):
                    self.assertEqual(
                        hint, hint.upper(),
                        f"{hint_type}[{idx}] contains lowercase characters: '{hint}'"
                    )

        # Test numerical hints
        for num, hints in NUMERICAL_HINTS.items():
            for idx, hint in enumerate(hints):
                with self.subTest(source="NUMERICAL_HINTS", num=num, hint_idx=idx):
                    self.assertEqual(
                        hint, hint.upper(),
                        f"NUMERICAL_HINTS[{num}][{idx}] contains lowercase characters: '{hint}'"
                    )

    def test_no_accidental_string_concatenation(self):
        """Test that hints don't have accidental string concatenation from missing commas."""
        # Maximum reasonable length for a hint: 3 lines * 22 chars + 2 pipes = 68 chars
        # Add some buffer for safety
        MAX_HINT_LENGTH = 75
        MAX_LINES = 3  # Game only supports 3 lines

        # Test community hints
        for hint_type, hints in COMMUNITY_HINTS.items():
            for idx, hint in enumerate(hints):
                with self.subTest(source="COMMUNITY_HINTS", hint_type=hint_type, hint_idx=idx, check="length"):
                    self.assertLessEqual(
                        len(hint), MAX_HINT_LENGTH,
                        f"{hint_type}[{idx}] is suspiciously long ({len(hint)} chars). "
                        f"Check for missing comma between strings: '{hint}'"
                    )

                # Check number of lines
                num_lines = len(hint.split('|'))
                with self.subTest(source="COMMUNITY_HINTS", hint_type=hint_type, hint_idx=idx, check="num_lines"):
                    self.assertLessEqual(
                        num_lines, MAX_LINES,
                        f"{hint_type}[{idx}] has too many lines ({num_lines}). "
                        f"Check for missing comma between strings: '{hint}'"
                    )

        # Test numerical hints
        for num, hints in NUMERICAL_HINTS.items():
            for idx, hint in enumerate(hints):
                with self.subTest(source="NUMERICAL_HINTS", num=num, hint_idx=idx, check="length"):
                    self.assertLessEqual(
                        len(hint), MAX_HINT_LENGTH,
                        f"NUMERICAL_HINTS[{num}][{idx}] is suspiciously long ({len(hint)} chars). "
                        f"Check for missing comma between strings: '{hint}'"
                    )

                # Check number of lines
                num_lines = len(hint.split('|'))
                with self.subTest(source="NUMERICAL_HINTS", num=num, hint_idx=idx, check="num_lines"):
                    self.assertLessEqual(
                        num_lines, MAX_LINES,
                        f"NUMERICAL_HINTS[{num}][{idx}] has too many lines ({num_lines}). "
                        f"Check for missing comma between strings: '{hint}'"
                    )


if __name__ == "__main__":
    unittest.main()
