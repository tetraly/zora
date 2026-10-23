"""Level 9 Entry (C08; features-behavior.md FP-TRIF-01 to FP-TRIF-06): what level 9's entrance asks
for in a generation pass, and the person's refusal text, which names it.

C08 = 0 to 7 ask for 8 down to 1 pieces and C08 = 8 for nothing, fixed by the field (no draw);
C08 = 9 draws the count from the range C24 to 8 - C25, C08 = 10 draws a count the same way and then
that many levels, and C08 = 11 draws an item, each pass anew, so a rejected pass's draws go with it
(VA-REJ-06). C08 = 12 is resolved once per seed, before the first pass (FL-DEP-04), and never
reaches here. Where in generation's stream the draws are taken is not normative (FL-SEED-01).

ZORA's own rulings (owner, 2026-10-22; docs/deviations.md): Other Item never draws the letter
(model/level_9_gate.GATE_ITEMS), and the acceptance check requires the drawn item before level 9
whatever it is (acceptance_check.LogicRules.level_9_gate). No hint names the count, the levels or
the item: only the entrance's bytes and this text show them.
"""
from dataclasses import dataclass

from ...flags.fields import Level9Requirement, WoodenSwordState
from ...model.enums import Item
from ...model.level_9_gate import (
    ALL_PIECES,
    EIGHT_PIECES,
    GATE_ITEMS,
    OPEN_GATE,
    TRIFORCE_LEVELS,
    GateKind,
    Level9Gate,
    item_gate,
    levels_gate,
    pieces_gate,
)
from ...rom.level_9_entrance import chosen_levels_text
from ..rng import Rng

DRAWN = frozenset({Level9Requirement.RANDOM_COUNT_IN_RANGE, Level9Requirement.SPECIFIC_PIECES,
                   Level9Requirement.ITEM_INSTEAD_OF_PIECES})


@dataclass(frozen=True)
class Level9Entry:
    """C08 after its random index is drawn (its index: 1 to 6 have no Level9Requirement name), with
    what its draws read."""
    requirement: int = Level9Requirement.EIGHT_PIECES
    piece_range: tuple[int, int] = (0, ALL_PIECES)        # FL-DEP-03: (C24, 8 - C25), in order
    wooden_sword_state: WoodenSwordState = WoodenSwordState.NORMAL

    @property
    def draws(self) -> bool:
        """C08 = 9, 10 and 11 draw in every pass."""
        return self.requirement in DRAWN

    @property
    def fixed_gate(self) -> Level9Gate:
        """The gate of a value that draws nothing (C08 = 0 to 8); for the others, until a pass draws."""
        if self.requirement <= Level9Requirement.ONE_PIECE:
            return pieces_gate(ALL_PIECES - self.requirement)
        if self.requirement == Level9Requirement.OPEN:
            return OPEN_GATE
        return EIGHT_PIECES


EIGHT_PIECES_ENTRY = Level9Entry()


def gate_items(wooden_sword_state: WoodenSwordState) -> tuple[Item, ...]:
    """FP-TRIF-06's draw, as the owner ruled: GATE_ITEMS, less the sword under Swordless (C07 = 3)."""
    if wooden_sword_state is WoodenSwordState.SWORDLESS:
        return tuple(item for item in GATE_ITEMS if item is not Item.WOOD_SWORD)
    return GATE_ITEMS


def draw_piece_count(entry: Level9Entry, rng: Rng) -> int:
    """FP-TRIF-04: one draw, uniform over the range, both ends included (taken when they are equal too)."""
    low, high = entry.piece_range
    return low + rng.below(high - low + 1)


def draw_levels(count: int, rng: Rng) -> frozenset[int]:
    """FP-TRIF-05: `count` of levels 1 to 8 by a partial shuffle, every set equally likely: at step i
    a partner is drawn among positions i to 7 and exchanged, and the level now at i is chosen."""
    levels = list(TRIFORCE_LEVELS)
    for position in range(count):
        partner = position + rng.below(len(levels) - position)
        levels[position], levels[partner] = levels[partner], levels[position]
    return frozenset(levels[:count])


def draw_level_9_gate(entry: Level9Entry, rng: Rng) -> Level9Gate:
    """FP-TRIF-04 to FP-TRIF-06: this pass's gate."""
    if entry.requirement == Level9Requirement.RANDOM_COUNT_IN_RANGE:
        return pieces_gate(draw_piece_count(entry, rng))
    if entry.requirement == Level9Requirement.SPECIFIC_PIECES:
        return levels_gate(draw_levels(draw_piece_count(entry, rng), rng))
    if entry.requirement == Level9Requirement.ITEM_INSTEAD_OF_PIECES:
        return item_gate(rng.choice(gate_items(entry.wooden_sword_state)))
    return entry.fixed_gate


COUNT_WORDS = ("NO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT")
# FP-TRIF-06: how the text names each item; the gate admits any sword, either candle, either arrow
GATE_ITEM_WORDS = {
    Item.WOOD_SWORD: "A SWORD", Item.RECORDER: "THE RECORDER", Item.BLUE_CANDLE: "A CANDLE",
    Item.WOOD_ARROWS: "AN ARROW", Item.BOW: "THE BOW", Item.MAGICAL_KEY: "THE MAGICAL KEY",
    Item.RAFT: "THE RAFT", Item.LADDER: "THE LADDER", Item.WAND: "THE MAGICAL ROD", Item.BOOK: "THE BOOK OF MAGIC",
    Item.POWER_BRACELET: "THE POWER BRACELET",
}


def refusal_text(gate: Level9Gate) -> str:
    """The entrance person's text (FP-TRIF-01 to FP-TRIF-06): the count, the chosen levels or the
    item. Under C08 = 8 and a count of 0 it is never shown. PRG0's eight keep ZORA's text of
    every earlier release."""
    if gate.kind is GateKind.ITEM:
        assert gate.item is not None
        return f"YOU NEED\n{GATE_ITEM_WORDS[gate.item]}."
    if gate.kind is GateKind.LEVELS and gate.levels:
        return chosen_levels_text(gate.levels)
    plural = "" if gate.pieces == 1 else "S"
    return f"YOU NEED {COUNT_WORDS[gate.pieces]}\nTRIFORCE PIECE{plural}."
