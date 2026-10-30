"""The base ROM: the repo's PRG0 file for scripts and tests (verify_base_rom), and the
player's ROM that generation reads the original game's bytes from (PlayerRom).

Every script and test that reads the repo's vanilla base ROM verifies it through this
module; anything that does not hash to the PRG0 set is refused. See AGENTS.md for the
recorded hashes. The player's ROM may be either release (revision.identify_rom).
"""
import hashlib
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from .revision import (
    IdentifiedRom,
    Revision,
    back_to_revision,
    headered,
    identify_rom,
    in_prg0_layout,
    recognized,
)

REPO = Path(__file__).resolve().parent.parent.parent
BASE_ROM_NAME = "Legend of Zelda, The (USA).nes"
BASE_ROM_PATH = REPO / BASE_ROM_NAME
# PRG1 (Rev 1), beside it for the tests and the release scan (never committed, never shipped)
PRG1_ROM_NAME = "Legend of Zelda, The (USA) (Rev 1).nes"
PRG1_ROM_PATH = REPO / PRG1_ROM_NAME

EXPECTED_MD5 = "337bd6f1a1163df31bf2633665589ab0"
EXPECTED_SHA1 = "dab79c84934f9aa5db4e7dad390e5d0c12443fa2"
EXPECTED_CRC32 = 0xD7AE93DF


class BaseRomMismatch(ValueError):
    pass


def base_rom_hashes(path: Path) -> tuple[str, str, int]:
    data = path.read_bytes()
    return (hashlib.md5(data).hexdigest(),
            hashlib.sha1(data).hexdigest(),
            zlib.crc32(data) & 0xFFFFFFFF)


def verify_base_rom(path: Path | None = None) -> Path:
    """Return `path` (default: repo-root PRG0 ROM) iff its hashes match."""
    p = path or BASE_ROM_PATH
    if not p.is_file():
        raise BaseRomMismatch(f"base ROM missing: {p}")
    md5, sha1, crc = base_rom_hashes(p)
    if (md5, sha1, crc) != (EXPECTED_MD5, EXPECTED_SHA1, EXPECTED_CRC32):
        raise BaseRomMismatch(
            f"base ROM {p.name}: not the PRG0 release\n"
            f"  md5  {md5} (want {EXPECTED_MD5})\n"
            f"  sha1 {sha1} (want {EXPECTED_SHA1})\n"
            f"  crc32 {crc:08X} (want {EXPECTED_CRC32:08X})"
        )
    return p


def verify_prg1_rom(path: Path | None = None) -> Path:
    """Return `path` (default: the repo-root PRG1 ROM) iff it is the unmodified PRG1 release (its
    ROM data's hashes; revision.identify_rom)."""
    p = path or PRG1_ROM_PATH
    if not p.is_file():
        raise BaseRomMismatch(f"PRG1 ROM missing: {p}")
    if identify_rom(p.read_bytes()) != IdentifiedRom(Revision.PRG1, modified_graphics=False):
        raise BaseRomMismatch(f"{p.name}: not the PRG1 (Rev 1) release")
    return p


# The original game's bytes are never shipped: what ZORA keeps or moves of them is read from
# the player's own ROM when it is needed, PRG0 or PRG1, with or without modified graphics
# (revision.identify_rom). Each generation, parse and serialization is passed its ROM and reads
# it within its own call (using_player_rom), so that Archipelago players baking from different
# releases in one process each read their own. Without one, player_rom() refuses: generation
# never falls back to a file on disk, which Archipelago (zora/ copied in as worlds.zora.zora,
# perhaps from a zip) does not have.
#
# Scripts and tests that parse finished or corpus ROMs outside any generation call
# remember_repo_base_rom() first, and Archipelago's client remembers the player's ROM
# (client_ready): the process's fallback, never read while a call has its own.


@dataclass(frozen=True)
class PlayerRom:
    """The player's base ROM: the file (headered), which release it is, and the same in PRG0's
    layout, where ZORA reads and writes (revision.in_prg0_layout; the file itself on PRG0).

    With a graphics theme (graphics_theme.themed_player_rom) the generation parses and writes a
    working copy, `themed`, in PRG0's layout; `layout` stays the untouched ROM's, which the original
    game's bytes (original_bytes) and the finished ROM's return to its release are read from."""
    data: bytes
    identity: IdentifiedRom
    layout: bytes
    theme: str = ""                 # graphics_theme.GraphicsTheme's value, "" without one
    themed: bytes = b""

    @property
    def revision(self) -> Revision:
        return self.identity.revision

    @property
    def canvas(self) -> bytes:
        """The image generation parses and the finished ROM is written over (PRG0's layout)."""
        return self.themed or self.layout

    def with_canvas(self, theme: str, themed: bytes) -> "PlayerRom":
        return PlayerRom(self.data, self.identity, self.layout, theme, themed)

    def finished(self, image: bytes) -> bytes:
        """The ROM ZORA wrote in PRG0's layout (`image`), on the player's own release."""
        return back_to_revision(self.data, self.revision, self.layout, image)


@lru_cache(maxsize=16)
def player_rom_of(data: bytes) -> PlayerRom:
    """The player's ROM for `data`; RomNotRecognized unless revision.identify_rom knows it."""
    identity = identify_rom(data)
    rom = headered(data)
    return PlayerRom(rom, identity, in_prg0_layout(rom, identity.revision))


def as_player_rom(base: bytes | PlayerRom) -> PlayerRom:
    """A PlayerRom as given (a graphics theme's, graphics_theme.themed_player_rom), else player_rom_of."""
    return base if isinstance(base, PlayerRom) else player_rom_of(base)


def recognized_player_rom(data: bytes) -> PlayerRom | None:
    """player_rom_of, or None for a ROM that is no release (a finished or corpus ROM)."""
    return player_rom_of(data) if recognized(data) else None


_scoped: ContextVar[PlayerRom | None] = ContextVar("zora_player_rom", default=None)


class _Remembered:
    player: PlayerRom | None = None


_remembered = _Remembered()


class NoPlayerRom(RuntimeError):
    pass


@contextmanager
def using_player_rom(player: PlayerRom) -> Iterator[PlayerRom]:
    """Within the block, the original game's bytes are read from `player`."""
    token = _scoped.set(player)
    try:
        yield player
    finally:
        _scoped.reset(token)


def remember_base_rom(data: bytes) -> None:
    """The process's fallback player ROM, for reads outside a generation call (scripts, tests,
    Archipelago's client); a ROM that is no release (a finished ROM) is ignored."""
    player = recognized_player_rom(data)
    if player is not None:
        _remembered.player = player


def remember_repo_base_rom() -> bytes:
    """For scripts and tests only: remember the verified repo-root PRG0 ROM and return its bytes."""
    data = verify_base_rom().read_bytes()
    remember_base_rom(data)
    return data


def current_player_rom() -> PlayerRom:
    """The ROM of the call in progress, else the remembered one; NoPlayerRom if neither."""
    player = _scoped.get() or _remembered.player
    if player is None:
        raise NoPlayerRom("no base ROM: pass it to generate_rom (or parse_rom) first; "
                          "scripts and tests call base_rom.remember_repo_base_rom()")
    return player


def player_rom() -> bytes:
    """The player's ROM file (current_player_rom)."""
    return current_player_rom().data


def original_bytes(offset: int, length: int) -> bytes:
    """`length` bytes of the original game from PRG0's file offset `offset`, read from the
    player's ROM in PRG0's layout."""
    return current_player_rom().layout[offset:offset + length]


class Original(NamedTuple):
    """In a patch's data: `length` bytes of the original game from file offset `source`, which
    the patch keeps in place or moves (when `source` is not where they are written). They are
    read from the player's ROM when the patch is written, never stored in this package."""
    source: int
    length: int


Piece = bytes | Original


def piece_bytes(piece: Piece) -> bytes:
    """A patch piece's bytes: its own, or the original game's read from the player's ROM."""
    return original_bytes(piece.source, piece.length) if isinstance(piece, Original) else piece


def piece_length(piece: Piece) -> int:
    return piece.length if isinstance(piece, Original) else len(piece)
