"""Shuffle Enemy Groups (B42; PS-EGRP-01 to -06, PS-SPR-03)."""

from dataclasses import dataclass

from zora.generate.rng import IntRng, discard
from zora.generate.shapes.tables import LANMOLA_BAD_LAYOUTS
from zora.generate.steps.group_banks import DISCARDED_DRAWS, GROUPS, OVERWORLD, E, SpriteObject, Staged
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.levels import LevelBlock
from zora.model.overworld import Overworld
from zora.model.rooms import EnemyInfo, Room
from zora.model.sprites import TILE_BYTES, PatternBlock

ENEMY_OBJECTS: dict[Enemy, SpriteObject] = {
    E.ZOL: SpriteObject(4, (PatternBlock.UWSP358, 160), (116, 2)),
    E.RED_GORIYA: SpriteObject(16, (PatternBlock.UWSP127, 288), (96, 4)),
    E.RED_DARKNUT: SpriteObject(20, (PatternBlock.UWSP358, 224), (100, 6)),
    E.VIRE: SpriteObject(8, (PatternBlock.UWSP469, 224), (112, 4)),
    E.POLS_VOICE: SpriteObject(4, (PatternBlock.UWSP358, 32), (120, 2)),
    E.LIKE_LIKE: SpriteObject(6, (PatternBlock.UWSP469, 64), (122, 4)),
    E.BLUE_WIZZROBE: SpriteObject(12, (PatternBlock.UWSP469, 352), (136, 4)),
    E.WALLMASTER: SpriteObject(4, (PatternBlock.UWSP127, 224), (146, 0)),
    E.ROPE: SpriteObject(8, (PatternBlock.UWSP127, 32), (148, 2)),
    E.STALFOS: SpriteObject(4, (PatternBlock.UWSP127, 160), (152, 1)),
    E.GIBDO: SpriteObject(4, (PatternBlock.UWSP358, 96), (154, 1)),
    E.RED_LANMOLA: SpriteObject(4, (PatternBlock.UWSP469, 0), (0, 0)),
    E.BLUE_TEKTITE: SpriteObject(4, (PatternBlock.OWSP, 960), (39, 2)),
    E.BLUE_LYNEL: SpriteObject(16, (PatternBlock.OWSP, 1024), (11, 4)),
    E.BLUE_MOBLIN: SpriteObject(16, (PatternBlock.OWSP, 1568), (19, 4)),
}
ROSTER = tuple(ENEMY_OBJECTS)                    # the spec's listing order
WALLMASTER_COUNTED_COST = 6                      # its 4 tiles count as 6


def counted_cost(enemy: Enemy) -> int:
    return WALLMASTER_COUNTED_COST if enemy == E.WALLMASTER else ENEMY_OBJECTS[enemy].tiles


SEED_CANDIDATES = (E.ZOL, E.POLS_VOICE, E.STALFOS, E.GIBDO, E.BLUE_TEKTITE)
SEED_GROUPS = (1, 2)
GROUP_TILE_LIMIT = 34
# The overworld group's total starts at -2 (34 minus the 36 tiles of blue
# Tektite, Lynel and Moblin), so it can take 36 tiles.
GROUP_START_TOTALS = (0, 0, 0, -2)
OVERWORLD_BARRED = frozenset({E.RED_LANMOLA, E.WALLMASTER, E.VIRE, E.ZOL, E.LIKE_LIKE})
DEAL_ATTEMPTS = 1_000
COVERAGE = frozenset({E.RED_GORIYA, E.RED_DARKNUT, E.GIBDO, E.BLUE_WIZZROBE,
                      E.BLUE_LYNEL, E.BLUE_MOBLIN})
VIRE_COVERS_AT_ZOL_HP = 4                        # Vire covers when Zol's HP nibble <= 4

# PS-EGRP-02: partners join their primary's group (no tile cost)
PARTNERS = {E.RED_GORIYA: E.BLUE_GORIYA, E.RED_DARKNUT: E.BLUE_DARKNUT,
            E.BLUE_WIZZROBE: E.RED_WIZZROBE, E.RED_LANMOLA: E.BLUE_LANMOLA,
            E.BLUE_LYNEL: E.RED_LYNEL, E.BLUE_MOBLIN: E.RED_MOBLIN,
            E.BLUE_TEKTITE: E.RED_TEKTITE}


@dataclass
class EnemyDeal:
    order: list[Enemy]                           # the sorted order (join order)
    seed: Enemy
    groups: dict[int, list[Enemy]]               # group -> dealt enemies, join order
    restarts: int = 0

    def members(self, group: int) -> list[Enemy]:
        """The group's pickable members: dealt enemies (the seed in groups 1
        and 2), then their partners."""
        dealt = self.groups[group]
        return dealt + [PARTNERS[enemy] for enemy in dealt if enemy in PARTNERS]

    def group_of(self, enemy: Enemy) -> int | None:
        return next((group for group in (0, 1, 2, OVERWORLD) if enemy in self.members(group)), None)


def _sort_by_cost(rng: IntRng) -> list[Enemy]:
    """PS-EGRP-01: a descending bubble sort by counted cost; each tied pair
    is decided by a coin flip."""
    order = list(ROSTER)
    for done in range(len(order) - 1):
        for position in range(len(order) - 1 - done):
            cost, next_cost = counted_cost(order[position]), counted_cost(order[position + 1])
            if cost < next_cost or (cost == next_cost and rng.below(2)):
                order[position], order[position + 1] = order[position + 1], order[position]
    return order


def _group_allows(members: list[Enemy], total: int, group: int, enemy: Enemy) -> bool:
    if {enemy, *members} >= {E.WALLMASTER, E.RED_LANMOLA}:
        return False
    if group == OVERWORLD and enemy in OVERWORLD_BARRED:
        return False
    return total + counted_cost(enemy) <= GROUP_TILE_LIMIT


def _is_covered(groups: dict[int, list[Enemy]], zol_hp: int) -> bool:
    cover = COVERAGE | ({E.VIRE} if zol_hp <= VIRE_COVERS_AT_ZOL_HP else set())
    return all(cover & set(groups[group]) for group in GROUPS)


def deal_enemies(rng: IntRng, zol_hp: int) -> EnemyDeal:
    """PS-EGRP-01: sort, seed enemy into groups 1 and 2, then one uniform
    group per enemy, redrawn while barred; 1,000 failures or a group
    without a coverage enemy redo the group draws (order and seed kept)."""
    discard(rng, DISCARDED_DRAWS)
    order = _sort_by_cost(rng)
    seed = SEED_CANDIDATES[rng.below(len(SEED_CANDIDATES))]
    restarts = 0
    while True:
        groups: dict[int, list[Enemy]] = {group: [] for group in GROUPS}
        totals = dict(zip(GROUPS, GROUP_START_TOTALS, strict=True))
        for group in SEED_GROUPS:
            groups[group].append(seed)
            totals[group] += counted_cost(seed)
        is_dealt = True
        for enemy in order:
            if enemy == seed:
                continue
            for _ in range(DEAL_ATTEMPTS):
                group = GROUPS[rng.below(len(GROUPS))]
                if _group_allows(groups[group], totals[group], group, enemy):
                    groups[group].append(enemy)
                    totals[group] += counted_cost(enemy)
                    break
            else:
                is_dealt = False
                break
        if is_dealt and _is_covered(groups, zol_hp):
            return EnemyDeal(order, seed, groups, restarts)
        restarts += 1


# --- PS-SPR: tile packing ------------------------------------------------------

ENEMY_BANK_TILES = range(158, 192)
OVERWORLD_BANK_TILES = (*range(202, 222), *range(240, 256))
ENEMY_BANK_FIRST_TILE = 158
WALLMASTER_SLOTS = (172, 173, 174, 175)
WALLMASTER_BORROWED = (158, 159)                 # get the tier-0 bank's first two tiles
LANMOLA_SLOTS = (158, 159, 160, 161)
SEED_END_TILE = 192                              # the seed ends at tile 191
ENEMY_BANK_BLOCKS = {0: PatternBlock.UWSP127, 1: PatternBlock.UWSP358, 2: PatternBlock.UWSP469}
OVERWORLD_BANK_OFFSET = 256                      # PatternBlockOWSP + 256 = tile 158


def _renumber(frames: list[int], slots: list[int], shift: int = 0) -> list[int]:
    """PS-SPR-02 renumbering: a frame value names tile value - min(frames),
    which becomes the slot it landed in (plus `shift`)."""
    lowest = min(frames)
    return [slots[frame - lowest] + shift for frame in frames]


def _tile_destination(group: int, tile: int) -> tuple[PatternBlock, int]:
    if group == OVERWORLD:
        return PatternBlock.OWSP, OVERWORLD_BANK_OFFSET + (tile - ENEMY_BANK_FIRST_TILE) * TILE_BYTES
    return ENEMY_BANK_BLOCKS[group], (tile - ENEMY_BANK_FIRST_TILE) * TILE_BYTES


def pack_enemies(gw: GameWorld, deal: EnemyDeal, staged: Staged) -> dict[int, dict[Enemy, list[int]]]:
    """PS-SPR-03: Wallmaster and red Lanmola at fixed tiles, the seed enemy
    ending at tile 191 (groups 1 and 2), everyone else first-fit in join
    order; frame bytes renumbered, then the partners' frames copied from
    their primaries. Returns each group's slots per enemy."""
    sources = {enemy: gw.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
               for enemy, sprite_object in ENEMY_OBJECTS.items()}
    tier0_first = gw.sprites.read_tiles(PatternBlock.UWSP127, 0, len(WALLMASTER_BORROWED))
    placed: dict[int, dict[Enemy, list[int]]] = {}
    for group in GROUPS:
        free = list(OVERWORLD_BANK_TILES if group == OVERWORLD else ENEMY_BANK_TILES)
        slots: dict[Enemy, list[int]] = {}
        members = deal.groups[group]
        if E.WALLMASTER in members:
            slots[E.WALLMASTER] = list(WALLMASTER_SLOTS)
            for tile, data in zip(WALLMASTER_BORROWED, tier0_first, strict=True):
                staged.tiles.append((*_tile_destination(group, tile), data))
            free = [tile for tile in free if tile not in (*WALLMASTER_SLOTS, *WALLMASTER_BORROWED)]
        if E.RED_LANMOLA in members:
            slots[E.RED_LANMOLA] = list(LANMOLA_SLOTS)
            free = [tile for tile in free if tile not in LANMOLA_SLOTS]
        if group in SEED_GROUPS:
            size = ENEMY_OBJECTS[deal.seed].tiles
            slots[deal.seed] = list(range(SEED_END_TILE - size, SEED_END_TILE))
            free = [tile for tile in free if tile not in slots[deal.seed]]
        for enemy in members:
            if enemy not in slots:
                count = ENEMY_OBJECTS[enemy].tiles
                slots[enemy], free = free[:count], free[count:]
        for enemy, tiles in slots.items():
            for tile, data in zip(tiles, sources[enemy], strict=True):
                staged.tiles.append((*_tile_destination(group, tile), data))
        placed[group] = slots
    for enemy, sprite_object in ENEMY_OBJECTS.items():
        offset, count = sprite_object.frames
        home = deal.group_of(enemy)
        if count and home is not None:
            frames = gw.enemies.frame_bytes(offset, count)
            staged.frames.update(zip(range(offset, offset + count),
                                     _renumber(frames, placed[home][enemy]), strict=True))
    _copy_partner_frames(gw, staged)
    return placed


# PS-SPR-03: partner frame runs (destination offset, source offset, length)
PARTNER_FRAME_COPIES = ((92, 96, 4), (106, 100, 6), (140, 136, 4),
                        (15, 11, 4), (23, 19, 4), (41, 39, 2))


def _copy_partner_frames(gw: GameWorld, staged: Staged) -> None:
    for destination, source, length in PARTNER_FRAME_COPIES:
        for offset in range(length):
            value = staged.frames.get(source + offset, gw.enemies.frame_bytes(source + offset, 1)[0])
            staged.frames[destination + offset] = value


# --- PS-EGRP-03: dungeon rooms -----------------------------------------------------

OLD_ENEMY_GROUPS: dict[Enemy, int] = {
    **dict.fromkeys((E.BLUE_GORIYA, E.RED_GORIYA, E.WALLMASTER, E.ROPE, E.STALFOS), 0),
    **dict.fromkeys((E.RED_DARKNUT, E.BLUE_DARKNUT, E.POLS_VOICE, E.GIBDO), 1),
    **dict.fromkeys((E.VIRE, E.LIKE_LIKE, E.RED_WIZZROBE, E.BLUE_WIZZROBE,
                     E.RED_LANMOLA, E.BLUE_LANMOLA), 2),
    **dict.fromkeys((E.BLUE_LYNEL, E.RED_LYNEL, E.BLUE_MOBLIN, E.RED_MOBLIN,
                     E.BLUE_TEKTITE, E.RED_TEKTITE), OVERWORLD),
}
GROUPED_VALUES = frozenset(e.value for e in OLD_ENEMY_GROUPS)
LANMOLAS = (E.RED_LANMOLA, E.BLUE_LANMOLA)
STAIRCASE_LAYOUTS = (0x3E, 0x3F)
COUNT_BIT_7 = 0b10                               # the monster byte's bit 7 in the count index


def _block_rooms(block: LevelBlock) -> list[Room]:
    """Rooms 0-127 of the block, staircases skipped. (The cells no level
    owns are blank rooms: monster list $00, which no rule here matches.)"""
    return [room for room in block.rooms if room.room_type not in STAIRCASE_LAYOUTS]


def redraw_rooms(blocks: list[LevelBlock], deal: EnemyDeal, rng: IntRng) -> int:
    """PS-EGRP-03: a room without the monster bit holding an old-group
    enemy gets a uniform pick from that group's new members (a Lanmola
    re-drawn while the layout bars it); a Zol room takes the seed enemy.
    The monster byte keeps its count bits, except that writing Zol clears
    bit 7 (quirk). Returns the rooms rewritten."""
    rewritten = 0
    for block in blocks:
        for room in _block_rooms(block):
            if room.has_monster_bit:
                continue
            current = room.enemy
            if current == E.ZOL:
                pick = deal.seed
            elif current in OLD_ENEMY_GROUPS:
                members = deal.members(OLD_ENEMY_GROUPS[current])
                pick = members[rng.below(len(members))]
                while pick in LANMOLAS and room.room_type in LANMOLA_BAD_LAYOUTS:
                    pick = members[rng.below(len(members))]
            else:
                continue
            # Quirk (PS-EGRP-03): the count bits stay, but writing Zol
            # clears the monster byte's bit 7.
            count_index = room.count_index & ~COUNT_BIT_7 if pick == E.ZOL else room.count_index
            room.enemy_info = EnemyInfo(pick, count_index)
            rewritten += 1
    return rewritten


# --- PS-EGRP-04: mixed monster lists ---------------------------------------------

RESERVED_LIST_BYTES = frozenset({0x00, 0x0F, 0x10, 0x2B, 0x2C, 0x2D, 0x4A})
CORNER_TRAPS = E.CORNER_TRAPS.value
ZOL_LIMIT = 10          # replaced bytes count 1 toward it, a Zol one more


def _list_bounds(gw: GameWorld) -> list[tuple[int, int]]:
    """Each mixed list's (start, end) in the blob: a list ends where the
    next entry's begins; the last ends at ObjListAddrs itself."""
    starts = [gw.enemies.mixed_group_offsets[code] for code in sorted(gw.enemies.mixed_group_offsets)]
    ends = [*starts[1:], len(gw.enemies.mixed_enemy_data)]
    return list(zip(starts, ends, strict=True))


def _list_group(members: bytearray) -> int | None:
    """The old group of the list's last grouped member; none when a Zol
    follows it or no member has one."""
    group, last = None, -1
    for position, value in enumerate(members):
        if value in GROUPED_VALUES:
            group, last = OLD_ENEMY_GROUPS[Enemy(value)], position
    if any(value == E.ZOL.value for value in members[last + 1:]):
        return None
    return group


def redraw_excess_zols(members: bytearray, replaced: int, non_zol: list[Enemy],
                       rng: IntRng) -> None:
    """PS-EGRP-04's Zol count (quirk, S6): every replaced byte counts 1 and
    a replaced Zol one more; while the count exceeds 10 every Zol is
    redrawn, never to a Zol. Five Zols alone (count 10) stand. The loop
    ends after one redraw: no Zol is left, and no list has more than 8
    bytes."""
    while replaced + members.count(E.ZOL.value) > ZOL_LIMIT and non_zol:
        for position, value in enumerate(members):
            if value == E.ZOL.value:
                members[position] = non_zol[rng.below(len(non_zol))].value


def redraw_mixed_lists(gw: GameWorld, deal: EnemyDeal, rng: IntRng, staged: Staged) -> None:
    """PS-EGRP-04: Zol bytes become the seed enemy; a grouped list's
    unreserved bytes are redrawn from its group (never a Lanmola; never
    Wallmaster beside corner traps); too many Zols are redrawn again.

    The Zol count is a quirk: see redraw_excess_zols."""
    data = bytearray(gw.enemies.mixed_enemy_data)
    for start, end in _list_bounds(gw):
        members = data[start:end]
        group = _list_group(members)
        for position, value in enumerate(members):
            if value == E.ZOL.value:
                members[position] = deal.seed.value
        if group is not None:
            allowed = [enemy for enemy in deal.members(group) if enemy not in LANMOLAS
                       and not (enemy == E.WALLMASTER and CORNER_TRAPS in members)]
            replaced = 0
            for position, value in enumerate(members):
                if value not in RESERVED_LIST_BYTES and allowed:
                    members[position] = allowed[rng.below(len(allowed))].value
                    replaced += 1
            redraw_excess_zols(members, replaced, [enemy for enemy in allowed if enemy != E.ZOL], rng)
        data[start:end] = members
    staged.mixed_lists = data


# --- PS-EGRP-05: overworld screens (overview) -----------------------------------

BRACELET_SCREENS = frozenset({9, 17, 27, 29, 35, 73, 121})
WIZZROBE_BARRED_SCREENS = frozenset({2, 5, 6, 7, 8, 23, 26, 29, 30, 56, 63, 68, 85, 114})
OVERWORLD_MONSTERS = frozenset({E.BLUE_LYNEL, E.RED_LYNEL, E.BLUE_MOBLIN, E.RED_MOBLIN,
                                E.BLUE_TEKTITE, E.RED_TEKTITE})
WIZZROBES = (E.RED_WIZZROBE, E.BLUE_WIZZROBE)
# MoveAndDrawRoomItem's three object-type operands, in order; disabled ($FF)
# when their type joins the overworld group
ITEM_CARRIERS = (E.LIKE_LIKE, E.STALFOS, E.GIBDO)
CARRIER_OFF = 0xFF
MIXED_SCREEN_CODE = 0x40                                 # table-D flag, in the enemy code
MOBLIN_MEMBER = 3                                        # a mixed list's blue-Moblin value
WIZZROBE_MEMBERS = (35, 36)                              # a mixed list's Wizzrobe values


def _is_screen_barred(screen: int, pick: Enemy) -> bool:
    return ((pick == E.BLUE_MOBLIN and screen in BRACELET_SCREENS)
            or (pick in WIZZROBES and screen in WIZZROBE_BARRED_SCREENS))


def _is_flagged_screen_unsafe(screen: int, code: int, lists: dict[int, bytes]) -> bool:
    """PS-EGRP-05 (B4.1): a flagged screen's code (low six bits + $40) names
    one of PS-EGRP-04's lists as that step left them; it is unsafe when the
    list holds a Moblin member on a bracelet screen, or a Wizzrobe member on
    a Wizzrobe-barred screen. Codes below $62 name no list."""
    members = lists.get(code)
    if members is None:
        return False
    return ((MOBLIN_MEMBER in members and screen in BRACELET_SCREENS)
            or (any(member in members for member in WIZZROBE_MEMBERS) and screen in WIZZROBE_BARRED_SCREENS))


def redraw_overworld(gw: GameWorld, overworld: Overworld, deal: EnemyDeal, rng: IntRng,
                     staged: Staged) -> None:
    """PS-EGRP-05: an unsafe flagged screen loses its flag and becomes a
    blue Moblin (quantity kept); then every unflagged Lynel/Moblin/Tektite
    screen gets a pick from the overworld group, redrawn while barred."""
    members = deal.members(OVERWORLD)
    assert staged.mixed_lists is not None, "PS-EGRP-04 runs first"
    lists = {code: bytes(staged.mixed_lists[start:end])
             for code, (start, end) in zip(sorted(gw.enemies.mixed_group_offsets), _list_bounds(gw), strict=True)}
    for screen in overworld.screens:
        code = screen.enemy_spec.enemy.value
        if code >= MIXED_SCREEN_CODE:
            if not _is_flagged_screen_unsafe(screen.screen_num, code, lists):
                continue
            code = E.BLUE_MOBLIN.value
        if Enemy(code) not in OVERWORLD_MONSTERS:
            continue
        pick = members[rng.below(len(members))]
        while _is_screen_barred(screen.screen_num, pick):
            pick = members[rng.below(len(members))]
        staged.overworld_monsters[screen.screen_num] = pick
    operands = gw.item_carrier_operands
    staged.item_carrier_operands = (
        CARRIER_OFF if ITEM_CARRIERS[0] in members else operands[0],
        CARRIER_OFF if ITEM_CARRIERS[1] in members else operands[1],
        CARRIER_OFF if ITEM_CARRIERS[2] in members else operands[2]
    )
    staged.red_wizzrobe_overworld = E.RED_WIZZROBE in members


# --- PS-EGRP-06: the hungry goriya's tile ---------------------------------------

GORIYA_CANDIDATES = (E.RED_GORIYA, E.ROPE, E.STALFOS, E.RED_DARKNUT, E.GIBDO,
                     E.BLUE_WIZZROBE, E.BLUE_LYNEL, E.BLUE_MOBLIN)
WALLMASTER_GORIYA_TILE = 0xAC
GORIYA_FALLBACK_TILE = 0x8E
GORIYA_TILE_OFFSET = 171                         # ObjAnimFrameHeap + 171
FIXED_FRAME_91 = (91, 0xB0)                      # ObjAnimFrameHeap + 91 = $B0
OBJECT_TYPE_OPERAND = 0x7E                       # 0x0474D, purpose unknown


def pick_goriya_tile(deal: EnemyDeal, placed: dict[int, dict[Enemy, list[int]]],
                     group: int, rng: IntRng) -> int:
    """PS-EGRP-06: uniform over the first slots of the candidate enemies
    packed into the goriya level's group (never the seed enemy), plus $AC
    with Wallmaster; $8E when there are none."""
    slots = placed[group]
    candidates = [slots[enemy][0] for enemy in GORIYA_CANDIDATES
                  if enemy in slots and enemy != deal.seed]
    if E.WALLMASTER in slots:
        candidates.append(WALLMASTER_GORIYA_TILE)
    if not candidates:
        return GORIYA_FALLBACK_TILE
    return candidates[rng.below(len(candidates))]


def shuffle_enemy_groups(blocks: list[LevelBlock], gw: GameWorld, goriya_tier: int, rng: IntRng,
                         overworld: Overworld, zol_hp: int, staged: Staged) -> tuple[EnemyDeal, int, int]:
    """PS-EGRP-01..06: deal the enemies into groups, pack their tiles, and
    redraw the rooms, the mixed lists and the overworld from them; then the
    goriya's tile from its level's group. Returns the deal, the goriya tile
    and the number of rooms redrawn."""
    enemy_deal = deal_enemies(rng, zol_hp)
    placed = pack_enemies(gw, enemy_deal, staged)
    rooms_redrawn = redraw_rooms(blocks, enemy_deal, rng)
    redraw_mixed_lists(gw, enemy_deal, rng, staged)
    redraw_overworld(gw, overworld, enemy_deal, rng, staged)
    goriya_tile = pick_goriya_tile(enemy_deal, placed, goriya_tier, rng)
    staged.frames[GORIYA_TILE_OFFSET] = goriya_tile
    staged.frames[FIXED_FRAME_91[0]] = FIXED_FRAME_91[1]
    return enemy_deal, goriya_tile, rooms_redrawn
