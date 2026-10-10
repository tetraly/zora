"""PRG0 base-ROM verification (single source of truth).

Every script and test that reads the vanilla base ROM MUST verify it through
this module; anything that does not hash to the PRG0 set is refused.
See AGENTS.md for the recorded hashes.
"""
import hashlib
import zlib
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent.parent
BASE_ROM_NAME = "Legend of Zelda, The (USA).nes"
BASE_ROM_PATH = REPO / BASE_ROM_NAME

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


def is_prg0(data: bytes) -> bool:
    """True iff `data` hashes as the PRG0 release."""
    return (hashlib.md5(data).hexdigest(), hashlib.sha1(data).hexdigest(),
            zlib.crc32(data) & 0xFFFFFFFF) == (EXPECTED_MD5, EXPECTED_SHA1, EXPECTED_CRC32)


# The original game's bytes are never shipped: what ZORA keeps or moves of them is read from
# the player's own PRG0 ROM when it is needed. generate_rom/generate_world, parse_rom and
# serialize_to_rom remember the ROM they are given (once verified) before reading anything.
# Without one, player_rom() refuses: generation never falls back to a file on disk, which
# Archipelago (zora/ copied in as worlds.zora.zora, perhaps from a zip) does not have.
#
# The remembered ROM is process-global, not per call: Archipelago generates several players'
# worlds in one process, one after another, and every player's base is the same PRG0 ROM
# (refused otherwise), so whichever call remembered it last leaves the same bytes. Scripts and
# tests that parse finished or corpus ROMs before any generation call
# remember_repo_base_rom() first (it is never called on the generation path).
class _PlayerRom:
    data: bytes | None = None


_player = _PlayerRom()


class NoPlayerRom(RuntimeError):
    pass


def remember_base_rom(data: bytes) -> None:
    """Keep `data` as the source of original bytes, if it is PRG0 (a corpus or finished ROM
    passed as a base is ignored)."""
    if data is not _player.data and is_prg0(data):
        _player.data = bytes(data)


def remember_repo_base_rom() -> bytes:
    """For scripts and tests only: remember the verified repo-root PRG0 ROM and return its bytes."""
    data = verify_base_rom().read_bytes()
    remember_base_rom(data)
    return data


def player_rom() -> bytes:
    """The player's verified PRG0 ROM, the one last remembered; NoPlayerRom if none was."""
    if _player.data is None:
        raise NoPlayerRom("no PRG0 base ROM remembered: pass it to generate_rom (or parse_rom) first; "
                          "scripts and tests call base_rom.remember_repo_base_rom()")
    return _player.data


def original_bytes(offset: int, length: int) -> bytes:
    """`length` bytes of the original game from file offset `offset`, read from the player's ROM."""
    return player_rom()[offset:offset + length]


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
