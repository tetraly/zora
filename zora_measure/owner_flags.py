"""The owner's 2.0 flags' invariants on a shipped world (docs/design/zora-flags-2.0.md; owner
decisions 2026-10-07), for the QA sweep and the tests: the wooden-sword cave off every gated
screen, each hint shop off its own maze's screens, each randomized maze's sequence by its rules and
its hint shop offer naming it at 1 rupee, the letter never in the potion shop, and Add L4 Sword's
one progressive sword in a level-9 room that docs/design/l4-sword.md R5-R6 allow, in the top half
of the triforce-checker room when it is there (R6a), and with Add L4 Sword = Level 2 (ASNB) level
2's one item cellar."""
from __future__ import annotations

from zora.generate.late_gate.walk import level9_entry_room
from zora.generate.shapes.tables import LEVEL_2_SWORD_LEVEL
from zora.generate.steps.add_l4_sword import (
    L4_SWORD_ITEM,
    POSITION_Y_MASK,
    TOP_HALF_Y_BELOW,
    collectible_rooms,
    qualifies,
)
from zora.generate.steps.extra_pool_items import item_cellars
from zora.generate.steps.overworld_gates import OverworldGates
from zora.generate.steps.randomize_mazes import DEAD_WOODS, LOST_HILLS, MAZE_HINT_PRICE, maze_hint
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.levels import LEVEL_9
from zora.model.overworld import HintShop, Shop

SELECTOR_TO_SLOT = 2


def owner_flag_problems(world: GameWorld, gates: OverworldGates, l4_sword: bool = False,
                        level_2_sword: bool = False) -> list[str]:
    """Every invariant the shipped world breaks (empty when none). l4_sword: Add L4 Sword =
    Level 9's sword; level_2_sword: Add L4 Sword = Level 2's cellar (ASNB: level 2 has exactly one
    item cellar)."""
    problems: list[str] = []
    overworld = world.overworld
    screens = {d: [s for s, screen in enumerate(overworld.screens) if screen.destination == d]
               for d in (Destination.WOOD_SWORD_CAVE, Destination.HINT_SHOP_1, Destination.HINT_SHOP_2)}
    if set(screens[Destination.WOOD_SWORD_CAVE]) & gates.wood_sword_barred():
        problems.append(f"wooden sword on a gated screen {screens[Destination.WOOD_SWORD_CAVE]}")
    problems.extend(f"{shop.name} behind its own maze at {screens[shop]}"
                    for shop in (Destination.HINT_SHOP_1, Destination.HINT_SHOP_2)
                    if set(screens[shop]) & gates.barred_for(shop))
    texts = {quote.quote_id: quote.text for quote in world.quotes}
    prices = [hint.price for cave in overworld.caves if isinstance(cave, HintShop) for hint in cave.hints]
    selectors = world.hint_shop_offer_selectors
    for on, maze, sequence in ((gates.lost_hills, LOST_HILLS, overworld.lost_hills_directions),
                               (gates.dead_woods, DEAD_WOODS, overworld.dead_woods_directions)):
        if not on:
            continue
        if len(sequence) != 4 or sequence[-1] != maze.last or any(step not in maze.choices for step in sequence):
            problems.append(f"{maze.name} sequence {[step.name for step in sequence]}")
        assert selectors is not None
        text = texts[selectors[maze.hint_shop_offer] // SELECTOR_TO_SLOT]
        shown = "|".join(line.strip("~ ") for line in text.split("|"))
        if shown != "|".join(maze_hint(maze, sequence)) or prices[maze.hint_shop_offer] != MAZE_HINT_PRICE:
            problems.append(f"{maze.name} hint {shown!r} at {prices[maze.hint_shop_offer]} rupees")
    potion = overworld.get_cave(Destination.POTION_SHOP, Shop)
    assert isinstance(potion, Shop)
    if any(ware.item == Item.LETTER for ware in (*potion.items, *([potion.middle] if potion.middle else []))):
        problems.append("the letter is in the potion shop")
    if l4_sword:
        level9 = next(level for level in world.levels if level.level_num == LEVEL_9)
        swords = [room for room in level9.rooms if room.item == L4_SWORD_ITEM]
        if len(swords) != 1 or not qualifies(level9, swords[0], collectible_rooms(level9), L4_SWORD_ITEM):
            problems.append(f"L4 sword rooms {[f'{room.room_num:02X}' for room in swords]}")
        elif swords[0].room_num == level9_entry_room(level9):
            y = level9.item_position_table[swords[0].item_position] & POSITION_Y_MASK
            if y >= TOP_HALF_Y_BELOW:
                problems.append(f"L4 sword in the triforce-checker room at Y ${y:X}, not the top half")
    if level_2_sword:
        level2 = next(level for level in world.levels if level.level_num == LEVEL_2_SWORD_LEVEL)
        cellars = len(list(item_cellars(level2)))
        if cellars != 1:
            problems.append(f"level 2 has {cellars} item cellars")
    return problems
