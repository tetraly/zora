"""Oops All Enemies and Oops All Bosses (ZORA extras; docs/design/oops-all.md, owner decisions of
2026-10-12 in its section 3).

Oops All Enemies rewrites every regular dungeon room's enemies, in all nine shipped levels, with
draws from one family (2.1): a single-type room keeps its count index and gets one member, drawn
per room; the members of every mixed list a dungeon room names become draws too, so a list room
mixes the family. The family's tiles are copied into all three enemy banks at the same tiles and
its frame bytes renumbered, so it draws in every level; when Shuffle Enemy Groups (B42) put the
family in its overworld group, the overworld screens and lists holding it are redrawn from the
rest of that group (2.2).

Oops All Bosses puts Dodongos in every level 1-8 boss room whose layout allows them; a room whose
layout bars Dodongos keeps its own boss (2.3). Dodongo's tiles go into boss blocks A and B at the
same tiles, and a level 1-8 on block C moves to block A (2.7). A kept boss must still draw: its
tiles stay clear of Dodongo's, copied into its level's block when that block changed; when no
placement of Dodongo leaves every kept boss whole, the attempt restarts.

Both run after every monster pass and the late gate, before the first walk that reads monsters
(Randomize Magical Sword's, then the acceptance check's; 2.6), on their own random stream (2.8).
Room changes go into the staged levels; tiles, frame bytes, lists, overworld monsters and boss
blocks are staged with the group passes' writes (group_banks.Staged), after B42's and B40's,
so they win when the attempt ships.
"""
from collections.abc import Iterable

from ...flags.zora_flags import OopsAllEnemies
from ...model.enums import BossSpriteSet, Enemy
from ...model.game_world import GameWorld
from ...model.levels import Level
from ...model.overworld import Overworld
from ...model.rooms import EnemyInfo, Room
from ...model.sprites import TILE_BYTES
from ..errors import GenerationFailure
from ..rng import IntRng
from .group_banks import OVERWORLD, E, Staged
from .randomize_boss_groups import (
    BOSS_BLOCK_FIRST_TILE,
    BOSS_BLOCKS,
    BOSSES,
    DODONGOS,
    OLD_BOSS_GROUPS,
    BossDeal,
    is_boss_pick_barred,
    packed_slots,
)
from .shuffle_enemy_groups import (
    BRACELET_SCREENS,
    ENEMY_BANK_BLOCKS,
    ENEMY_BANK_FIRST_TILE,
    ENEMY_OBJECTS,
    GORIYA_CANDIDATES,
    GORIYA_FALLBACK_TILE,
    GORIYA_TILE_OFFSET,
    PARTNER_FRAME_COPIES,
    RESERVED_LIST_BYTES,
    SEED_END_TILE,
    WIZZROBE_BARRED_SCREENS,
    WIZZROBES,
    EnemyDeal,
    _is_screen_barred,
    _renumber,
)

# --- the families ----------------------------------------------------------------------------

FAMILIES: dict[OopsAllEnemies, tuple[Enemy, ...]] = {
    OopsAllEnemies.WIZZROBES: (E.RED_WIZZROBE, E.BLUE_WIZZROBE),
    OopsAllEnemies.KEESE: (E.BLUE_KEESE, E.RED_KEESE, E.DARK_KEESE),
    OopsAllEnemies.BOUNCERS: (E.POLS_VOICE, E.VIRE),
}
# The sprite objects whose tiles each family needs, packed in this order so the last ends at
# tile 191 (as B42's seed enemy does). The Keese draw from the common dungeon tiles ($9A-$9C),
# which every level loads (1.3), and red Wizzrobe shares blue Wizzrobe's tiles (PS-EGRP-02).
FAMILY_SPRITES: dict[OopsAllEnemies, tuple[Enemy, ...]] = {
    OopsAllEnemies.WIZZROBES: (E.BLUE_WIZZROBE,),
    OopsAllEnemies.KEESE: (),
    OopsAllEnemies.BOUNCERS: (E.VIRE, E.POLS_VOICE),
}
# The single-type codes a regular room may hold (1.1, 1.6): every enemy the dungeons use or B42
# deals into them. Left alone: the Bubbles (unkillable hazards, reserved in lists too), Moldorm
# (monster bit), bosses, people, traps, the hungry Goriya, the rupee stash, Zelda and Ganon.
REWRITTEN_ENEMIES = frozenset({
    E.BLUE_LYNEL, E.RED_LYNEL, E.BLUE_MOBLIN, E.RED_MOBLIN, E.BLUE_GORIYA, E.RED_GORIYA,
    E.RED_DARKNUT, E.BLUE_DARKNUT, E.BLUE_TEKTITE, E.RED_TEKTITE, E.VIRE, E.ZOL, E.GEL_1, E.GEL_2,
    E.POLS_VOICE, E.LIKE_LIKE, E.BLUE_KEESE, E.RED_KEESE, E.DARK_KEESE, E.RED_WIZZROBE,
    E.BLUE_WIZZROBE, E.WALLMASTER, E.ROPE, E.STALFOS, E.GIBDO, E.RED_LANMOLA, E.BLUE_LANMOLA,
})
FIRST_LIST_CODE = 0x62                   # codes $62-$7F name a mixed list (1.1)
LIST_READ_LENGTH = 8                     # a room reads up to its count's bytes, at most 8


def draw_member(family: tuple[Enemy, ...], rng: IntRng) -> Enemy:
    return family[rng.below(len(family))]


def rewrite_rooms(levels: Iterable[Level], family: tuple[Enemy, ...], rng: IntRng) -> int:
    """2.1: each single-type regular room gets a family member drawn for it, its count index
    kept (the monster bit stays clear). Returns the rooms rewritten."""
    rewritten = 0
    for level in levels:
        for room in level.rooms:
            if not room.has_monster_bit and room.enemy in REWRITTEN_ENEMIES:
                room.enemy_info = EnemyInfo(draw_member(family, rng), room.count_index)
                rewritten += 1
    return rewritten


def list_starts(gw: GameWorld) -> dict[int, int]:
    """Each mixed list's first byte in the list blob, by its code."""
    return dict(gw.enemies.mixed_group_offsets)


def _read_positions(codes: Iterable[int], starts: dict[int, int], blob_length: int) -> set[int]:
    """The blob bytes rooms naming these lists can read: lists overlap, and a room reads its
    count's bytes from the list's start, so a list's bytes run on into the next list's."""
    return {position for code in codes if code in starts
            for position in range(starts[code], min(starts[code] + LIST_READ_LENGTH, blob_length))}


def dungeon_list_codes(levels: Iterable[Level]) -> set[int]:
    return {room.enemy.value for level in levels for room in level.rooms if room.enemy >= FIRST_LIST_CODE}


def overworld_list_codes(overworld: Overworld, staged: Staged) -> dict[int, set[int]]:
    """The lists the overworld screens name as the attempt ships them (a screen B42 staged a
    single monster for names none), with the screens naming each."""
    named: dict[int, set[int]] = {}
    for screen in overworld.screens:
        code = screen.enemy_spec.enemy.value
        if code >= FIRST_LIST_CODE and screen.screen_num not in staged.overworld_monsters:
            named.setdefault(code, set()).add(screen.screen_num)
    return named


def rewrite_lists(gw: GameWorld, levels: list[Level], overworld: Overworld, family: tuple[Enemy, ...],
                  rng: IntRng, staged: Staged) -> int:
    """2.1: every unreserved byte the dungeons' lists read becomes a family member, drawn per
    byte, starting from B42's lists when it ran. No byte an overworld list reads changes (the
    base ROM's dungeon and overworld lists share only reserved bytes; asserted). Returns the
    bytes rewritten."""
    data = bytearray(staged.mixed_lists if staged.mixed_lists is not None else gw.enemies.mixed_enemy_data)
    starts = list_starts(gw)
    dungeon = _read_positions(dungeon_list_codes(levels), starts, len(data))
    overworld_read = _read_positions(overworld_list_codes(overworld, staged), starts, len(data))
    shared = sorted(position for position in dungeon & overworld_read if data[position] not in RESERVED_LIST_BYTES)
    assert not shared, f"dungeon and overworld lists share unreserved bytes {shared}"
    rewritten = 0
    for position in sorted(dungeon):
        if data[position] not in RESERVED_LIST_BYTES:
            data[position] = draw_member(family, rng).value
            rewritten += 1
    staged.mixed_lists = data
    return rewritten


# --- the family's tiles ----------------------------------------------------------------------

def family_slots(choice: OopsAllEnemies) -> dict[Enemy, list[int]]:
    """Each sprite object's tiles in every enemy bank: packed downward so the last ends at 191."""
    slots: dict[Enemy, list[int]] = {}
    end = SEED_END_TILE
    for enemy in reversed(FAMILY_SPRITES[choice]):
        size = ENEMY_OBJECTS[enemy].tiles
        slots[enemy] = list(range(end - size, end))
        end -= size
    return slots


def _enemy_bank_offset(tile: int) -> int:
    return (tile - ENEMY_BANK_FIRST_TILE) * TILE_BYTES


def stage_family_tiles(gw: GameWorld, choice: OopsAllEnemies, staged: Staged) -> dict[Enemy, list[int]]:
    """2.1: the family's tiles copied from the base sprites into all three enemy banks at the same
    tiles, its frame bytes renumbered to them, and each partner's frames copied from its
    primary's (PS-SPR-03's partner runs). Returns the slots."""
    slots = family_slots(choice)
    for enemy, tiles in slots.items():
        sprite_object = ENEMY_OBJECTS[enemy]
        data = gw.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
        for bank in ENEMY_BANK_BLOCKS.values():
            for tile, tile_data in zip(tiles, data, strict=True):
                staged.tiles.append((bank, _enemy_bank_offset(tile), tile_data))
        offset, count = sprite_object.frames
        renumbered = _renumber(gw.enemies.frame_bytes(offset, count), tiles)
        staged.frames.update(zip(range(offset, offset + count), renumbered, strict=True))
        for destination, source, length in PARTNER_FRAME_COPIES:
            if source == offset:
                for step in range(length):
                    staged.frames[destination + step] = staged.frames[source + step]
    return slots


def goriya_tile(slots: dict[Enemy, list[int]]) -> int:
    """1.6: the hungry Goriya draws one tile of its level's bank; the family's first tile when it
    is a PS-EGRP-06 candidate, otherwise PS-EGRP-06's fallback (the Bubble tile)."""
    return next((tiles[0] for enemy, tiles in slots.items() if enemy in GORIYA_CANDIDATES), GORIYA_FALLBACK_TILE)


# --- the overworld (2.2) -----------------------------------------------------------------------

def redraw_overworld(gw: GameWorld, overworld: Overworld, deal: EnemyDeal, family: tuple[Enemy, ...],
                     rng: IntRng, staged: Staged) -> int:
    """2.2: when B42 dealt the family into its overworld group, the family's tiles there are gone
    (one enemy type draws from one set of tiles), so each overworld screen and overworld-list byte
    holding a family member gets another member of that group, with PS-EGRP-05's bars (blue
    Moblins off the bracelet screens, Wizzrobes off theirs). Returns the screens and bytes
    redrawn."""
    remaining = [enemy for enemy in deal.members(OVERWORLD) if enemy not in family]
    redrawn = 0
    for screen_num, monster in sorted(staged.overworld_monsters.items()):
        if monster in family:
            staged.overworld_monsters[screen_num] = _pick_allowed(
                [enemy for enemy in remaining if not _is_screen_barred(screen_num, enemy)], rng)
            redrawn += 1
    assert staged.mixed_lists is not None, "rewrite_lists runs first"
    starts = list_starts(gw)
    values = {enemy.value for enemy in family}
    for code, screens in sorted(overworld_list_codes(overworld, staged).items()):
        for position in sorted(_read_positions([code], starts, len(staged.mixed_lists))):
            if staged.mixed_lists[position] in values:
                allowed = [enemy for enemy in remaining
                           if not (enemy == E.BLUE_MOBLIN and screens & BRACELET_SCREENS)
                           and not (enemy in WIZZROBES and screens & WIZZROBE_BARRED_SCREENS)]
                staged.mixed_lists[position] = _pick_allowed(allowed, rng).value
                redrawn += 1
    staged.red_wizzrobe_overworld = E.RED_WIZZROBE in remaining
    return redrawn


def _pick_allowed(allowed: list[Enemy], rng: IntRng) -> Enemy:
    if not allowed:
        raise GenerationFailure("Oops All Enemies: no other overworld-group enemy fits an overworld screen")
    return allowed[rng.below(len(allowed))]


def oops_all_enemies(gw: GameWorld, levels: list[Level], overworld: Overworld, deal: EnemyDeal | None,
                     choice: OopsAllEnemies, rng: IntRng, staged: Staged) -> int:
    """Oops All Enemies: the rooms and lists, the tiles and the overworld. Returns the single-type
    rooms rewritten."""
    family = FAMILIES[choice]
    rooms = rewrite_rooms(levels, family, rng)
    rewrite_lists(gw, levels, overworld, family, rng, staged)
    if FAMILY_SPRITES[choice]:
        slots = stage_family_tiles(gw, choice, staged)
        staged.frames[GORIYA_TILE_OFFSET] = goriya_tile(slots)
    if deal is not None and set(family) & set(deal.members(OVERWORLD)):
        redraw_overworld(gw, overworld, deal, family, rng, staged)
    return rooms


# --- Oops All Bosses ---------------------------------------------------------------------------

LAST_BOSS_LEVEL = 8                      # level 9's bosses and Ganon stay (2.7)
BLOCK_OF_SET = {BossSpriteSet.A: 0, BossSpriteSet.B: 1, BossSpriteSet.C: 2}
SET_OF_BLOCK = {block: sprite_set for sprite_set, block in BLOCK_OF_SET.items()}
DODONGO_BLOCKS = (0, 1)                  # Dodongo's 36 tiles fit blocks A and B only (1.5)
LEVEL_C_TARGET = 0                       # a level 1-8 on block C moves to block A
DODONGO = BOSSES[E.TRIPLE_DODONGO].body
BOSS_BLOCK_END = 256
# Dodongo's run starts on an even tile (the sprites are 8x16 pairs); its vanilla run, 220-255 in
# block A, first, so with nothing to avoid its frames keep their vanilla values.
DODONGO_RUN_STARTS = tuple(range(BOSS_BLOCK_END - DODONGO.tiles, BOSS_BLOCK_FIRST_TILE - 1, -2))
# Every boss variant's packing key in BOSSES (Gleeok's one-head code draws as the others)
BOSS_KEYS = {variant: key for key, boss in BOSSES.items() for variant in boss.variants} | {E.GLEEOK_1: E.GLEEOK_2}


def boss_homes(deal: BossDeal | None) -> dict[Enemy, tuple[int, list[int]]]:
    """Each boss's block and tiles as the attempt ships them: B40's packing when it ran, else the
    base ROM's (block 3 is the common block, which every level sees)."""
    if deal is not None:
        homes: dict[Enemy, tuple[int, list[int]]] = {}
        for block, boss, _sprite_object, slots in packed_slots(deal):
            homes.setdefault(boss, (block, []))[1].extend(slots)
        return homes
    vanilla_blocks = {pattern_block: block for block, pattern_block in BOSS_BLOCKS.items()}
    homes = {}
    for key, boss_sprites in BOSSES.items():
        for sprite_object in (boss_sprites.body, boss_sprites.companion):
            if sprite_object is not None:
                pattern_block, offset = sprite_object.source
                first = BOSS_BLOCK_FIRST_TILE + offset // TILE_BYTES
                homes.setdefault(key, (vanilla_blocks[pattern_block], []))[1].extend(
                    range(first, first + sprite_object.tiles))
    return homes


def _boss_offset(tile: int) -> int:
    return (tile - BOSS_BLOCK_FIRST_TILE) * TILE_BYTES


def _shipped_boss_tile(gw: GameWorld, staged: Staged, block: int, tile: int) -> bytes:
    """A boss block's tile as the attempt ships it: the last staged write, else the base's."""
    pattern_block, offset = BOSS_BLOCKS[block], _boss_offset(tile)
    written = [data for staged_block, staged_offset, data in staged.tiles
               if staged_block == pattern_block and staged_offset == offset]
    return written[-1] if written else gw.sprites.read_tiles(pattern_block, offset, 1)[0]


def place_dodongos(levels: Iterable[Level], rng: IntRng) -> tuple[int, list[tuple[Level, Room]]]:
    """2.3: each level 1-8 boss room gets a Dodongo, triple or single, drawn per room among the
    variants its layout allows (count index 0: three for the triple); a room whose layout bars
    both keeps its own boss. Returns the rooms given Dodongos and the kept rooms."""
    placed, kept = 0, []
    for level in levels:
        if level.level_num > LAST_BOSS_LEVEL:
            continue
        for room in level.rooms:
            if room.enemy not in OLD_BOSS_GROUPS:
                continue
            allowed = [pick for pick in DODONGOS if not is_boss_pick_barred(pick, room.room_type, room.movable_block)]
            if allowed:
                room.enemy_info = EnemyInfo(allowed[rng.below(len(allowed))])
                placed += 1
            else:
                kept.append((level, room))
    return placed, kept


def dodongo_run(needed: dict[int, dict[int, bytes]]) -> list[int]:
    """The first run of Dodongo's 36 tiles, the same in blocks A and B, that leaves every tile a
    kept boss needs in either block alone; a restart when there is none."""
    taken = {tile for block in DODONGO_BLOCKS for tile in needed[block]}
    for start in DODONGO_RUN_STARTS:
        run = range(start, start + DODONGO.tiles)
        if not taken.intersection(run):
            return list(run)
    raise GenerationFailure("Oops All Bosses: no room in boss blocks A and B for Dodongo beside a kept boss")


def oops_all_bosses(gw: GameWorld, levels: list[Level], boss_sets: dict[int, BossSpriteSet],
                    deal: BossDeal | None, rng: IntRng, staged: Staged) -> int:
    """Oops All Bosses. boss_sets: each level's boss block as the attempt ships it. Returns the
    rooms given Dodongos."""
    placed, kept = place_dodongos(levels, rng)
    for level in levels:
        if level.level_num <= LAST_BOSS_LEVEL and boss_sets[level.level_num] is BossSpriteSet.C:
            staged.boss_sprite_sets[level.level_num] = SET_OF_BLOCK[LEVEL_C_TARGET]
    homes = boss_homes(deal)
    # The tiles each kept boss needs in its level's block after the move, and their data there.
    needed: dict[int, dict[int, bytes]] = {block: {} for block in DODONGO_BLOCKS}
    # Each needed tile's home block. Two kept bosses share a tile only when it is the same tile of
    # the same block, never because two tiles' bytes happen to match, so the player's graphics (a
    # graphics hack, Halloween Mode's art) can never change a seed's game.
    homes_of: dict[int, dict[int, int]] = {block: {} for block in DODONGO_BLOCKS}
    for level, room in kept:
        if room.enemy in DODONGOS:         # a Dodongo kept by a barring layout draws from the run
            continue
        home, tiles = homes[BOSS_KEYS[room.enemy]]
        if home == OVERWORLD:              # the common block: every level sees it
            continue
        target = BLOCK_OF_SET[staged.boss_sprite_sets.get(level.level_num, boss_sets[level.level_num])]
        for tile in tiles:
            if homes_of[target].setdefault(tile, home) != home:
                raise GenerationFailure("Oops All Bosses: two kept bosses need one tile")
            needed[target][tile] = _shipped_boss_tile(gw, staged, home, tile)
    run = dodongo_run(needed)
    dodongo_data = gw.sprites.read_tiles(*DODONGO.source, DODONGO.tiles)
    for block in DODONGO_BLOCKS:
        for tile, data in zip(run, dodongo_data, strict=True):
            staged.tiles.append((BOSS_BLOCKS[block], _boss_offset(tile), data))
        for tile, data in sorted(needed[block].items()):
            staged.tiles.append((BOSS_BLOCKS[block], _boss_offset(tile), data))
    offset, count = DODONGO.frames
    staged.frames.update(zip(range(offset, offset + count),
                             _renumber(gw.enemies.frame_bytes(offset, count), run), strict=True))
    return placed

