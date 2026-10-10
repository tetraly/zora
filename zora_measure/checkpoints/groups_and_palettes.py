"""The enemy and boss groups' and the dungeon palettes' figures
(post-shapes-b4.md, post-shapes-b5.md)."""

import functools
from collections import Counter
from collections.abc import Callable
from typing import Any

from zora.model.enums import BossSpriteSet, Enemy, EnemySpriteSet
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.rooms import Room
from zora_measure.statistics import b1_checkpoint

# --- B4: enemy and boss groups; B5: repack and color sets -----------------------

@functools.cache
def _vanilla() -> GameWorld:
    """The PRG0 base, parsed once: the vanilla tile runs, frame bytes and
    color sets some B4/B5 checkpoints compare against."""
    from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
    from zora.rom.parse.rom_file import load_rom, parse_rom
    verify_base_rom(BASE_ROM_PATH)
    return parse_rom(load_rom(BASE_ROM_PATH))


OVERWORLD_IN_DUNGEON = (Enemy.BLUE_TEKTITE, Enemy.RED_TEKTITE, Enemy.BLUE_MOBLIN,
                        Enemy.RED_LYNEL, Enemy.BLUE_LYNEL, Enemy.RED_MOBLIN)


def _dungeon_monster_rooms(gw: GameWorld) -> list[Room]:
    """PS-EGRP-03's Check base: level rooms of both quest-1 blocks with a
    monster (low six bits non-zero) and the monster bit clear."""
    return [room for level in gw.levels for room in level.rooms
            if room.monster_list and not room.has_monster_bit]


def overworld_enemy_shares(gw: GameWorld) -> dict[str, tuple[int, int]]:
    rooms = _dungeon_monster_rooms(gw)
    return {enemy.name.lower(): (sum(room.monster_list == enemy for room in rooms), len(rooms))
            for enemy in OVERWORLD_IN_DUNGEON}


def any_overworld_enemy_in_dungeon(gw: GameWorld) -> bool:
    return any(room.monster_list in OVERWORLD_IN_DUNGEON for room in _dungeon_monster_rooms(gw))


def _mixed_lists(gw: GameWorld) -> list[bytes]:
    offsets = [gw.enemies.mixed_group_offsets[code] for code in sorted(gw.enemies.mixed_group_offsets)]
    ends = [*offsets[1:], len(gw.enemies.mixed_enemy_data)]
    return [bytes(gw.enemies.mixed_enemy_data[a:b]) for a, b in zip(offsets, ends, strict=True)]


MAX_MIXED_LIST_ZOLS = 4


def mixed_list_checks(gw: GameWorld) -> dict[str, tuple[int, int]]:
    lists = _mixed_lists(gw)
    lanmolas = {Enemy.RED_LANMOLA.value, Enemy.BLUE_LANMOLA.value}
    return {"lanmola": (sum(bool(lanmolas & set(members)) for members in lists), len(lists)),
            "zols > 4": (sum(members.count(Enemy.ZOL.value) > MAX_MIXED_LIST_ZOLS
                             for members in lists), len(lists))}


BOSS_IDENTITIES = (Enemy.AQUAMENTUS, Enemy.MANHANDLA, Enemy.SINGLE_DIGDOGGER,
                   Enemy.TRIPLE_DIGDOGGER, Enemy.BLUE_GOHMA, Enemy.RED_GOHMA, Enemy.PATRA_1,
                   Enemy.PATRA_2, Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO, Enemy.GLEEOK_2,
                   Enemy.GLEEOK_3, Enemy.GLEEOK_4)
BOSS_CODES = frozenset(BOSS_IDENTITIES) | {Enemy.GLEEOK_1}


def _combined(room: Room) -> int:
    return room.monster_list | (0x40 if room.has_monster_bit else 0)


def _boss_rooms(gw: GameWorld) -> list[tuple[Level, Room]]:
    return [(level, room) for level in gw.levels for room in level.rooms
            if _combined(room) in BOSS_CODES]


def boss_identities(gw: GameWorld) -> Counter[int]:
    return Counter(_combined(room) for _, room in _boss_rooms(gw))


def one_headed_gleeoks(gw: GameWorld) -> tuple[int, int]:
    rooms = _boss_rooms(gw)
    return sum(_combined(room) == Enemy.GLEEOK_1 for _, room in rooms), len(rooms)


ZOL_COUNT_BIT_7 = 0b10


def zol_rooms_with_bit_7(gw: GameWorld) -> tuple[int, int]:
    """PS-EGRP-03: Zol rooms (monster bit clear, low six 19) of all four
    room blocks whose monster byte keeps bit 7."""
    rooms = [room for block in (*gw.blocks, *gw.blocks_2q) for room in block.rooms
             if not room.has_monster_bit and room.monster_list == Enemy.ZOL]
    return sum(bool(room.count_index & ZOL_COUNT_BIT_7) for room in rooms), len(rooms)


GORIYA_TILE_OFFSET = 171
GORIYA_TILES = (0x9E, 0xA2, 0xA0, 0xAC, 0x8E)
SEED_SLOT_TILE = 0xBC
TIER_0_BANK = EnemySpriteSet.A


def goriya_tile(gw: GameWorld) -> Counter[int]:
    return Counter([gw.enemies.frame_bytes(GORIYA_TILE_OFFSET, 1)[0]])


def _goriya_level(gw: GameWorld) -> Level | None:
    return next((level for level in gw.levels for room in level.rooms
                 if not room.has_monster_bit and room.monster_list == Enemy.HUNGRY_GORIYA), None)


def goriya_seed_slot(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """$BC ($188, a seed-enemy slot in banks 1 and 2) by the goriya level's
    enemy bank: tier 0 or another."""
    level = _goriya_level(gw)
    hit = gw.enemies.frame_bytes(GORIYA_TILE_OFFSET, 1)[0] == SEED_SLOT_TILE
    tier_0 = level is not None and level.enemy_sprite_set == TIER_0_BANK
    return {"tier 0": (int(hit and tier_0), int(tier_0)),
            "other": (int(hit and not tier_0), int(not tier_0))}


WALLMASTER_FRAMES = (146, [0xAC, 0x9C])
PARTNER_RUNS = ((92, 96, 4), (106, 100, 6), (140, 136, 4), (15, 11, 4), (23, 19, 4), (41, 39, 2))
PARTNER_NAMES = ("goriya", "darknut", "wizzrobe", "lynel", "moblin", "tektite")


def fixed_frame_bytes(gw: GameWorld) -> dict[str, bool]:
    """PS-SPR-02/-03: Wallmaster's + 146/147, Gleeok's neck / head / + 199
    bytes $DA/$DC/$DE, and the open-mouth operand = Aquamentus's fourth
    frame byte minus 2."""
    enemies = gw.enemies
    fourth = (enemies.aquamentus_tile_layout_table or [0] * 4)[3]
    return {"wallmaster": enemies.frame_bytes(*WALLMASTER_FRAMES[:1], 2) == WALLMASTER_FRAMES[1],
            "gleeok": (enemies.gleeok_head_sprite_ptr_a, enemies.gleeok_head_sprite_ptr_b,
                       enemies.frame_bytes(199, 1)[0]) == (0xDA, 0xDC, 0xDE),
            "open mouth": enemies.aquamentus_sprite_ptr == fourth - 2}


def partner_runs(gw: GameWorld) -> dict[str, bool]:
    """Each partner's frame run equals its primary's (PS-SPR-03)."""
    enemies = gw.enemies
    return {name: enemies.frame_bytes(dest, n) == enemies.frame_bytes(src, n)
            for name, (dest, src, n) in zip(PARTNER_NAMES, PARTNER_RUNS, strict=True)}


def partner_runs_changed(gw: GameWorld) -> dict[str, bool]:
    vanilla = _vanilla().enemies
    return {name: gw.enemies.frame_bytes(dest, n) != vanilla.frame_bytes(dest, n)
            for name, (dest, _src, n) in zip(PARTNER_NAMES, PARTNER_RUNS, strict=True)}


OPEN_MOUTH_VALUES = (0x31, 0xE4, 0xE2)


def open_mouth(gw: GameWorld) -> Counter[int]:
    return Counter([gw.enemies.aquamentus_sprite_ptr or 0])


CARRIER_OFF = 0xFF


def item_carriers_off(gw: GameWorld) -> dict[str, bool]:
    names = ("like like $17", "stalfos $2A", "gibdo $30")
    return {name: value == CARRIER_OFF for name, value in zip(names, gw.item_carrier_operands, strict=True)}


# B5: where each boss's tiles sit, read back from its frame bytes: the slot
# of its first tile (odd = the common block, 8x16 bit 0), and for a bank
# slot, which boss bank holds its vanilla first tiles there.
BOSS_BANKS = {BossSpriteSet.A: 0, BossSpriteSet.B: 1, BossSpriteSet.C: 2}
COMMON = "common"
BOSS_FIRST_TILE = 192
TILES_COMPARED = 4


def _boss_kind(code: int) -> Enemy:
    from zora.generate.steps.randomize_boss_groups import BOSSES
    for kind, boss in BOSSES.items():
        if code in boss.variants or (kind == Enemy.GLEEOK_2 and code == Enemy.GLEEOK_1):
            return kind
    raise KeyError(code)


def _first_slot(gw: GameWorld, kind: Enemy) -> int:
    from zora.generate.steps.randomize_boss_groups import (
        AQUAMENTUS_FRAMES,
        BOSSES,
        GLEEOK_FRAMES,
        GLEEOK_NECK_LIFT,
    )
    enemies = gw.enemies
    frames = BOSSES[kind].body.frames
    if frames == AQUAMENTUS_FRAMES:
        return enemies.aquamentus_sprite_ptr or 0
    if frames == GLEEOK_FRAMES:
        return (enemies.gleeok_head_sprite_ptr_a or 0) - GLEEOK_NECK_LIFT
    return min(enemies.frame_bytes(*frames))


def boss_locations(gw: GameWorld) -> dict[Enemy, str | int | None]:
    """Each boss kind's block: 0-2, "common", or None when no bank holds its
    vanilla first tiles at the slot its frames name."""
    from zora.generate.steps.randomize_boss_groups import BOSSES
    from zora.model.sprites import TILE_BYTES, PatternBlock
    banks = (PatternBlock.BOSS1257, PatternBlock.BOSS3468, PatternBlock.BOSS9)
    where: dict[Enemy, str | int | None] = {}
    for kind, boss in BOSSES.items():
        slot = _first_slot(gw, kind)
        if slot & 1:
            where[kind] = COMMON
            continue
        count = min(TILES_COMPARED, boss.body.tiles)
        vanilla = _vanilla().sprites.read_tiles(*boss.body.source, count)
        offset = (slot - BOSS_FIRST_TILE) * TILE_BYTES
        where[kind] = next((b for b, bank in enumerate(banks)
                            if 0 <= offset <= 1024 - count * TILE_BYTES
                            and gw.sprites.read_tiles(bank, offset, count) == vanilla), None)
    return where


def boss_placement(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """Boss rooms whose boss sits in its level's boss block, in the common
    block, or elsewhere; level 9's common share."""
    where = boss_locations(gw)
    rooms = _boss_rooms(gw)
    located = [(level, where[_boss_kind(_combined(room))]) for level, room in rooms]
    own = sum(block == BOSS_BANKS[level.boss_sprite_set] for level, block in located)
    common = sum(block == COMMON for _, block in located)
    level9 = [block for level, block in located if level.level_num == 9]
    return {"own block": (own, len(located)), "common": (common, len(located)),
            "elsewhere": (len(located) - own - common, len(located)),
            "L9 common": (sum(block == COMMON for block in level9), len(level9))}


def boss_blocks(gw: GameWorld) -> dict[str, bool]:
    where = boss_locations(gw)
    shared = where[Enemy.TRIPLE_DODONGO] == where[Enemy.GLEEOK_2]
    return {"dodongo+gleeok": shared,
            "block 2 digdogger": where[Enemy.SINGLE_DIGDOGGER] == 2,
            "block 2 patra": where[Enemy.PATRA_1] == 2}


def _color_pairs(gw: GameWorld) -> list[tuple[bytes, bytes]]:
    return [level.color_sets for level in gw.levels]


def color_sets_check(gw: GameWorld) -> dict[str, bool]:
    from zora.generate.steps.shuffle_dungeon_palettes import color_candidates
    pairs = _color_pairs(gw)
    candidates = set(color_candidates(_vanilla()))
    return {"distinct": len(set(pairs)) == len(pairs),
            "all candidates": all(pair in candidates for pair in pairs)}


INNER_SELECTORS = (2, 3, 0)


def inner_selector_shares(gw: GameWorld) -> dict[str, tuple[int, int]]:
    rooms = [room for level in gw.levels for room in level.rooms]
    return {f"inner {n}": (sum(room.palette_1 == n for room in rooms), len(rooms))
            for n in INNER_SELECTORS}


def _b1(field: str) -> Callable[[GameWorld], Any]:
    return lambda gw: getattr(b1_checkpoint(gw), field)


def hearts_total(gw: GameWorld) -> int:
    cp = b1_checkpoint(gw)
    return cp.hearts_dungeon + cp.hearts_caves
