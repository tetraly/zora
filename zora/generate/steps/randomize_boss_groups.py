"""Randomize Boss Groups (B40; PS-BGRP-01 to -03, PS-SPR-02)."""

from dataclasses import dataclass

from zora.generate.rng import IntRng, discard
from zora.generate.shapes.tables import (
    DODONGO_BAD_LAYOUTS,
    GLEEOK4_EXTRA_BAD,
    GLEEOK_BAD_LAYOUTS,
    GOHMA_BAD_LAYOUTS,
)
from zora.generate.steps.group_banks import DISCARDED_DRAWS, GROUPS, OVERWORLD, E, SpriteObject, Staged
from zora.generate.steps.shuffle_enemy_groups import _block_rooms, _renumber
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.levels import LevelBlock
from zora.model.rooms import EnemyInfo
from zora.model.sprites import TILE_BYTES, PatternBlock

# --- PS-BGRP: bosses ----------------------------------------------------------

@dataclass(frozen=True)
class Boss:
    cost: int                                    # deal cost, companion included
    body: SpriteObject
    companion: SpriteObject | None
    variants: tuple[Enemy, ...]                  # PS-BGRP-02's widened list


AQUAMENTUS_FRAMES = (-1, 12)                     # frames in AquamentusTiles
GLEEOK_FRAMES = (-2, 18)                         # frames in GleeokBodyTiles0-2
BOSSES: dict[Enemy, Boss] = {
    E.TRIPLE_DODONGO: Boss(
        36, SpriteObject(36, (PatternBlock.BOSS1257, 448), (155, 10)), None,
        (E.TRIPLE_DODONGO, E.SINGLE_DODONGO)
    ),
    E.GLEEOK_2: Boss(
        34, SpriteObject(32, (PatternBlock.BOSS3468, 0), GLEEOK_FRAMES),
        SpriteObject(2, (PatternBlock.BOSS3468, 736), (198, 1)),
        (E.GLEEOK_2, E.GLEEOK_3, E.GLEEOK_4)
    ),
    E.AQUAMENTUS: Boss(
        20, SpriteObject(20, (PatternBlock.BOSS1257, 0), AQUAMENTUS_FRAMES), None,
        (E.AQUAMENTUS,)
    ),
    E.BLUE_GOHMA: Boss(
        16, SpriteObject(16, (PatternBlock.BOSS3468, 768), (165, 6)), None,
        (E.BLUE_GOHMA, E.RED_GOHMA)
    ),
    E.MANHANDLA: Boss(
        14, SpriteObject(14, (PatternBlock.BOSS3468, 512), (178, 6)), None,
        (E.MANHANDLA,)
    ),
    E.SINGLE_DIGDOGGER: Boss(
        8, SpriteObject(4, (PatternBlock.BOSS1257, 320), (174, 1)),
        SpriteObject(4, (PatternBlock.BOSS1257, 384), (126, 2)),
        (E.SINGLE_DIGDOGGER, E.TRIPLE_DIGDOGGER)
    ),
    E.PATRA_1: Boss(
        8, SpriteObject(4, (PatternBlock.BOSS9, 896), (200, 1)),
        SpriteObject(4, (PatternBlock.BOSS9, 960), (144, 2)),
        (E.PATRA_1, E.PATRA_2)
    ),
}
BOSS_ORDER = tuple(BOSSES)                       # Dodongo, Gleeok, Aquamentus, ...
SPECIAL_CANDIDATES = (E.AQUAMENTUS, E.MANHANDLA, E.SINGLE_DIGDOGGER)
BLOCK_FREE_TILES = (64, 64, 8, 32)
BOSS_BLOCK_TILES = {0: range(192, 256), 1: range(192, 256), 2: range(248, 256),
                    OVERWORLD: range(48, 80)}
BOSS_BLOCKS = {0: PatternBlock.BOSS1257, 1: PatternBlock.BOSS3468, 2: PatternBlock.BOSS9}
BOSS_BLOCK_FIRST_TILE = 192
COMMON_BLOCK_FIRST_TILE = 48
COMMON_BLOCK_OFFSET = 768                        # CommonBackgroundPatterns + 768
COMMON_TABLE_BIT = 1                             # 8x16 tile bit 0: the other table
AQUAMENTUS_FRAME_LIFT = 2                        # its smallest frame is its third tile
GLEEOK_NECK_LIFT, GLEEOK_HEAD_LIFT, GLEEOK_HEAP_LIFT = 26, 28, 30
GLEEOK_HEAP_OFFSET = 199


@dataclass
class BossDeal:
    special: Enemy
    blocks: dict[int, list[Enemy]]               # block -> bosses, special first

    def widened(self, block: int) -> list[Enemy]:
        """PS-BGRP-02: the block's bosses' variants, then the common
        block's."""
        bosses = self.blocks[block] + (self.blocks[OVERWORLD] if block != OVERWORLD else [])
        return [variant for boss in bosses for variant in BOSSES[boss].variants]


def deal_bosses(rng: IntRng) -> BossDeal:
    """PS-BGRP-01: the special boss is reserved into the common block; the
    rest, in the fixed order, draw a block uniformly until they fit."""
    discard(rng, DISCARDED_DRAWS)
    special = SPECIAL_CANDIDATES[rng.below(len(SPECIAL_CANDIDATES))]
    free = list(BLOCK_FREE_TILES)
    free[OVERWORLD] -= BOSSES[special].cost
    blocks: dict[int, list[Enemy]] = {group: [] for group in GROUPS}
    blocks[OVERWORLD].append(special)
    for boss in BOSS_ORDER:
        if boss == special:
            continue
        block = rng.below(len(GROUPS))
        while BOSSES[boss].cost > free[block]:
            block = rng.below(len(GROUPS))
        free[block] -= BOSSES[boss].cost
        blocks[block].append(boss)
    return BossDeal(special, blocks)


def _boss_destination(block: int, tile: int) -> tuple[PatternBlock, int]:
    if block == OVERWORLD:
        return (PatternBlock.COMMON_BACKGROUND,
                COMMON_BLOCK_OFFSET + (tile - COMMON_BLOCK_FIRST_TILE) * TILE_BYTES)
    return BOSS_BLOCKS[block], (tile - BOSS_BLOCK_FIRST_TILE) * TILE_BYTES


def pack_bosses(gw: GameWorld, deal: BossDeal, staged: Staged) -> None:
    """PS-SPR-02: first-fit per block in packing order, companions right
    after their boss; frame bytes renumbered (+1 in the common block), with
    Aquamentus's and Gleeok's operand fix-ups."""
    enemies = gw.enemies
    for block, bosses in deal.blocks.items():
        free = list(BOSS_BLOCK_TILES[block])
        shift = COMMON_TABLE_BIT if block == OVERWORLD else 0
        # Packing follows the dealing order (descending cost), the special
        # boss included: Aquamentus dealt into the common block beside a
        # special Digdogger still takes its first slot.
        for boss in sorted(bosses, key=BOSS_ORDER.index):
            for sprite_object in (BOSSES[boss].body, BOSSES[boss].companion):
                if sprite_object is None:
                    continue
                data = gw.sprites.read_tiles(*sprite_object.source, sprite_object.tiles)
                slots, free = free[:sprite_object.tiles], free[sprite_object.tiles:]
                for tile, tile_data in zip(slots, data, strict=True):
                    staged.tiles.append((*_boss_destination(block, tile), tile_data))
                offset, count = sprite_object.frames
                if sprite_object.frames == AQUAMENTUS_FRAMES:
                    assert enemies.aquamentus_tile_layout_table is not None
                    staged.aquamentus_tiles = _renumber(
                        enemies.aquamentus_tile_layout_table, slots,
                        AQUAMENTUS_FRAME_LIFT + shift
                    )
                    staged.aquamentus_open_mouth = slots[0] + shift
                elif sprite_object.frames == GLEEOK_FRAMES:
                    assert enemies.gleeok_body_tiles is not None
                    body = _renumber(enemies.gleeok_body_tiles, slots, shift)
                    staged.gleeok_body_tiles = body
                    staged.gleeok_neck = body[0] + GLEEOK_NECK_LIFT
                    staged.gleeok_head = body[0] + GLEEOK_HEAD_LIFT
                    staged.frames[GLEEOK_HEAP_OFFSET] = body[0] + GLEEOK_HEAP_LIFT
                else:
                    frames = enemies.frame_bytes(offset, count)
                    staged.frames.update(zip(range(offset, offset + count),
                                             _renumber(frames, slots, shift), strict=True))


OLD_BOSS_GROUPS: dict[int, int] = {
    **dict.fromkeys((E.AQUAMENTUS, E.TRIPLE_DODONGO, E.SINGLE_DODONGO,
                     E.TRIPLE_DIGDOGGER, E.SINGLE_DIGDOGGER), 0),
    **dict.fromkeys((E.MANHANDLA, E.BLUE_GOHMA, E.RED_GOHMA,
                     E.GLEEOK_1, E.GLEEOK_2, E.GLEEOK_3, E.GLEEOK_4), 1),
    **dict.fromkeys((E.PATRA_1, E.PATRA_2), 2),
}
GLEEOK_HEADS = (E.GLEEOK_2, E.GLEEOK_3, E.GLEEOK_4)
GOHMAS = (E.BLUE_GOHMA, E.RED_GOHMA)
DODONGOS = (E.TRIPLE_DODONGO, E.SINGLE_DODONGO)


def is_boss_pick_barred(pick: Enemy, layout: int, has_push_block: bool) -> bool:
    """PS-BGRP-03's layout bars, on the pick's value and the layout's low
    six bits."""
    if pick in GLEEOK_HEADS:
        return (has_push_block or layout in GLEEOK_BAD_LAYOUTS
                or (pick == E.GLEEOK_4 and layout in GLEEOK4_EXTRA_BAD))
    if pick in GOHMAS:
        return layout in GOHMA_BAD_LAYOUTS
    if pick in DODONGOS:
        return layout in DODONGO_BAD_LAYOUTS
    return False


def redraw_bosses(blocks: list[LevelBlock], deal: BossDeal, rng: IntRng) -> int:
    """PS-BGRP-03: every boss room's boss (combined value, count bits
    ignored) is redrawn from its old group's block, until the layout
    allows it. The monster byte becomes the pick's low six bits with count
    0, and the monster bit follows the pick ($40 and up set it)."""
    rewritten = 0
    for block in blocks:
        for room in _block_rooms(block):
            old_group = OLD_BOSS_GROUPS.get(room.enemy.value)
            if old_group is None:
                continue
            choices = deal.widened(old_group)
            pick = choices[rng.below(len(choices))]
            while is_boss_pick_barred(pick, room.room_type, room.movable_block):
                pick = choices[rng.below(len(choices))]
            room.enemy_info = EnemyInfo(pick)
            rewritten += 1
    return rewritten


def randomize_boss_groups(blocks: list[LevelBlock], gw: GameWorld, rng: IntRng,
                          staged: Staged) -> tuple[BossDeal, int]:
    """PS-BGRP-01..03: deal the bosses into pattern blocks, pack their tiles
    and redraw every boss room from its block. Returns the deal and the
    number of bosses redrawn."""
    boss_deal = deal_bosses(rng)
    pack_bosses(gw, boss_deal, staged)
    return boss_deal, redraw_bosses(blocks, boss_deal, rng)
