"""HT-HINT-01 (hints-behavior.md @ 6c6506b): the tested room of every level, and a second-quest
level in a pair (data levels 2 and 3, 4 and 5, 7 and 8, each shown as its partner's number,
SH-NUM-03): its level-location entry and boss forms name the player level, and its
inside-dungeon walks cover its own rooms (owner-ruled deviation, docs/deviations.md) unless the
measurement switch asks for the original randomizer's."""
from functools import cache

import pytest

from zora.generate.pipeline import generate_rom, plan
from zora.generate.steps.hint_text import (
    INSIDE_MEANS,
    LEVEL_LOCATION_SLOTS,
    REGION_PHRASES,
    SLOT_COUNT,
    Form,
    ItemPlace,
    inside_dungeon_needs,
    is_paired,
    level_shown_as,
    region_of_screen,
    requirement_candidates,
    requirement_text,
    write_level_location_texts,
)
from zora.generate.steps.hint_text import tested_place as room_tested_for
from zora.generate.steps.item_shuffle_result import TrackedPlace
from zora.generate.steps.mixed_overworld_quest import door_screen
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.rooms import DARK_BIT, ITEM_MASK, Room
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.dungeon_quest import SECOND_QUEST_DUNGEONS_FLAGS

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

PARTNERS = {2: 3, 3: 2, 4: 5, 5: 4, 7: 8, 8: 7}
SEED = 3


@cache
def _prg0() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


@cache
def _second_quest_final() -> GameWorld:
    config = plan(SECOND_QUEST_DUNGEONS_FLAGS, SEED).config
    rom = generate_rom(SECOND_QUEST_DUNGEONS_FLAGS, SEED, remember_repo_base_rom()).rom
    return parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode))


def _unique_item_room(level: Level) -> Room:
    """A room of the level holding an item whose whole byte no other room of the level holds."""
    bytes_held = [room.item_byte for room in level.rooms]
    return next(room for room in level.rooms
                if room.item != Item.NOTHING and bytes_held.count(room.item_byte) == 1)


def _record(level: Level, room: int, item_byte: int) -> TrackedPlace:
    return TrackedPlace(item_byte & ITEM_MASK, level=level.level_num, room=room, item_byte=item_byte)


def test_the_tested_room_is_the_record_room_while_it_holds_the_recorded_byte() -> None:
    level = _prg0().levels[0]
    room = _unique_item_room(level)
    assert room_tested_for(_prg0().levels, _record(level, room.room_num, room.item_byte)) == ItemPlace(
        level, room=room.room_num)


def test_a_moved_item_is_tested_in_the_first_room_holding_its_whole_byte() -> None:
    level = _prg0().levels[0]
    room = _unique_item_room(level)
    elsewhere = next(other.room_num for other in level.rooms if other.item_byte != room.item_byte)
    assert room_tested_for(_prg0().levels, _record(level, elsewhere, room.item_byte)) == ItemPlace(
        level, room=room.room_num)


def test_no_room_holding_the_byte_or_a_byte_of_80_or_more_forms_no_tested_room() -> None:
    level = _prg0().levels[0]
    room = _unique_item_room(level)
    held = {other.item_byte for other in level.rooms}
    missing = next(value for value in range(DARK_BIT) if value not in held)
    assert room_tested_for(_prg0().levels, _record(level, room.room_num, missing)) is None
    dark = room.item_byte | DARK_BIT
    assert room_tested_for(_prg0().levels, _record(level, room.room_num, dark)) is None


def test_an_item_cellar_record_keeps_its_cellar() -> None:
    level = _prg0().levels[0]
    record = TrackedPlace(Item.BOW, level=level.level_num, cellar=0x7F)
    assert room_tested_for(_prg0().levels, record) == ItemPlace(level, cellar=0x7F)


def test_the_second_quest_pairs_show_their_partners_numbers() -> None:
    levels = _prg0().levels_2q
    assert [level.level_num for level in levels if is_paired(level)] == sorted(PARTNERS)
    assert all(level_shown_as(levels, level.level_num).level_num == PARTNERS.get(level.level_num, level.level_num)
               for level in levels)
    assert not any(is_paired(level) for level in _prg0().levels)


@pytest.mark.parametrize("data_level", sorted(PARTNERS))
def test_the_reference_walks_enter_only_a_paired_levels_own_start_room(data_level: int) -> None:
    """Owner-ruled deviation: the measurement switch off gives the original randomizer's walks, which
    enter only data level d's start room; ZORA's own walk enters the start room with the sword."""
    level = _prg0().levels_2q[data_level - 1]
    start = ItemPlace(level, room=level.entrance_room)
    other = ItemPlace(level, room=next(room for room in level.room_nums if room != level.entrance_room))
    assert inside_dungeon_needs(start, Item.BOW, walk_own_rooms=False) == [
        form for means, form in INSIDE_MEANS if means != Item.BOW]
    assert inside_dungeon_needs(other, Item.BOW, walk_own_rooms=False) == []
    assert inside_dungeon_needs(start, Item.BOW) == []


def test_a_second_quest_level_location_entry_names_the_player_level_and_its_door() -> None:
    world = _second_quest_final()
    texts: list[list[str] | None] = [None] * SLOT_COUNT
    sentences: list[str | None] = [None] * SLOT_COUNT
    write_level_location_texts(world, texts, sentences)
    for player_level, slot in enumerate(LEVEL_LOCATION_SLOTS, start=1):
        data_level = PARTNERS.get(player_level, player_level)
        door = door_screen(world.overworld, data_level)
        assert door is not None
        assert sentences[slot] == f"LEVEL-{player_level} LIES {REGION_PHRASES[region_of_screen(door)]}."


def test_a_boss_form_names_the_player_level_the_item_is_in() -> None:
    world = _second_quest_final()
    candidates = requirement_candidates(world, [(Item.BOW, 2), (Item.RAFT, 6)])
    bosses = [candidate for candidate in candidates if candidate.form == Form.BOSS]
    assert [(candidate.item, candidate.level) for candidate in bosses] == [(Item.BOW, 3), (Item.RAFT, 6)]
    assert "LEVEL-3" in " ".join(requirement_text(bosses[0]))
