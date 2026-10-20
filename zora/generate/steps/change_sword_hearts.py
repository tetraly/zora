"""Change Sword Hearts (B10; FP-SWORD-01): the hearts the sword caves ask for."""

from ...model.enums import Destination
from ...model.overworld import ItemCave, Overworld
from ..rng import IntRng

# FP-SWORD-01: the heart counts the sword caves ask for, with C20 to C23 at 0.
WHITE_SWORD_HEARTS = range(4, 7)
MAGICAL_SWORD_HEARTS = range(10, 15)


def change_sword_hearts(overworld: Overworld, rng: IntRng, magical_sword_hearts: range = MAGICAL_SWORD_HEARTS,
                        white_sword_hearts: range = WHITE_SWORD_HEARTS) -> None:
    """FP-SWORD-01 with FL-ALT-05's ranges: the white sword's from 4 + C20 to 6 - C21, the
    magical sword's from 10 + C22 to 14 - C23 (or the ZORA cap's narrower range,
    zora_flags.magical_sword_heart_range), each swapped when its lowest is above its highest
    (FL-DEP-03). One draw each, taken whatever the range, also when it holds one count.

    Drawn before the hint text, which picks heart-count quotes by these
    requirements (docs/ui-provenance.md); the spec constrains only their
    marginal distributions, so stream position does not matter (FL-SEED-01).
    With Randomize Magical Sword on they are drawn before the acceptance check,
    which judges the magical-sword cave's exact requirement."""
    white_sword_cave = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    magical_sword_cave = overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    if white_sword_cave is not None:
        white_sword_cave.heart_requirement = white_sword_hearts[rng.below(len(white_sword_hearts))]
    if magical_sword_cave is not None:
        magical_sword_cave.heart_requirement = magical_sword_hearts[rng.below(len(magical_sword_hearts))]
