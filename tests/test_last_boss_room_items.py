"""VA-REJ-20 and SH-MAP-05's trigger-3 landing. VA-REJ-20: after the gate, level 9's last-boss
shutter rooms (trigger 3) keep only a key, bombs, five rupees or (Ganon's room) the Triforce of
Power; anything else moves over the small item of a random other level-9 room, which is lost; no
receiving room restarts the pass."""
from functools import cache

import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.errors import GenerationFailure
from zora.generate.pipeline import generate_rom
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.move_last_boss_room_items import (
    LEADING_DISCARDS,
    SMALL_ITEMS,
    STAYING_ITEMS,
    move_last_boss_room_items,
    receiving_rooms,
)
from zora.generate.steps.move_map_near_entrance import CANDIDATE_ITEMS, move_map_near_entrance
from zora.model.enums import Enemy, Item, RoomAction
from zora.model.levels import Level
from zora.model.rooms import Room
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

DISCARDS = [0] * LEADING_DISCARDS
SEEDS = range(24)


@cache
def finished_level9(seed: int) -> Level:
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, verify_base_rom().read_bytes()).rom)
    return world.levels[8]


def last_boss_rooms(level9: Level) -> list[Room]:
    """Level 9's trigger-3 rooms other than Ganon's."""
    return [room for room in level9.rooms
            if room.room_action == RoomAction.LAST_BOSS and room.enemy != Enemy.THE_BEAST]


def fresh_level9() -> Level:
    return parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 0, verify_base_rom().read_bytes()).rom).levels[8]


@pytest.mark.parametrize("seed", SEEDS)
def test_finished_last_boss_rooms_hold_only_small_items_or_the_moved_map(seed: int) -> None:
    """The map may still land there afterwards (SH-MAP-05); the compass never does."""
    for room in last_boss_rooms(finished_level9(seed)):
        assert room.item in SMALL_ITEMS | {Item.NOTHING, Item.MAP}, f"seed {seed} room {room.room_num:02X}"


def test_a_compass_moves_over_the_drawn_small_item_keeping_each_rooms_bits() -> None:
    level9 = fresh_level9()
    shutter = sorted(level9.rooms, key=lambda room: room.room_num)[0]
    shutter.room_action, shutter.item, shutter.is_dark = RoomAction.LAST_BOSS, Item.COMPASS, True
    for room in level9.rooms:
        moving = room.room_action == RoomAction.LAST_BOSS and room.item not in STAYING_ITEMS
        if room is not shutter and (room.item == Item.COMPASS or moving):
            room.item = Item.KEY                  # one move only: one scripted draw
    candidates = receiving_rooms(level9)
    assert len(candidates) >= 2
    assert [room.room_num for room in candidates] == sorted((room.room_num for room in candidates), reverse=True)
    receiver = candidates[1]
    receiver_trigger, receiver_dark = receiver.room_action, receiver.is_dark
    items_before = sum(room.item != Item.NOTHING for room in level9.rooms)
    move_last_boss_room_items(level9, ScriptedRng([*DISCARDS, 1]))
    assert shutter.item == Item.NOTHING and shutter.is_dark and shutter.room_action == RoomAction.LAST_BOSS
    assert receiver.item == Item.COMPASS
    assert (receiver.room_action, receiver.is_dark) == (receiver_trigger, receiver_dark)
    assert sum(room.item != Item.NOTHING for room in level9.rooms) == items_before - 1   # the small item is lost


@pytest.mark.parametrize("item", [Item.NOTHING, Item.KEY, Item.BOMBS, Item.FIVE_RUPEES, Item.TRIFORCE_OF_POWER])
def test_allowed_items_stay_and_only_the_discards_are_drawn(item: Item) -> None:
    level9 = fresh_level9()
    for room in level9.rooms:
        if room.room_action == RoomAction.LAST_BOSS and room.item not in STAYING_ITEMS:
            room.item = item
    before = [(room.room_num, room.item_info, room.secret_info) for room in level9.rooms]
    move_last_boss_room_items(level9, ScriptedRng(DISCARDS))      # a further draw would exhaust it
    assert [(room.room_num, room.item_info, room.secret_info) for room in level9.rooms] == before


def test_no_receiving_room_restarts_the_pass() -> None:
    level9 = fresh_level9()
    for room in level9.rooms:
        if room.item in SMALL_ITEMS:
            room.item = Item.NOTHING
    shutter = sorted(level9.rooms, key=lambda room: room.room_num)[0]
    shutter.room_action, shutter.item = RoomAction.LAST_BOSS, Item.MAP
    with pytest.raises(GenerationFailure):
        move_last_boss_room_items(level9, ScriptedRng(DISCARDS))


class CountingRng(Rng):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.draws = 0

    def below(self, n: int) -> int:
        self.draws += 1
        return super().below(n)


@pytest.mark.parametrize("seed", range(4))
def test_the_map_move_draws_its_trigger_test_whatever_the_trigger(seed: int) -> None:
    """SH-MAP-05: one number for the four-in-five test even when the chosen room is on another
    trigger; a last-boss room keeps trigger 3 and the map stays behind its shutters."""
    level9 = fresh_level9()
    candidates = [room for room in level9.rooms if room.item in CANDIDATE_ITEMS and room.item != Item.MAP]
    for room in candidates:
        room.room_action = RoomAction.LAST_BOSS
    rng = CountingRng(seed)
    move_map_near_entrance(level9, rng)
    assert rng.draws == 2                     # the weighted room draw, then the trigger test
    map_room = next(room for room in level9.rooms if room.item == Item.MAP)
    assert map_room.room_action == RoomAction.LAST_BOSS
