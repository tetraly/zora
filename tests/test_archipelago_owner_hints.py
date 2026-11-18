"""Owner-named hints for other players' items (owner approval 2026-11-18)."""
import unittest
from types import SimpleNamespace

import pytest

from zora import archipelago
from zora.generate.finish import FOREIGN as FOREIGN_VALUE
from zora.generate.finish import hinted_foreign_places
from zora.generate.steps.hint_text import (
    Form, ItemNames, Requirement, has_shown_character, item_location_sentence, requirement_text,
)
from zora.rom.base_rom import BASE_ROM_PATH

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


def place(name: str, level: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, level=level)


PLACES = [place("L1 a", 1), place("L1 b", 1), place("L2 a", 2), place("L3 a", 3), place("Coast"),
          place("White Sword Cave"), place("Elsewhere")]
OWNERS = {name: ("GOB", "HAMMER") for name in ("L1 a", "L1 b", "L2 a", "L3 a", "Coast", "White Sword Cave", "Elsewhere")}
ALL_FOREIGN = {p.name: FOREIGN_VALUE for p in PLACES}


class HintedPlacesTest(unittest.TestCase):
    def test_only_hintable_places_are_kept(self) -> None:
        hinted = hinted_foreign_places(PLACES, ALL_FOREIGN, OWNERS)
        # level 1 holds two other-player items, so neither is named; a place no hint reads is left out
        self.assertEqual(hinted, {"L2 a": 2, "L3 a": 3, "Coast": "coast", "White Sword Cave": "white sword"})

    def test_own_items_are_not_hinted(self) -> None:
        assignment = {**ALL_FOREIGN, "L2 a": "Candle"}
        self.assertNotIn("L2 a", hinted_foreign_places(PLACES, assignment, OWNERS))

    def test_name_with_no_shown_character_falls_back(self) -> None:
        owners = {**OWNERS, "L2 a": ("ゴブ", "HAMMER"), "L3 a": ("GOB", ":::")}
        hinted = hinted_foreign_places(PLACES, ALL_FOREIGN, owners)
        self.assertNotIn("L2 a", hinted)
        self.assertNotIn("L3 a", hinted)
        self.assertIn("Coast", hinted)

    def test_has_shown_character(self) -> None:
        self.assertTrue(has_shown_character("Gob-Z2"))
        self.assertFalse(has_shown_character("ゴブ :: "))
        self.assertFalse(has_shown_character("   "))


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")
def test_recipe_rebuild_matches_generation() -> None:
    """The ROM rebuilt from the filtered recipe is the one generation wrote."""
    from tests.test_archipelago_client_ram import CASE, SEED
    from tests.test_archipelago_beta_smoke import FLAG_CASES
    from zora.rom.base_rom import remember_repo_base_rom

    rom = remember_repo_base_rom()
    result = archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, rom)
    names = [p.name for p in result.state.places]
    assignment = {name: archipelago.FOREIGN for name in names}
    owners = {name: ("Gob-Z2", "HAMMER") for name in names}
    generated = archipelago.finish(result, assignment, (), None, ap_name=b"ZORA1_test", foreign_owners=owners)
    recipe = archipelago.recipe(result, assignment, (), None, ap_name=b"ZORA1_test", foreign_owners=owners)
    hinted = hinted_foreign_places(result.state.places, assignment, owners)
    assert set(recipe["foreignOwners"]) == set(hinted)
    assert set(recipe["foreignOwners"]) <= set(names)
    assert archipelago.rom_from_recipe(recipe, rom) == generated
