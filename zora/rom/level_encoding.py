"""Encode level data (features-behavior.md FP-TOURNEY-01): the public interface.

With level encoding on, the finished ROM stores most dungeon and overworld
data in an encoded form that the game decodes as it loads a level, so ROM
editors and map viewers can't read it; gameplay is exactly the same. The
encoder lives in the owner's private repo, checked out (when present) at
`private/` in this folder and never committed here; this module imports it.
Without it, level encoding is not available: asking for it raises
`LevelEncodingUnavailable`, never a silent plain build.
"""
from __future__ import annotations

import importlib
from types import ModuleType

from zora.rom.game_config import LevelEncodingKey

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
    encoded: bytes = encoder.apply(rom, key.seed, key.settings_bytes)
    return encoded


def plain_level_data(rom: bytes) -> bytes:
    """The plain bytes of the three loaded blocks, from a ROM before encoding."""
    return bytes(rom[LEVEL_DATA_START:LEVEL_DATA_START + PLAIN_BLOCKS_SIZE])


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
