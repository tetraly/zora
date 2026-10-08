"""Shuffle Dungeon Text (B19; hints-behavior.md HT-TEXT-04): the dungeon hint
texts exchange pointers, not room codes."""
from dataclasses import replace

from zora.generate.rng import IntRng, discard
from zora.generate.steps.hint_text import HintTextResult

# HT-TEXT-04: the slots whose pointers are exchanged, in walk order (slot 38
# first, not slot 19, which belongs to the white-sword cave)
SHUFFLED_SLOTS = (38, 20, 21, 22, 23, 24, 28, 29, 31, 32, 33)
HINT_POINTER_DISCARDS = 2          # discarded before the eleven partner draws


def shuffle_dungeon_text(hint_text: HintTextResult, rng: IntRng) -> HintTextResult:
    """HT-TEXT-04: two discarded draws, then a Fisher-Yates over the pointers
    of SHUFFLED_SLOTS, in that order. The text bytes stay in place. With B19
    off (FL-OFF-04) this does not run and each slot shows its own text."""
    pointers = list(hint_text.pointers)
    slots = list(SHUFFLED_SLOTS)
    discard(rng, HINT_POINTER_DISCARDS)
    for i in range(len(slots)):
        j = i + rng.below(len(slots) - i)
        pointers[slots[i]], pointers[slots[j]] = pointers[slots[j]], pointers[slots[i]]
    return replace(hint_text, pointers=tuple(pointers))
