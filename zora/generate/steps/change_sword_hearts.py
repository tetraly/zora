"""Change Sword Hearts (B10; FP-SWORD-01): the hearts the sword caves ask for."""

from ...model.enums import Destination
from ...model.overworld import ItemCave, Overworld
from ..rng import IntRng

# FP-SWORD-01: the heart counts the sword caves ask for.
WHITE_SWORD_HEARTS = range(4, 7)
MAGICAL_SWORD_HEARTS = range(10, 15)
# FL-ALT-03 (C20 = 1): the white-sword cave asks for 5 or 6 hearts.
WHITE_SWORD_HEARTS_FROM_FIVE = range(5, 7)


def change_sword_hearts(overworld: Overworld, rng: IntRng, magical_sword_hearts: range = MAGICAL_SWORD_HEARTS) -> None:
    """FP-SWORD-01: white 4..6 hearts, magical 10..14 hearts (or the ZORA cap's
    narrower range, zora_flags.magical_sword_heart_range).

    Drawn before the hint text, which picks heart-count quotes by these
    requirements (docs/ui-provenance.md); the spec constrains only their
    marginal distributions, so stream position does not matter. With
    Randomize Magical Sword on they are drawn before the acceptance check,
    which judges the magical-sword cave's exact requirement."""
    _draw_sword_hearts(overworld, rng, WHITE_SWORD_HEARTS, magical_sword_hearts)


def change_sword_hearts_from_five_hearts(overworld: Overworld, rng: IntRng,
                                         magical_sword_hearts: range = MAGICAL_SWORD_HEARTS) -> None:
    """FL-ALT-03 (C20 = 1): FP-SWORD-01 with the white-sword range 5 to 6, the same draws in the
    same order; the magical sword's range is unchanged."""
    _draw_sword_hearts(overworld, rng, WHITE_SWORD_HEARTS_FROM_FIVE, magical_sword_hearts)


def _draw_sword_hearts(overworld: Overworld, rng: IntRng, white_sword_hearts: range,
                       magical_sword_hearts: range) -> None:
    white_sword_cave = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    magical_sword_cave = overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    if white_sword_cave is not None:
        white_sword_cave.heart_requirement = white_sword_hearts[rng.below(len(white_sword_hearts))]
    if magical_sword_cave is not None:
        magical_sword_cave.heart_requirement = magical_sword_hearts[rng.below(len(magical_sword_hearts))]
