"""Remove Maps, All Maps and All Compasses (B92 to B94; features-behavior.md FP-MAP-01, FP-MAP-02) in the
emulator, each a pair: CP-5, and CP-5 with the setting on, the same seed (the same world, FL-SEED-01).

  - Remove Maps, a map lying in a room: with B92 off the room shows the map when entered; with it on,
    nothing.
  - Remove Maps, a map a room releases when its last foe dies (trigger 7, ZORA's guard): with B92 off
    the map appears once the foes are gone; with it on (the room's trigger now 1) nothing appears and
    the shutters open as they did. The same ROM with that room's trigger set back to 7 shows item 3,
    the magical sword, which is why the guard is there (FP-MAP-01's MUST).
  - All Maps and All Compasses: a new save file holds every level's map, or compass, before any is taken."""
from functools import cache

import pytest

from tests.emulator import CUR_OPENED_DOORS, INV_MAP, ITEMS, OBJ_STATE, ROOM_ITEM_SLOT
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_progressive_emulator import ITEM_ACTIVE, ROOM_ITEM_ID
from zora.generate.pipeline import generate_rom
from zora.model.enums import Item, RoomAction
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

CP5 = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
B92_ON = "BtH0Hdj8LFhsBw!L!jIWWh3fmMqsjAMeny0rUJ3A"      # FP-MAP-01's Check strings
B93_ON = "Zdp0qu9P0kpBvgbm87GTyntdh!Xges99NmGHUJ3A"
B94_ON = "1huR2WgSC2EAB5uR0XJAMJ7MXUtd6RxVf8C!ZUJ3A"
SEEDS = range(100001, 100009)
SETTLE_FRAMES = 120
MAGICAL_SWORD_CODE = 0x03               # what PRG0 shows for item $03 once a trigger switches it on
INV_COMPASS, INV_COMPASS_9, INV_MAP_9 = ITEMS + 0x10, ITEMS + 0x12, ITEMS + 0x13
EVERY_LEVEL_1_TO_8, LEVEL_9 = 0xFF, 0x01


@cache
def rom(flags: str, seed: int) -> bytes:
    return generate_rom(flags, seed, remember_repo_base_rom()).rom


def map_room(trigger_7: bool) -> tuple[int, int, int]:
    """(seed, level, room): the first map room of a level in CP-5's ROMs whose trigger is 7, or is not."""
    for seed in SEEDS:
        for level in parse_rom(rom(CP5, seed)).levels:
            for room in level.rooms:
                if room.item is Item.MAP and (room.room_action is RoomAction.ALL_DEAD_ITEM) == trigger_7:
                    return seed, level.level_num, room.room_num
    raise AssertionError(f"no map room with trigger 7 = {trigger_7} in seeds {SEEDS.start}-{SEEDS.stop - 1}")


def item_shown(console: Console) -> int | None:
    """The room item's code once it is active, or None."""
    return console.emu[ROOM_ITEM_ID] if console.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_ACTIVE else None


def test_a_lying_map_is_gone() -> None:
    seed, level, room = map_room(trigger_7=False)
    off, on = Console(rom(CP5, seed)), Console(rom(B92_ON, seed))
    off.enter_room(level, room)
    on.enter_room(level, room)
    assert item_shown(off) == Item.MAP
    assert item_shown(on) is None


def test_a_released_map_is_gone_and_the_shutters_open() -> None:
    seed, level, room = map_room(trigger_7=True)
    world = parse_rom(rom(B92_ON, seed))
    shipped = next(lvl for lvl in world.levels if lvl.level_num == level).block.room(room)
    assert shipped.item is Item.NOTHING and shipped.room_action is RoomAction.ALL_DEAD
    shipped.room_action = RoomAction.ALL_DEAD_ITEM
    unguarded = serialize_to_rom(world, rom(B92_ON, seed))
    shown, doors = {}, {}
    for name, image in (("off", rom(CP5, seed)), ("on", rom(B92_ON, seed)), ("unguarded", unguarded)):
        console = Console(image)
        console.enter_room(level, room)
        assert item_shown(console) is None, name
        console.clear_monsters()
        console.emu.run(SETTLE_FRAMES)
        shown[name], doors[name] = item_shown(console), console.emu[CUR_OPENED_DOORS]
    assert shown == {"off": Item.MAP, "on": None, "unguarded": MAGICAL_SWORD_CODE}
    assert doors["on"] == doors["off"]


@pytest.mark.parametrize(("flags", "maps", "compasses"),
                         ((CP5, False, False), (B93_ON, True, False), (B94_ON, False, True)),
                         ids=["off", "all-maps", "all-compasses"])
def test_a_new_file_holds_every_map_or_compass(flags: str, maps: bool, compasses: bool) -> None:
    console = Console(rom(flags, SEEDS[0]))
    held = (console.emu[INV_MAP], console.emu[INV_MAP_9]), (console.emu[INV_COMPASS], console.emu[INV_COMPASS_9])
    every, none = (EVERY_LEVEL_1_TO_8, LEVEL_9), (0, 0)
    assert held == (every if maps else none, every if compasses else none)
