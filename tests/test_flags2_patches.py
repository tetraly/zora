"""The ZORA 2.0 flag patches of asm/flags2/ (docs/design/zora-flags-2.0.md), not wired:
asm/flags2/flags2_data.py matches a fresh build, every byte a patch replaces is PRG0's in
ZORA's output, the original game's bytes a patch keeps are read from the player's ROM, no
two patches (these, the series, the player settings, the overworld Wizzrobe routine) write
the same byte, and the data edits are where their notes say. The patches' effects in the
emulator: tests/test_flags2_emulator.py."""
import importlib.util
import shutil
from functools import cache
from itertools import combinations
from pathlib import Path
from types import ModuleType

import pytest

from tests.test_feature_patches import vanilla
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import Original, Piece, original_bytes, piece_length
from zora.rom.code_patch_data import PATCHES as SERIES_PATCHES
from zora.rom.layout import OVERWORLD_WIZZROBE_PATCH
from zora.rom.vanilla_overworld.screens import read_screens
from zora.rom.vanilla_overworld.tables import LAYOUT_COLUMNS, OW_LAYOUT_COUNT

REPO = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of some trees: what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _module("flags2_build", REPO / "asm" / "flags2" / "build.py")
data = build.load_data()
settings = _module("player_settings_data", REPO / "asm" / "settings" / "player_settings_data.py")

# RoomLayoutsOW (bank 5 $9418): headered file offset of layout 0's first column descriptor.
ROOM_LAYOUTS_OW_FILE = 0x15428


def written(pieces: tuple[tuple[int, Piece], ...]) -> set[int]:
    return {offset + i for offset, piece in pieces for i in range(piece_length(piece))}


def test_module_matches_a_fresh_build() -> None:
    if not (shutil.which("ca65") and shutil.which("ld65") and build.tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    vanilla()
    _, writes = build.build_all()
    assert build.render(writes) == build.OUTPUT.read_text()


def test_every_patch_is_built() -> None:
    assert tuple(data.PATCHES) == build.PATCHES
    assert all(data.PATCHES[name] for name in build.PATCHES)


def test_kept_bytes_are_read_from_prg0() -> None:
    """An Original piece is the original game's bytes, read from the player's ROM (never stored)."""
    rom = vanilla()
    for name, pieces in data.PATCHES.items():
        for _, piece in pieces:
            if isinstance(piece, Original):
                assert original_bytes(piece.source, piece.length) == rom[piece.source:piece.source + piece.length], name


@cache
def zora_output(seed: int, zora_flags: str) -> bytes:
    flags = MVP_BASELINE_LEVEL_ENCODING_OFF
    if zora_flags:
        # Progressive Items refuses Extra Candles (B09), as in tests/test_asm_patches.py.
        flags = encode(decode(flags).updated(toggles={"B09": ThreeState.OFF}))
    return generate_rom(flags, seed, vanilla(), zora_flag_string=zora_flags).rom


@pytest.mark.parametrize(("seed", "zora_flags"), [(1, ""), (2, "2.19")])
def test_every_replaced_byte_is_prg0_in_zora_output(seed: int, zora_flags: str) -> None:
    """Each patch replaces PRG0's bytes: ZORA's output (series patches, the serializer's writes;
    in the second case Progressive Items and Shop Items in the Item Pool on, Extra Candles off)
    holds PRG0's bytes wherever a patch writes."""
    rom, original = zora_output(seed, zora_flags), vanilla()
    for name, pieces in data.PATCHES.items():
        for offset in sorted(written(pieces)):
            assert rom[offset] == original[offset], f"{name} 0x{offset:05X}"


def test_no_two_patches_write_the_same_byte() -> None:
    """Between these patches, and between each of them and the series, every player setting's
    choices and the overworld red Wizzrobe routine."""
    others = {f"series {name}": written(pieces) for name, pieces in SERIES_PATCHES.items()}
    for setting, choices in settings.SETTINGS.items():
        others[f"setting {setting}"] = set().union(*(written(runs) for runs in choices.values()))
    others["overworld Wizzrobe routine"] = written(OVERWORLD_WIZZROBE_PATCH)
    for (name_a, a), (name_b, b) in combinations(data.PATCHES.items(), 2):
        assert not written(a) & written(b), (name_a, name_b)
    for name, pieces in data.PATCHES.items():
        for other, offsets in others.items():
            assert not written(pieces) & offsets, (name, other)


def test_data_edits_are_where_their_notes_say() -> None:
    """Every data edit lies in RoomLayoutsOW, and its note names each layout it changes and
    every screen that uses that layout."""
    screens_of: dict[int, list[int]] = {}
    for screen in read_screens(vanilla()):
        screens_of.setdefault(screen.layout, []).append(screen.room_id)
    for name in build.PATCHES:
        for edit in build.data_edits(name):
            for offset in range(edit.offset, edit.offset + len(edit.data)):
                layout = (offset - ROOM_LAYOUTS_OW_FILE) // LAYOUT_COLUMNS
                assert 0 <= layout < OW_LAYOUT_COUNT, name
                assert f"Layout {layout} (" in edit.note or f"layout {layout} (" in edit.note, (name, edit.note)
                for room_id in screens_of[layout]:
                    assert f"${room_id:02X}" in edit.note, (name, layout, edit.note)


def test_the_credits_are_recorded() -> None:
    """The document's two community credits, in the data module, the patches' notes and
    docs/credits.md."""
    assert data.CREDITS == {"fast-heart-fill": "snarfblam", "recorder-pols-voice": "Stratoform"}
    credits = (REPO / "docs" / "credits.md").read_text()
    for name, author in data.CREDITS.items():
        assert author in (REPO / "asm" / "flags2" / name / "patch.toml").read_text()
        assert author in credits
