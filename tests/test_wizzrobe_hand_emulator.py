"""Wizzrobes Shoot Wallmasters (ZORA flag wizzrobes_shoot_wallmasters; asm/flags2/wizzrobe-hand/) in the
emulator, from the baseline with Shuffle Enemy Groups on and with it off (the flag turns it on, and the
deal puts the Wizzrobes with the Wallmasters). A new game is put in a room holding a Wizzrobe by the level-load
and enter-room modes. While no shot is near, Link is invincible and the Wizzrobes' bodies are moved off him
whenever one is, so only a shot can reach him.

  - Drawn: each Wizzrobe shot ($58, $59) is drawn as two sprites whose pattern data is PRG0's open hand.
  - A hit: half a heart (the Wallmaster's damage), then mode 3 takes Link to the level's entrance room
    with his hearts kept.
  - A hit on his last half heart: mode $11, death.
  - The Magical Shield: Link faces each shot as it comes; a shot vanishes beside him, no damage and no
    return."""
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_DIR,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    Emulator,
    Mode,
)
from tests.needs import needs_base_rom
from tests.test_wizzrobe_hand import HAND_TILES, OPEN_HAND, with_groups
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.generate.pipeline import generate_rom
from zora.generate.steps.shuffle_enemy_groups import ENEMY_BANK_FIRST_TILE
from zora.model.enums import Enemy
from zora.model.sprites import TILE_BYTES, PatternBlock
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 0
ON = zora_flags.encode(zora_flags.ZoraFlags(wizzrobes_shoot_wallmasters=ThreeState.ON))
IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
RETURN_MODE = 0x03                       # the Wallmaster's: unfurl the level from its entrance
DEATH_MODE = 0x11
HEART_VALUES, HEART_PARTIAL = 0x66F, 0x670
THREE_HEARTS, FULL, HALF, EMPTY = 0x22, 0xFF, 0x7F, 0x00
LAST_HEART = 0x20                        # three containers, the last heart filling
INV_MAGIC_SHIELD = ITEMS + 0x1F
LINK_INVINCIBILITY_TIMER = 0x4F0
INVINCIBLE = 0xFF
MONSTER_SLOTS = range(1, 0x0C)
SHOTS = {0x58, 0x59}                     # ShootMagicShot's types, blue and red
WIZZROBE_TYPES = {int(Enemy.RED_WIZZROBE), int(Enemy.BLUE_WIZZROBE)}
NEAR, BODY_NEAR = 24, 40
PARKED = 0x30, 0x5D                      # a Wizzrobe moved off Link
OPPOSITE = {1: 2, 2: 1, 4: 8, 8: 4}
SPRITES, OAM_RECORDS, HIDDEN_Y = 0x200, 64, 0xEF
SPRITE_TABLE_BIT, PAIR = 1, 0xFE
ROOM_FRAMES = 4000


@cache
def hand_rom(shuffled: bool) -> tuple[bytes, int, int, int]:
    """A finished ROM with the flag on: its bytes, a level and room holding a Wizzrobe, and the level's
    entrance room."""
    rom = generate_rom(with_groups(shuffled), SEED, remember_repo_base_rom(), zora_flag_string=ON).rom
    for level in parse_rom(rom).levels:
        for room in level.rooms:
            if level.level_num and int(room.enemy) in WIZZROBE_TYPES and not room.has_monster_bit:
                return rom, level.level_num, room.room_num, level.entrance_room
    raise AssertionError("no Wizzrobe room")


def start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def enter_room(rom: bytes, level: int, room: int) -> Emulator:
    emu = Emulator(rom)
    emu.new_game()
    emu[CUR_LEVEL] = level
    start_mode(emu, Mode.LOAD_LEVEL)
    wait_for_play(emu)
    emu[ROOM_ID] = room
    start_mode(emu, ENTER_ROOM_MODE)
    wait_for_play(emu)
    return emu


def shots(emu: Emulator) -> dict[int, tuple[int, int, int]]:
    return {slot: (emu[OBJ_X + slot], emu[OBJ_Y + slot], emu[OBJ_DIR + slot])
            for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot] in SHOTS}


def is_near(emu: Emulator, x: int, y: int, reach: int) -> bool:
    return abs(x - emu[OBJ_X]) < reach and abs(y - emu[OBJ_Y]) < reach


def step(emu: Emulator, hearts: tuple[int, int] | None) -> tuple[dict[int, tuple[int, int, int]], bool]:
    """One frame in which only a shot can touch Link; `hearts` refilled while none is near."""
    flying = shots(emu)
    near = any(is_near(emu, x, y, NEAR) for x, y, _direction in flying.values())
    emu[LINK_INVINCIBILITY_TIMER] = 0 if near else INVINCIBLE
    if near:
        for slot in MONSTER_SLOTS:
            if emu[OBJ_TYPE + slot] in WIZZROBE_TYPES and is_near(emu, emu[OBJ_X + slot], emu[OBJ_Y + slot],
                                                                  BODY_NEAR):
                emu[OBJ_X + slot], emu[OBJ_Y + slot] = PARKED
    elif hearts is not None:
        emu[HEART_VALUES], emu[HEART_PARTIAL] = hearts
    emu.run(1)
    return flying, near


def sprite_data(emu: Emulator, tile: int) -> bytes:
    start = (tile & SPRITE_TABLE_BIT) * 0x1000 + (tile & PAIR) * TILE_BYTES
    return emu.pattern_tables()[start:start + 2 * TILE_BYTES]


@cache
def prg0_hand() -> bytes:
    """PRG0's open hand: the 8x16 sprites $AC and $AE of its tier-0 enemy bank."""
    tiles = parse_rom(remember_repo_base_rom()).sprites.read_tiles(
        PatternBlock.UWSP127, (OPEN_HAND - ENEMY_BANK_FIRST_TILE) * TILE_BYTES, HAND_TILES)
    return b"".join(tiles)


@pytest.mark.parametrize("shuffled", [True, False], ids=["b42-on", "b42-off"])
def test_the_shot_is_drawn_as_the_hand(shuffled: bool) -> None:
    rom, level, room, _entrance = hand_rom(shuffled)
    emu = enter_room(rom, level, room)
    drawn = 0
    for _ in range(ROOM_FRAMES):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1)
        oam = emu.sprites()
        for x, y, _direction in shots(emu).values():
            tiles = sorted(oam[record * 4 + 1] for record in range(OAM_RECORDS)
                           if oam[record * 4] < HIDDEN_Y and abs(oam[record * 4 + 3] - x) <= 8
                           and 0 <= oam[record * 4] - y <= 3 and oam[record * 4 + 1] not in (0xB4, 0xB6))
            if len(tiles) == 2 and tiles[1] == tiles[0] + 2:
                assert sprite_data(emu, tiles[0]) + sprite_data(emu, tiles[1]) == prg0_hand()
                drawn += 1
        if drawn >= 20:
            break
    assert drawn >= 20


def first_contact(rom: bytes, level: int, room: int, hearts: tuple[int, int], shield: bool = False) -> Emulator:
    """The emulator on the frame a shot first touches Link (his mode leaves play, or, with the shield, a
    shot vanishes beside him)."""
    emu = enter_room(rom, level, room)
    if shield:
        emu[INV_MAGIC_SHIELD] = 1
    emu[HEART_VALUES], emu[HEART_PARTIAL] = hearts
    for _ in range(ROOM_FRAMES):
        if shield:
            flying = shots(emu)
            if flying:
                closest = min(flying.values(), key=lambda shot: abs(shot[0] - emu[OBJ_X]) + abs(shot[1] - emu[OBJ_Y]))
                emu[OBJ_DIR] = OPPOSITE.get(closest[2], emu[OBJ_DIR])
        flying, near = step(emu, hearts)
        if emu.mode != Mode.PLAY:
            return emu
        if shield and near and any(emu[OBJ_TYPE + slot] not in SHOTS and is_near(emu, x, y, NEAR)
                                   for slot, (x, y, _direction) in flying.items()):
            return emu
    raise AssertionError("no shot reached Link")


@pytest.mark.parametrize("shuffled", [True, False], ids=["b42-on", "b42-off"])
def test_a_hit_takes_link_to_the_entrance_with_his_hearts(shuffled: bool) -> None:
    rom, level, room, entrance = hand_rom(shuffled)
    emu = first_contact(rom, level, room, (THREE_HEARTS, FULL))
    assert emu.mode == RETURN_MODE
    assert (emu[HEART_VALUES], emu[HEART_PARTIAL]) == (THREE_HEARTS, HALF)
    wait_for_play(emu)
    assert (emu[CUR_LEVEL], emu[ROOM_ID]) == (level, entrance)
    assert (emu[HEART_VALUES], emu[HEART_PARTIAL]) == (THREE_HEARTS, HALF)


@pytest.mark.parametrize("shuffled", [True, False], ids=["b42-on", "b42-off"])
def test_a_hit_on_the_last_half_heart_kills(shuffled: bool) -> None:
    rom, level, room, _entrance = hand_rom(shuffled)
    emu = first_contact(rom, level, room, (LAST_HEART, HALF))
    assert emu.mode == DEATH_MODE
    assert emu[HEART_PARTIAL] == EMPTY


@pytest.mark.parametrize("shuffled", [True, False], ids=["b42-on", "b42-off"])
def test_the_magical_shield_blocks_the_hand_and_it_vanishes(shuffled: bool) -> None:
    rom, level, room, _entrance = hand_rom(shuffled)
    emu = first_contact(rom, level, room, (THREE_HEARTS, FULL), shield=True)
    assert emu.mode == Mode.PLAY
    assert (emu[HEART_VALUES], emu[HEART_PARTIAL]) == (THREE_HEARTS, FULL)
    assert (emu[CUR_LEVEL], emu[ROOM_ID]) == (level, room)
