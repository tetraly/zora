"""Encode level data (features-behavior.md FP-TOURNEY-01): the public interface.

With level encoding on, the finished ROM stores most dungeon and overworld
data in an encoded form that the game decodes as it loads a level, so ROM
editors and map viewers can't read it; gameplay is exactly the same. The
encoder lives in the owner's private repo, checked out (when present) at
`private/` in this folder and never committed here; this module imports it.
Without it, level encoding is not available: asking for it raises
`LevelEncodingUnavailable`, never a silent plain build.

The encoding protects the overworld block and the two first-quest room blocks
and takes the space of the two second-quest blocks for itself. Second-quest
dungeons (Dungeon Quest's 2nd Quest, or a second-quest half of Mixed + Shapes)
still work: just before the encoding, `fold_second_quest_blocks` copies each
second-quest set's block into that set's first-quest block and points the set's
levels there (owner decision, 2026-10-12). It runs only with level encoding on,
so a plain build is unchanged.
"""
from __future__ import annotations

import importlib
from types import ModuleType

from .game_config import LevelEncodingKey
from .layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    ROOM_BLOCK_ADDRESSES_Q1,
    ROOM_BLOCK_HIGH_BYTES,
)

PRIVATE_MODULE = "private.level_encoding.encoder"

LABEL = "Encode level data"
HELP_TEXT = ("Encodes most dungeon and overworld data so ROM editors and map viewers "
             "(like the Z1R Visualizer) can't read it. Gameplay is exactly the same. "
             "This isn't cheat-proof: a determined person can still decode the data.")
UNAVAILABLE_TEXT = "Level encoding is not available in this build."

# The level data the encoding replaces: the overworld and the two
# first-quest dungeon blocks (encoded) and the two second-quest blocks (key
# material and decoder), file offsets 0x18410-0x1930F.
LEVEL_DATA_START = 0x18410
LEVEL_DATA_END = 0x19310
PLAIN_BLOCKS_SIZE = 0x900        # the three blocks the game loads

# The two sets of levels (SH-SRC-02): levels 1-6 read one room block, levels 7-9 another, each
# either its first-quest block or its second-quest block.
SET_LEVELS = (range(1, 7), range(7, 10))
ROOM_BLOCK_SIZE = 0x300
FIRST_QUEST_BLOCKS = (LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS)
SECOND_QUEST_BLOCKS = (LEVEL_1_6_DATA_ADDRESS_Q2, LEVEL_7_9_DATA_ADDRESS_Q2)
FIRST_QUEST_HIGH_BYTES = ROOM_BLOCK_HIGH_BYTES[:2]
SECOND_QUEST_HIGH_BYTES = ROOM_BLOCK_HIGH_BYTES[2:]


class LevelEncodingUnavailable(RuntimeError):
    """Level encoding was asked for, but the private module is not installed."""

    def __init__(self) -> None:
        super().__init__(UNAVAILABLE_TEXT)


def _load() -> ModuleType | None:
    try:
        return importlib.import_module(PRIVATE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name is not None and PRIVATE_MODULE.startswith(exc.name):
            return None
        raise                    # the module is there but broken: say so


_ENCODER = _load()


def is_available() -> bool:
    return _ENCODER is not None


def require_available() -> ModuleType:
    if _ENCODER is None:
        raise LevelEncodingUnavailable
    return _ENCODER


def encode_rom(rom: bytes, key: LevelEncodingKey) -> bytes:
    """The finished ROM with its level data encoded (same size)."""
    encoder = require_available()
    encoded: bytes = encoder.apply(fold_second_quest_blocks(rom), key.seed, key.settings_bytes)
    return encoded


def fold_second_quest_blocks(rom: bytes) -> bytes:
    """The ROM the encoding receives: each set of levels that reads its second-quest room block
    reads a copy of it in its first-quest block instead (owner decision, 2026-10-12).

    The encoding replaces the two second-quest blocks, so a set reading one (Dungeon Quest's
    2nd Quest, a second-quest half of Mixed + Shapes) moves to its first-quest block, which no
    level of that set reads: its 768 bytes become the second-quest block's, and the set's levels'
    room-block high bytes ($8D, $90) become the first-quest ones ($87, $8A). A room block holds
    no addresses and the game reads it only when it loads a level, so play is unchanged. Owner
    ruling (FP-TOURNEY-01): the changed pointer bytes are data the protection method needs. Runs
    only with Encode level data on; a ROM with no second-quest set comes back unchanged."""
    folded = bytearray(rom)
    for set_index, levels in enumerate(SET_LEVELS):
        high_byte_addresses = [ROOM_BLOCK_ADDRESSES_Q1 + 2 * level + 1 for level in levels]
        high_bytes = {rom[address] for address in high_byte_addresses}
        if high_bytes == {FIRST_QUEST_HIGH_BYTES[set_index]}:
            continue
        if high_bytes != {SECOND_QUEST_HIGH_BYTES[set_index]}:
            raise ValueError(f"levels {levels.start}-{levels.stop - 1} point at room blocks "
                             f"{sorted(f'${byte:02X}' for byte in high_bytes)}, not one block of their own")
        source, target = SECOND_QUEST_BLOCKS[set_index], FIRST_QUEST_BLOCKS[set_index]
        folded[target:target + ROOM_BLOCK_SIZE] = rom[source:source + ROOM_BLOCK_SIZE]
        for address in high_byte_addresses:
            folded[address] = FIRST_QUEST_HIGH_BYTES[set_index]
    return bytes(folded)


def plain_level_data(rom: bytes) -> bytes:
    """The plain bytes of the three loaded blocks, from a ROM before encoding: those the
    encoding receives, so a second-quest set's block once folded (fold_second_quest_blocks)."""
    return bytes(fold_second_quest_blocks(rom)[LEVEL_DATA_START:LEVEL_DATA_START + PLAIN_BLOCKS_SIZE])


def decode_level_data(rom: bytes, key: LevelEncodingKey) -> bytes:
    """The plain bytes of the three blocks, decoded from an encoded ROM."""
    encoder = require_available()
    decoded: bytes = encoder.decode_level_data(rom, key.seed, key.settings_bytes)
    return decoded


def changed_ranges_allowed() -> list[tuple[int, int]]:
    """The file ranges (start, end) the encoding may change: the level data
    and its two edit sites in bank 6."""
    encoder = require_available()
    return [(start, end) for start, end in encoder.ALLOWED_RANGES]
