"""Owner-named hints for other players' items (owner approval 2026-11-18)."""
import unittest

from zora.generate.steps.hint_text import (
    Form, ItemNames, Requirement, item_location_sentence, requirement_text,
)

FOREIGN = 0x18
LABELS = ((3, "Gob-Z2", "HAMMER"), ("coast", "Gob-DWR", "WINGS"), ("white sword", "Gob-DWR", "MAGIC KEY"),
          (5, "A-VERY-LONG-NAME", "AN EXTREMELY LONG ITEM NAME THAT WILL NOT FIT AT ALL"))
NAMES = ItemNames(foreign_code=FOREIGN, foreign_labels=LABELS)


class OwnerHintTest(unittest.TestCase):
    def test_level_sentence_names_owner(self) -> None:
        self.assertEqual(item_location_sentence(FOREIGN, 3, NAMES), "Gob-Z2'S HAMMER AWAITS IN LEVEL-3.")

    def test_unlabelled_level_is_generic(self) -> None:
        self.assertEqual(item_location_sentence(FOREIGN, 4, NAMES), "ANOTHER PLAYER'S ITEM AWAITS IN LEVEL-4.")

    def test_too_long_falls_back(self) -> None:
        self.assertEqual(item_location_sentence(FOREIGN, 5, NAMES), "ANOTHER PLAYER'S ITEM AWAITS IN LEVEL-5.")

    def test_coast_ladder_names_owner(self) -> None:
        lines = requirement_text(Requirement(Form.LADDER, FOREIGN), NAMES)
        self.assertEqual(" ".join(lines), "Gob-DWR'S WINGS NEEDS THE LADDER")

    def test_white_sword_cave_names_owner(self) -> None:
        lines = requirement_text(Requirement(Form.RECORDER, FOREIGN, white_sword_cave=True), NAMES)
        self.assertEqual(lines, ["THE CAVE WITH", "Gob-DWR'S MAGIC KEY", "NEEDS THE RECORDER"])

    def test_no_labels_keeps_generic_wording(self) -> None:
        plain = ItemNames(foreign_code=FOREIGN)
        lines = requirement_text(Requirement(Form.LADDER, FOREIGN), plain)
        self.assertEqual(" ".join(lines), "ANOTHER PLAYER'S ITEM NEEDS THE LADDER")
