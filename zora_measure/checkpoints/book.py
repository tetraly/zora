"""Book to Understand NPCs (B48; hints-behavior.md HT-BOOK): the Checks measured on finished ROMs,
against the original randomizer's b48 corpus (corpus("b48"); hash manifest in docs/spec/)."""
from zora.model.game_world import GameWorld

SPEC_HT_BOOK = "hints-behavior.md @ 3a9a4dd"
# The b48 corpus's flag string: the MVP baseline's with B48 on
BOOK_FLAGS = "8iaDYa1PX9GK!pC9GIQIO5JJE!UJ3A"
# HT-BOOK-01: the three bytes at 0x04847 with B48 (JSR $9F30) and in PRG0 (LDA $8000, Y)
BOOK_POINTER_LOAD = bytes.fromhex("20309f")
PRG0_POINTER_LOAD = bytes.fromhex("b90080")
POINTER_LOAD_KEYS = ("B48's call", "PRG0's load")


def person_text_pointer_load(gw: GameWorld) -> dict[str, bool]:
    """HT-BOOK-01's Check: the text-pointer load is B48's call, or PRG0's load."""
    return {"B48's call": gw.person_text_pointer_load == BOOK_POINTER_LOAD,
            "PRG0's load": gw.person_text_pointer_load == PRG0_POINTER_LOAD}
