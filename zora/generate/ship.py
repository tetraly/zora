"""Shipping an accepted generation attempt (SH-FLOW-02): its staged levels,
blocks and results are written into the GameWorld in SHIP_STEPS order. A
restarted attempt never reaches here, so the GameWorld keeps the base's values."""
from collections.abc import Callable
from dataclasses import dataclass, field

from ..model.enums import BossSpriteSet, Destination, EnemySpriteSet, Item
from ..model.game_world import GameWorld
from ..model.levels import Level, LevelBlock
from ..model.overworld import HintShop, ItemCave, OverworldItem, Quote
from .shapes.world import SetWorld
from .shapes.writeback import build_block, build_level
from .steps.assign_hints_for_hint_type import HintAssignmentResult
from .steps.cave_entries import OverworldResult
from .steps.change_enemy_hp import EnemyHpResult, apply_enemy_hp
from .steps.extra_pool_items import ExtraPoolItems, apply_extra_pool_items
from .steps.hint_text import HintTextResult
from .steps.item_shuffle_result import ItemShuffleResult
from .steps.monster_lists import MonsterShuffleResult
from .steps.shuffle_dungeon_palettes import DungeonPaletteResult, apply_dungeon_palettes
from .steps.shuffle_groups import GroupShuffleResult, apply_groups
from .steps.shuffle_hungry_goriya import GORIYA_TILE_INDEX
from .steps.shuffle_start_screen import StartScreen, apply_start_screen


@dataclass
class StagedSets:
    """A pass's two finished sets as the GameWorld holds them: both quest-1
    blocks and the nine levels, in level order."""
    blocks: list[LevelBlock]
    levels: list[Level]
    # The same levels in the order the shape stage made them (set by set,
    # blob by blob). A pass that draws once per level walks them in this
    # order, which keeps the random stream as it was on the plans.
    generation_order: list[Level]


@dataclass
class Staged:
    """One accepted generation pass's results, written into the GameWorld
    only when the pass ships (a restarted pass never touches it)."""
    sets: StagedSets
    item_shuffle_result: ItemShuffleResult
    overworld: OverworldResult | None
    hints: HintAssignmentResult | None
    monster_shuffle: MonsterShuffleResult | None
    hit_points: EnemyHpResult | None
    groups: GroupShuffleResult | None
    colors: DungeonPaletteResult | None
    start: StartScreen | None
    extras: ExtraPoolItems = field(default_factory=ExtraPoolItems)


def _ship_sets(gw: GameWorld, staged: Staged) -> None:
    gw.blocks, gw.levels = staged.sets.blocks, staged.sets.levels


def _ship_overworld(gw: GameWorld, staged: Staged) -> None:
    if staged.overworld is not None:
        gw.overworld = staged.overworld.overworld


def _ship_item_shuffle(gw: GameWorld, staged: Staged) -> None:
    _apply_item_shuffle(gw, staged.item_shuffle_result)


def _ship_extra_pool_items(gw: GameWorld, staged: Staged) -> None:
    apply_extra_pool_items(gw, staged.extras)


def _ship_hints(gw: GameWorld, staged: Staged) -> None:
    if staged.hints is not None:
        gw.person_inits = staged.hints.person_inits()


def _displayed_quotes(hint_text: HintTextResult) -> list[Quote]:
    """Reorder quotes so that each slot's quote is the text displayed there.

    The encoded bodies in hint_text.text_bytes are written in original slot
    order; hint_text.pointers permutes them. Build the inverse map so
    gw.quotes matches what parse_rom produces for the same ROM.
    """
    from ..rom.layout import CONSTERNATION_HINT_SLOTS, cpu_address_in_bank1, place_hint_texts
    offsets = place_hint_texts([len(body) for body in hint_text.text_bytes], CONSTERNATION_HINT_SLOTS)
    original_addresses = [cpu_address_in_bank1(offset) for offset in offsets]
    original_slot_of = {cpu_address: slot for slot, cpu_address in enumerate(original_addresses)}
    displayed: list[Quote | None] = [None] * len(hint_text.quotes)
    for final_slot, cpu_address in enumerate(hint_text.pointers):
        orig_slot = original_slot_of.get(cpu_address)
        if orig_slot is not None:
            displayed[final_slot] = hint_text.quotes[orig_slot]
    # Any unmatched slot (e.g., slot 27 patched to the toll text) keeps its
    # original-slot text; hint checkpoints do not use such slots.
    for slot, quote in enumerate(displayed):
        if quote is None:
            displayed[slot] = hint_text.quotes[slot]
    return displayed  # type: ignore[return-value]


def ship_hint_text(gw: GameWorld, hint_text: HintTextResult) -> None:
    """Write the composed hint text into the shipped GameWorld."""
    gw.quotes = _displayed_quotes(hint_text)
    gw.quotes_raw = b""
    gw.hint_pointers = hint_text.pointers
    gw.hint_text_bytes = hint_text.text_bytes
    gw.white_sword_text_selector = hint_text.white_sword_selector
    gw.hint_shop_offer_selectors = hint_text.hint_shop_offer_selectors
    gw.underworld_text_selectors_a = hint_text.underworld_selectors_a
    gw.underworld_text_selectors_b = hint_text.underworld_selectors_b
    gw.hint_overlay_flags = hint_text.overlay_flags
    price_index = 0
    for destination in (Destination.HINT_SHOP_1, Destination.HINT_SHOP_2):
        shop = gw.overworld.get_cave(destination, HintShop)
        if shop is not None:
            for hint in shop.hints:
                if price_index < len(hint_text.hint_shop_prices):
                    hint.price = hint_text.hint_shop_prices[price_index]
                    price_index += 1


def _ship_start_screen(gw: GameWorld, staged: Staged) -> None:
    if staged.start is not None:
        apply_start_screen(gw.overworld, staged.start)


def _ship_monster_shuffle(gw: GameWorld, staged: Staged) -> None:
    if staged.monster_shuffle is not None:
        _apply_monster_shuffle(gw, staged.monster_shuffle)


def _ship_hit_points(gw: GameWorld, staged: Staged) -> None:
    if staged.hit_points is not None:
        apply_enemy_hp(gw, staged.hit_points)


def _ship_groups(gw: GameWorld, staged: Staged) -> None:
    if staged.groups is not None:
        apply_groups(gw, staged.groups)


def _ship_colors(gw: GameWorld, staged: Staged) -> None:
    if staged.colors is not None:
        apply_dungeon_palettes(gw, staged.colors)


# The order the staged results are written in when a pass ships. It
# matters where two steps write the same thing:
#   - the overworld copy replaces gw.overworld, so it goes before B1, whose
#     cave items (PS-ITEM-01) are written onto it;
#   - B1, B2 and the groups each write the goriya tile, and the groups'
#     (PS-EGRP-06) is the one that ships, so the groups come after both;
#   - the start screen (OW-START-01) exchanges the overworld monster groups
#     as they stand after PS-EGRP-05, so it comes after the groups.
# tests/test_flow.py pins this order.
SHIP_STEPS: tuple[tuple[str, Callable[[GameWorld, Staged], None]], ...] = (
    ("sets", _ship_sets),                        # both level blocks and the nine levels
    ("overworld", _ship_overworld),              # the staged overworld copy
    ("item shuffle", _ship_item_shuffle),        # B1's caves, goriya tile, toll, bomb levels
    ("extra pool items", _ship_extra_pool_items),  # the ZORA extras' caves (on the shipped overworld)
    ("hints", _ship_hints),                      # B2.5's person inits
    ("monster shuffle", _ship_monster_shuffle),  # B2's banks and goriya tile
    ("hit points", _ship_hit_points),            # B8's hit points
    ("groups", _ship_groups),                    # B4's tiles, frames, lists, overworld monsters
    ("colors", _ship_colors),                    # B5's color sets
    ("start screen", _ship_start_screen),        # OW-START-01's start screen, Y and monster exchange
)


def ship(gw: GameWorld, staged: Staged) -> None:
    """Write an accepted pass into the GameWorld, step by step in SHIP_STEPS order."""
    for _name, step in SHIP_STEPS:
        step(gw, staged)



def build_sets(gw: GameWorld, worlds: list[SetWorld]) -> StagedSets:
    """Both quest-1 blocks and all nine levels built from the shape stage's
    plans, on the base GameWorld's (its palettes, item positions and counts
    are kept). The post-shapes passes, the late gate and the passes after
    it work on the result; the GameWorld is not touched until the pass
    ships it."""
    blocks = [build_block(base, world) for base, world in zip(gw.blocks, worlds, strict=True)]
    new_levels: list[Level] = []
    for block, world in zip(blocks, worlds, strict=True):
        for blob in range(world.blob_count):
            base = gw.levels[world.levels[blob] - 1]
            new_levels.append(build_level(base, world, blob, block))
    return StagedSets(blocks, sorted(new_levels, key=lambda level: level.level_num), new_levels)


def _cave_slot(gw: GameWorld, slot: str) -> OverworldItem | ItemCave:
    overworld = gw.overworld
    cave: OverworldItem | ItemCave | None
    if slot == "armos":
        cave = overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    elif slot == "coast":
        cave = overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    else:
        cave = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert cave is not None, slot
    return cave


def cave_item_bytes(gw: GameWorld) -> dict[str, int]:
    """The three special-cave item bytes (PS-ITEM-01's cave slots)."""
    return {slot: int(_cave_slot(gw, slot).item) for slot in ("armos", "white_sword", "coast")}


def _write_goriya_tile(gw: GameWorld, tile: int) -> None:
    """PS-GRUM-03 / PS-MONLV-06: ObjAnimFrameHeap + 171. Two frame lists
    start there (the rupee boss shares the goriya's pointer); both carry
    the byte."""
    enemies = gw.enemies
    for enemy, pointer in enemies.tile_pointers.items():
        frames = enemies.tile_frames[enemy]
        if pointer <= GORIYA_TILE_INDEX < pointer + len(frames):
            frames[GORIYA_TILE_INDEX - pointer] = tile


def _apply_item_shuffle(gw: GameWorld, item_shuffle_result: ItemShuffleResult) -> None:
    """Write B1's staged outside-the-block results into the GameWorld."""
    for slot, item_byte in item_shuffle_result.caves.items():
        _cave_slot(gw, slot).item = Item(item_byte)
    if item_shuffle_result.goriya_tile is not None:
        _write_goriya_tile(gw, item_shuffle_result.goriya_tile)
    gw.life_or_money_toll = item_shuffle_result.toll
    gw.bomb_upgrade_levels = item_shuffle_result.bomb_levels


# PS-BOSS-01 / PS-MONLV-01: bank tiers 0, 1, 2
BOSS_BANKS = (BossSpriteSet.A, BossSpriteSet.B, BossSpriteSet.C)
ENEMY_BANKS = (EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C)


def _apply_monster_shuffle(gw: GameWorld, monster_shuffle: MonsterShuffleResult) -> None:
    """Write B2's staged banks and goriya tile into the GameWorld. Level 9's
    boss bank is never drawn (PS-BOSS-06) and keeps the shape stage's."""
    for level in gw.levels:
        if level.level_num in monster_shuffle.boss_tiers:
            level.boss_sprite_set = BOSS_BANKS[monster_shuffle.boss_tiers[level.level_num]]
        level.enemy_sprite_set = ENEMY_BANKS[monster_shuffle.enemy_tiers[level.level_num]]
    if monster_shuffle.goriya_tile is not None:
        _write_goriya_tile(gw, monster_shuffle.goriya_tile)

