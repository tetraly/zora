"""Add Extra Bosses (B79; post-shapes-b2.md PS-BOSS-07) in the emulator, on CP-5 with B79 on: an extra
boss stands in an ordinary room with that room's shutters and trigger. Entered, the room holds the boss's
object and draws its sprites from the level's boss bank; once the room's monsters are gone, a room
whose trigger opens on all dead opens its shutters; and no extra boss roars (the end pass, PS-MONRD-07).

The rooms are those of levels 1 to 8 that hold a boss but no heart container and whose doors include a
shutter, in a level with more bosses than its own (extra bosses, then, not the level's boss)."""
from functools import cache

import pytest

from tests.emulator import CUR_OPENED_DOORS, OBJ_TYPE, SHUTTER_TRIGGER
from tests.needs import needs_base_rom
from tests.test_asnb_emulator import MONSTER_SLOTS
from tests.test_assignment_emulator import Console
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.shuffle_bosses import BOSS_TIERS
from zora.model.enums import BossSound, Item, RoomAction, WallType
from zora.model.rooms import Room
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 1
BOSS_CODES = frozenset(code for tier in BOSS_TIERS for code in tier)
MONSTER_BIT_CODE = 0x40
LEVELS = range(1, 9)
OWN_BOSSES = 2                       # a level's own boss (and its Gleeok-free twin at most)
SPAWN_FRAMES = 60
CLEAR_FRAMES = 90
SPRITE_RECORDS, HIDDEN_Y = 64, 0xEF


def boss_code(room: Room) -> int:
    return room.enemy & (MONSTER_BIT_CODE - 1) | (MONSTER_BIT_CODE if room.has_monster_bit else 0)


@cache
def extra_boss_rom() -> bytes:
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B79": ThreeState.ON}))
    return generate_rom(flags, SEED, remember_repo_base_rom()).rom


@cache
def extra_boss_rooms() -> tuple[tuple[int, Room], ...]:
    found = []
    for level in parse_rom(extra_boss_rom()).levels:
        if level.level_num not in LEVELS:
            continue
        owned = {room.room_num: room for room in level.block.rooms if room.room_num in level.room_nums}
        bosses = [room for room in owned.values() if boss_code(room) in BOSS_CODES]
        if len(bosses) <= OWN_BOSSES:
            continue
        found += [(level.level_num, room) for room in bosses if room.item != Item.HEART_CONTAINER
                  and WallType.SHUTTER_DOOR in (room.walls.north, room.walls.east, room.walls.south, room.walls.west)]
    return tuple(found)


def test_some_level_has_extra_bosses_behind_shutters() -> None:
    assert extra_boss_rooms()


def test_no_extra_boss_roars() -> None:
    assert all(room.boss_sound == BossSound(0) for _level, room in extra_boss_rooms())


def test_an_extra_boss_appears_and_its_room_opens_once_cleared() -> None:
    level, room = next((level, room) for level, room in extra_boss_rooms() if room.room_action == RoomAction.ALL_DEAD)
    console = Console(extra_boss_rom())
    console.enter_room(level, room.room_num)
    console.emu.run(SPAWN_FRAMES)
    assert any(console.emu[OBJ_TYPE + slot] == boss_code(room) for slot in MONSTER_SLOTS)
    sprites = console.emu.sprites()
    assert any(sprites[record * 4] < HIDDEN_Y for record in range(SPRITE_RECORDS))
    assert not console.emu[CUR_OPENED_DOORS]
    console.clear_monsters()
    console.emu.run(CLEAR_FRAMES)
    assert console.emu[SHUTTER_TRIGGER] or console.emu[CUR_OPENED_DOORS]
