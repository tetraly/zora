"""Post-shapes pass B5: the dungeon color sets (docs/spec/post-shapes-b5.md
@ a123227, PS-COLOR-01..03).

Runs after the hint assignment and immediately before the boss shuffle.
Nine of 23 candidate color-set pairs are drawn without replacement and
given to levels 1-9. Room palette selectors are never touched
(PS-COLOR-01). The draw is staged and written into the GameWorld when the
generation pass ships (generation_pass.py), so candidates are always built from the
base ROM's own sets.
"""
from dataclasses import dataclass

from ...model.game_world import GameWorld
from ..rng import IntRng, discard

ColorPair = tuple[bytes, bytes]                  # (set 1: 32 bytes, set 2: 96 bytes)

DISCARDED_DRAWS = 3
CANDIDATE_LEVELS = range(1, 9)                   # levels 1-8's own pairs
LOW_NIBBLE = 0x0F
RAISED_FROM, RAISED_TO = 0x0C, 0x04              # the clone: low nibble $C -> $4
# Template variants: set 1 bytes 8-15, set 2 bytes 0-7 and 64-71 take the
# eight colors; set 1 bytes 28-31 the first four.
EIGHT_COLOR_SPANS = ((0, slice(8, 16)), (1, slice(0, 8)), (1, slice(64, 72)))
FOUR_COLOR_SPAN = (0, slice(28, 32))
# Then every position whose ORIGINAL first-pair byte is 12, 28 or 44 takes
# the template's 2nd, 3rd or 4th color (last, so it wins).
VALUE_TO_TEMPLATE_INDEX = {12: 1, 28: 2, 44: 3}
TEMPLATES = (
    (15, 17, 33, 60, 15, 18, 33, 60),
    (15, 17, 33, 60, 15, 17, 33, 60),
    (15, 11, 26, 41, 15, 24, 26, 41),
    (15, 11, 26, 41, 15, 18, 26, 41),
    (15, 24, 40, 56, 15, 22, 40, 56),
    (15, 24, 40, 56, 15, 24, 40, 56),
    (15, 4, 21, 38, 15, 4, 21, 38),
    (15, 14, 45, 61, 15, 10, 45, 61),
    (15, 14, 45, 61, 15, 7, 45, 61),
    (15, 0, 29, 19, 15, 4, 29, 19),
    (15, 29, 24, 61, 15, 9, 24, 61),
    (15, 61, 34, 32, 15, 49, 34, 32),
    (15, 5, 36, 48, 15, 50, 36, 48),
    (15, 1, 45, 61, 15, 15, 1, 61),
)
DUNGEON_LEVELS = range(1, 10)


def _raised_clone(pair: ColorPair) -> ColorPair:
    def raise_bytes(data: bytes) -> bytes:
        return bytes((value & ~LOW_NIBBLE) | RAISED_TO if value & LOW_NIBBLE == RAISED_FROM else value
                     for value in data)
    return raise_bytes(pair[0]), raise_bytes(pair[1])


def _template_variant(first: ColorPair, template: tuple[int, ...]) -> ColorPair:
    sets = [bytearray(first[0]), bytearray(first[1])]
    for which, span in EIGHT_COLOR_SPANS:
        sets[which][span] = bytes(template)
    which, span = FOUR_COLOR_SPAN
    sets[which][span] = bytes(template[:4])
    for original, current in zip(first, sets, strict=True):
        for position, value in enumerate(original):
            if value in VALUE_TO_TEMPLATE_INDEX:
                current[position] = template[VALUE_TO_TEMPLATE_INDEX[value]]
    return bytes(sets[0]), bytes(sets[1])


def color_candidates(gw: GameWorld) -> list[ColorPair]:
    """PS-COLOR-02's 23 candidates: levels 1-8's pairs as read, the first
    pair's raised clone, and 14 template variants of the first pair."""
    level_pairs = [gw.levels[level - 1].color_sets for level in CANDIDATE_LEVELS]
    first = level_pairs[0]
    return (level_pairs + [_raised_clone(first)]
            + [_template_variant(first, template) for template in TEMPLATES])


@dataclass
class DungeonPaletteResult:
    picks: list[int]                             # candidate index per level 1-9
    pairs: list[ColorPair]


def shuffle_dungeon_palettes(gw: GameWorld, rng: IntRng) -> DungeonPaletteResult:
    """PS-COLOR-02: nine distinct candidates, uniformly without
    replacement, for levels 1-9 in order. Stream note (non-normative): a
    full Fisher-Yates over the 23 indices whose position 0 is unused."""
    candidates = color_candidates(gw)
    discard(rng, DISCARDED_DRAWS)
    order = list(range(len(candidates)))
    for position in range(len(order) - 1, 0, -1):
        other = rng.below(position + 1)
        order[position], order[other] = order[other], order[position]
    picks = order[1:1 + len(DUNGEON_LEVELS)]
    return DungeonPaletteResult(picks, [candidates[pick] for pick in picks])


def apply_dungeon_palettes(gw: GameWorld, state: DungeonPaletteResult) -> None:
    for level, pair in zip(DUNGEON_LEVELS, state.pairs, strict=True):
        gw.levels[level - 1].set_color_sets(*pair)
