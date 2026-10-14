"""Archipelago's WorldTestBase on several of ZORA's option sets (each generates a whole ZORA world and
checks every location is reachable and the goal beatable), and the color settings' values."""
import unittest
from typing import Any, ClassVar

from . import ZoraTestBase


class TestDefaults(ZoraTestBase):
    pass


class TestLevel4SwordEntrance(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "progressive_items": "on", "extra_candles": "off", "add_l4_sword": "level_2",
        "level_9_entrance_sword": "level_4_sword"}


class TestMixedShapesDungeons(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "dungeon_quest": "mixed_plus_shapes", "shuffle_dungeon_start_room": "on",
        "remove_most_open_stairs": "on", "book_to_understand_old_men": "on"}


class TestSecondQuestCosmetics(ZoraTestBase):
    options: ClassVar[dict[str, Any]] = {
        "dungeon_quest": "second_quest", "green_tunic": 0x2A, "level_word": "lair",
        "boss_sound_word": "random_word", "start_inventory": {"Raft": 1, "Bombs": 2}}


class TestColorSettings(unittest.TestCase):
    def test_color_options_take_palette_numbers(self) -> None:
        """Each color setting's option values are the NES palette numbers themselves, so an
        unquoted 0x29 in a YAML (the number 41) is palette value 41, never a list position."""
        from ..options import SETTING_CLASSES
        for key in ("green_tunic", "blue_ring_tunic", "red_ring_tunic", "hearts"):
            option = SETTING_CLASSES[key]
            self.assertEqual(sorted(option.options.values())[:3], [0, 1, 2], key)
            self.assertNotIn(0x0D, option.options.values(), key)
            self.assertEqual(option.from_any(0x29).value, 0x29, key)
            self.assertEqual(option.from_any("0x2a").value, 0x2A, key)
