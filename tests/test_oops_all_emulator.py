"""Oops All Enemies and Oops All Bosses in the emulator (docs/design/oops-all.md): ZORA's
MVP-baseline output with one extra on, Link put in a room by the level-load and enter-room modes,
invincible, while every sprite tile drawn is recorded with its pattern data.

  - Wizzrobes, Bouncers and Keese: a count-8 family room in a level of each enemy bank draws
    every sprite tile with the same pattern data in all three banks, the family's own tiles
    being its base-ROM tiles; the Wizzrobes' magic shots (object types $58 and $59,
    ShootMagicShot) are among them.
  - Eight Vires, struck one by one with the magical sword: play goes on and the room empties,
    with at least one red Keese per Vire. (Measured: 13 Keese from 8 Vires, with all 11 monster
    slots full at the peak, so 3 splits found no slot.)
  - Dodongos in a level that Shuffle Bosses had put on boss block C: the level now loads block
    A, and the Dodongos draw their base-ROM tiles."""
from collections import Counter
from dataclasses import dataclass
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
    Button,
    Direction,
    Emulator,
    Mode,
)
from zora.flags import zora_flags
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OopsAllBosses, OopsAllEnemies, ZoraFlags
from zora.generate.pipeline import build, finish, plan
from zora.generate.steps.oops_all import DODONGO, FAMILIES, FAMILY_SPRITES, family_slots
from zora.generate.steps.shuffle_enemy_groups import ENEMY_OBJECTS
from zora.model.enums import BossSpriteSet, Enemy, EnemySpriteSet
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEED = 1
DODONGO_SEED = 8                          # Shuffle Bosses puts a level 1-8 on block C (level 8; seed 7 until 114f280)
IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
LINK_INVINCIBILITY_TIMER = 0x4F0          # ObjInvincibilityTimer, slot 0 (Link)
INVINCIBLE = 0xFF
HEART_VALUES = 0x66F
MANY_HEARTS = 0xFF
# Items+0, the sword level: the white sword, so a Vire splits. Since 1d260c7 a seed whose level 9 has
# no bomb dropper but Vires caps their hit points at 4 (this one does), and the magical sword then
# kills a Vire outright, leaving its drop.
WHITE_SWORD = 2
MONSTER_SLOTS = range(1, 0x0C)
SPRITES, OAM_RECORDS, HIDDEN_Y = 0x200, 64, 0xEF
TILE_BYTES, SPRITE_TABLE_BIT, PAIR = 16, 1, 0xFE
ROOM_FRAMES = 900
MAGIC_SHOTS = {0x58, 0x59}                # ShootMagicShot's shot types
FULL_COUNT_INDEX = 3                      # count 8
STRIKE_FRAMES, MOST_STRIKES = 14, 400
SWORD_REACH = 14                          # Link stands this far left of his target


@cache
def oops_rom(enemies: OopsAllEnemies = OopsAllEnemies.OFF, bosses: OopsAllBosses = OopsAllBosses.OFF,
             seed: int = SEED) -> tuple[bytes, GameWorld]:
    """A finished ROM with the extras on, and its built world."""
    base = remember_repo_base_rom()
    text = zora_flags.encode(ZoraFlags(oops_all_enemies=enemies, oops_all_bosses=bosses))
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, text), base)
    return finish(built, base), built.world


@dataclass
class Visit:
    """What a room showed: the object types in the monster slots and each sprite tile drawn with
    its 32 bytes of pattern data (an 8x16 sprite's two tiles)."""
    types: Counter[int]
    tiles: dict[int, bytes]
    mode: int


def start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def enter_room(rom: bytes, level: int, room: int) -> Emulator:
    """A new game in `room` of `level`, Link with many hearts."""
    emu = Emulator(rom)
    emu.new_game()
    emu[HEART_VALUES] = MANY_HEARTS
    emu[CUR_LEVEL] = level
    start_mode(emu, Mode.LOAD_LEVEL)
    wait_for_play(emu)
    emu[ROOM_ID] = room
    start_mode(emu, ENTER_ROOM_MODE)
    wait_for_play(emu)
    return emu


def sprite_data(emu: Emulator, tile: int) -> bytes:
    start = (tile & SPRITE_TABLE_BIT) * 0x1000 + (tile & PAIR) * TILE_BYTES
    return emu.pattern_tables()[start:start + 2 * TILE_BYTES]


def visit(rom: bytes, level: int, room: int, frames: int = ROOM_FRAMES) -> Visit:
    emu = enter_room(rom, level, room)
    seen: set[int] = set()
    types: Counter[int] = Counter()
    for _ in range(frames):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1)
        oam = emu.sprites()
        seen |= {oam[record * 4 + 1] for record in range(OAM_RECORDS) if oam[record * 4] < HIDDEN_Y}
        types.update(emu[OBJ_TYPE + slot] for slot in MONSTER_SLOTS)
    return Visit(types, {tile: sprite_data(emu, tile) for tile in seen}, emu.mode)


def family_room_per_bank(world: GameWorld, family: tuple[Enemy, ...]) -> dict[EnemySpriteSet, tuple[int, int]]:
    """A count-8 single-type family room (level, room) in a level of each enemy bank."""
    rooms: dict[EnemySpriteSet, tuple[int, int]] = {}
    for level in world.levels:
        for room in level.rooms:
            if (level.enemy_sprite_set not in rooms and room.enemy in family and not room.has_monster_bit
                    and room.count_index == FULL_COUNT_INDEX):
                rooms[level.enemy_sprite_set] = (level.level_num, room.room_num)
    return rooms


def family_visits(enemies: OopsAllEnemies) -> dict[EnemySpriteSet, Visit]:
    rom, world = oops_rom(enemies)
    rooms = family_room_per_bank(world, FAMILIES[enemies])
    assert set(rooms) == {EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C}
    return {bank: visit(rom, *place) for bank, place in rooms.items()}


def expected_family_data(enemies: OopsAllEnemies) -> dict[int, bytes]:
    """Each family tile pair's base-ROM pattern data, by its first tile."""
    base = parse_rom(remember_repo_base_rom())
    expected = {}
    for enemy, tiles in family_slots(enemies).items():
        sprite_object = ENEMY_OBJECTS[enemy]
        source = base.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
        for index in range(0, len(tiles), 2):
            expected[tiles[index]] = source[index] + source[index + 1]
    return expected


def assert_drawn_alike(visits: dict[EnemySpriteSet, Visit], enemies: OopsAllEnemies) -> None:
    """Every tile drawn shows one pattern in every bank, and the family's own are its base tiles."""
    for visit_ in visits.values():
        assert visit_.mode == Mode.PLAY
    drawn: dict[int, set[bytes]] = {}
    for visit_ in visits.values():
        for tile, data in visit_.tiles.items():
            drawn.setdefault(tile & ~SPRITE_TABLE_BIT, set()).add(data)
    assert all(len(patterns) == 1 for patterns in drawn.values()), \
        {f"${tile:02X}": len(patterns) for tile, patterns in drawn.items() if len(patterns) > 1}
    expected = expected_family_data(enemies)
    for tile, data in expected.items():
        if tile in drawn:
            assert drawn[tile] == {data}, f"${tile:02X}"
    assert expected.keys() & drawn.keys() or not FAMILY_SPRITES[enemies]   # the Keese have no own tiles


def test_wizzrobes_and_their_magic_draw_alike_in_every_enemy_bank() -> None:
    visits = family_visits(OopsAllEnemies.WIZZROBES)
    assert_drawn_alike(visits, OopsAllEnemies.WIZZROBES)
    for visit_ in visits.values():
        assert visit_.types.keys() & MAGIC_SHOTS             # a shot was fired and drawn


def test_bouncers_draw_alike_in_every_enemy_bank() -> None:
    visits = family_visits(OopsAllEnemies.BOUNCERS)
    assert_drawn_alike(visits, OopsAllEnemies.BOUNCERS)


def test_keese_draw_alike_in_every_enemy_bank() -> None:
    visits = family_visits(OopsAllEnemies.KEESE)
    for visit_ in visits.values():
        assert visit_.types.keys() & {enemy.value for enemy in FAMILIES[OopsAllEnemies.KEESE]}
    assert_drawn_alike(visits, OopsAllEnemies.KEESE)


def test_eight_vires_split_without_breaking() -> None:
    rom, world = oops_rom(OopsAllEnemies.BOUNCERS)
    level, room = next((level.level_num, room.room_num) for level in world.levels for room in level.rooms
                       if room.enemy == Enemy.VIRE and not room.has_monster_bit
                       and room.count_index == FULL_COUNT_INDEX)
    emu = enter_room(rom, level, room)
    emu[ITEMS] = WHITE_SWORD
    emu.run(60)

    def monsters() -> list[int]:
        return [emu[OBJ_TYPE + slot] for slot in MONSTER_SLOTS]

    assert Counter(monsters())[Enemy.VIRE] == 8
    vires_died = keese_appeared = most = 0
    previous = monsters()
    for strike in range(MOST_STRIKES):
        targets = [slot for slot, kind in zip(MONSTER_SLOTS, previous, strict=True)
                   if kind in (Enemy.VIRE, Enemy.RED_KEESE)]
        if not targets:
            break
        target = targets[strike % len(targets)]
        emu[OBJ_X] = max(0x10, emu[OBJ_X + target] - SWORD_REACH)
        emu[OBJ_Y] = emu[OBJ_Y + target]
        emu[OBJ_DIR] = Direction.RIGHT
        emu.run(2, Button.A)
        for _ in range(STRIKE_FRAMES):
            emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
            emu.run(1)
            now = monsters()
            vires_died += sum(1 for before, after in zip(previous, now, strict=True)
                              if before == Enemy.VIRE and after != Enemy.VIRE)
            keese_appeared += sum(1 for before, after in zip(previous, now, strict=True)
                                  if after == Enemy.RED_KEESE and before != Enemy.RED_KEESE)
            most = max(most, sum(1 for kind in now if kind in (Enemy.VIRE, Enemy.RED_KEESE)))
            previous = now
    assert emu.mode == Mode.PLAY
    assert not any(monsters())                             # the room emptied
    assert vires_died == 8 and 8 <= keese_appeared <= 16 and most <= len(MONSTER_SLOTS)


def test_dodongos_draw_in_a_level_moved_off_block_c() -> None:
    base = remember_repo_base_rom()
    text = zora_flags.encode(ZoraFlags(oops_all_bosses=OopsAllBosses.DODONGOS))
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, DODONGO_SEED, text), base)
    moved = built.result.groups.staged.boss_sprite_sets if built.result.groups else {}
    assert moved, "the seed no longer puts a level 1-8 on block C"
    level_num = min(moved)
    world = parse_rom(finish(built, base))
    level = world.levels[level_num - 1]
    assert level.boss_sprite_set is BossSpriteSet.A
    room = next(room.room_num for room in level.rooms if room.enemy in (Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO))
    visit_ = visit(finish(built, base), level_num, room)
    assert visit_.mode == Mode.PLAY
    offset, count = DODONGO.frames
    first = min(world.enemies.frame_bytes(offset, count))
    source = parse_rom(base).sprites.read_tiles(*DODONGO.source, DODONGO.tiles)
    dodongo = {first + index: source[index] + source[index + 1] for index in range(0, DODONGO.tiles, 2)}
    drawn = {tile & ~SPRITE_TABLE_BIT: data for tile, data in visit_.tiles.items()
             if first <= tile & ~SPRITE_TABLE_BIT < first + DODONGO.tiles}
    assert drawn and all(dodongo[tile] == data for tile, data in drawn.items())
