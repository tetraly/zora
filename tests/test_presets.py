"""The Vanilla preset (owner, 2026-10-17): every flag Off, the closest to the original game ZORA
produces (zora/flags/presets.py VANILLA_FLAGS)."""
from collections import Counter
from functools import cache

from zora.flags import form
from zora.flags.codec import encode
from zora.flags.fields import (
    DUNGEON_ROOM_SHUFFLE,
    HINT_STYLE,
    STARTING_HEARTS,
    DungeonRoomShuffle,
    HintStyle,
    Settings,
    ThreeState,
)
from zora.flags.presets import VANILLA_FLAGS, ZORA_PRESETS
from zora.generate.pipeline import generate_rom
from zora.generate.steps.move_last_boss_room_items import SMALL_ITEMS
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave
from zora.rom.base_rom import verify_base_rom
from zora.rom.parse.rom_file import parse_rom

ORIGINAL_STARTING_HEARTS = 2                 # C16's index for 3 hearts, the original game's
# The toggles whose off ZORA does not produce, left on
NOT_PRODUCED_OFF = ("B18", "B20", "B32", "B33", "B35", "B43")


@cache
def base() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def vanilla_world(seed: int) -> GameWorld:
    return parse_rom(generate_rom(VANILLA_FLAGS, seed, base()).rom)


def test_the_string_is_every_flag_off_where_zora_produces_it() -> None:
    settings = Settings.zero().updated(
        options={HINT_STYLE.id: HintStyle.COMMUNITY, DUNGEON_ROOM_SHUFFLE.id: DungeonRoomShuffle.WITHIN_EACH_DUNGEON,
                 STARTING_HEARTS.id: ORIGINAL_STARTING_HEARTS},
        toggles=dict.fromkeys(NOT_PRODUCED_OFF, ThreeState.ON))
    assert encode(settings) == VANILLA_FLAGS
    assert form.value_label(STARTING_HEARTS, ORIGINAL_STARTING_HEARTS) == "3"
    assert ZORA_PRESETS["Vanilla"] == (VANILLA_FLAGS, "")
    assert form.generation_refusals(VANILLA_FLAGS, "") == []
    entry = next(entry for entry in form.presets() if entry["name"] == "Vanilla")
    assert entry["available"] and entry["flags"] == VANILLA_FLAGS and entry["zoraFlags"] == ""


def test_a_vanilla_seed_keeps_the_original_overworld_and_each_levels_rooms() -> None:
    """The overworld (every screen's cave, monsters and layout) and the caves' items are the
    original's; each level holds its own rooms and items, rearranged by Dungeon Room Shuffle. Level 9
    may hold fewer small items: VA-REJ-20 moves an item out of a room beside Zelda's that opens only
    with Ganon's death over another room's small item (owner ruling, 2026-10-17; seed 2's bombs)."""
    original = parse_rom(base())
    for seed in (1, 2):
        world = vanilla_world(seed)
        for screen, kept in zip(world.overworld.screens, original.overworld.screens, strict=True):
            assert (screen.destination, screen.enemy_spec, screen.screen_code) == \
                (kept.destination, kept.enemy_spec, kept.screen_code), screen.screen_num
        for destination in (Destination.WOOD_SWORD_CAVE, Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE):
            cave, kept_cave = (w.overworld.get_cave(destination, ItemCave) for w in (world, original))
            assert cave is not None and kept_cave is not None
            assert (cave.item, cave.heart_requirement) == (kept_cave.item, kept_cave.heart_requirement)
        for level, kept_level in zip(world.levels, original.levels, strict=True):
            assert {room.room_num for room in level.rooms} == {room.room_num for room in kept_level.rooms}
            items, kept_items = (Counter(room.item for room in rooms) for rooms in (level.rooms, kept_level.rooms))
            if level.level_num == 9:
                lost = kept_items - items
                assert items - kept_items == Counter({Item.NOTHING: lost.total()}) and set(lost) <= SMALL_ITEMS
            else:
                assert items == kept_items
