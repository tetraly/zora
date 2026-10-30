"""The code-patch bytes (zora/rom/code_patch_data.py): they match a fresh build
of asm/, each patch applies on top of the ones before it, and no other
serializer write touches them."""
import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from tests.test_feature_patches import vanilla
from zora.rom.base_rom import Original, original_bytes, piece_bytes, piece_length
from zora.rom.code_patch_data import PATCHES
from zora.rom.code_patches import (
    BLANK_HINTS, BOOK_TO_UNDERSTAND_NPCS, ENTR_01, ENTR_01_SIDES, EXIT_ROOM_COUNT_FLAG, LEVEL_INFO_EXIT_ROOM_COUNT, ONE_TIME_WARES, PROGRESSIVE_CAVES,
    PROGRESSIVE_ITEMS_BYTE,
    PROGRESSIVE_ROOM_ITEMS, SHOPS_BY_NUMBER, START_ITEMS, left_out_patches, one_time_wares,
)
from zora.flags import zora_flags
from zora.model.enums import Item
from zora.model.overworld import Shop
from zora.rom.game_config import GameConfig, HintMode
from zora.rom.parse.rom_file import original_bins_from_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.rom.serialize.game_world import serialize_game_world
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions

REPO = Path(__file__).resolve().parent.parent


def _asm_patches() -> ModuleType:
    """A fresh copy of scripts/asm_patches.py, so a test may repoint it."""
    path = REPO / "scripts" / "asm_patches.py"
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location("asm_patches_tool", path)
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def _skip_without_the_assembler_or_the_clone(tool: ModuleType) -> None:
    if not (shutil.which("ca65") and shutil.which("ld65") and tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")


def test_module_matches_a_fresh_build() -> None:
    tool = _asm_patches()
    _skip_without_the_assembler_or_the_clone(tool)
    vanilla()
    patches, symbols = tool.build_all()
    assert tool.render(patches, symbols) == tool.OUTPUT.read_text()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def test_the_pinned_commit_is_read_whatever_the_clone_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The builder reads DISASSEMBLY_COMMIT from git, never the clone's working tree: in a
    throwaway clone checked out on another commit, with an edit committed there and another
    left uncommitted, the pristine sources are the pinned commit's and still rebuild PRG0."""
    tool = _asm_patches()
    _skip_without_the_assembler_or_the_clone(tool)
    rom = vanilla()
    scratch = tool.scratch("asm-pin-test")         # a folder of this test's own, removed at exit
    clone, work = scratch / "clone", scratch / "work"
    try:
        subprocess.run(["git", "clone", "--quiet", str(tool.DISASSEMBLY_REPO), str(clone)], check=True)
        _git(clone, "checkout", "--quiet", "-b", "elsewhere", tool.DISASSEMBLY_COMMIT)
        z01, z05 = clone / "src" / "Z_01.asm", clone / "src" / "Z_05.asm"
        z01.write_text(z01.read_text() + "\n    .BYTE $EA ; committed elsewhere\n")
        _git(clone, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
             "commit", "--quiet", "-am", "not the pinned commit")
        z05.write_text(z05.read_text() + "\n    .BYTE $EA ; uncommitted\n")
        assert _git(clone, "rev-parse", "HEAD").strip() != tool.DISASSEMBLY_COMMIT
        assert _git(clone, "status", "--porcelain").strip()

        monkeypatch.setattr(tool, "DISASSEMBLY_REPO", clone)
        tool.pristine_sources(work / "src")
        for name in ("Z_01.asm", "Z_05.asm"):
            pinned = _git(clone, "show", f"{tool.DISASSEMBLY_COMMIT}:src/{name}").replace("\r\n", "\n")
            assert (work / "src" / name).read_text() == pinned
        tool.extract_bins(rom, work / "bin")
        image, _ = tool.assemble(work / "src", work / "bin", work / "obj")
        assert image == rom
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_a_missing_clone_or_commit_is_named() -> None:
    tool = _asm_patches()
    scratch = tool.scratch("asm-missing-test")
    missing = scratch / "no-such-disassembly"
    with pytest.raises(tool.DisassemblyError, match="no-such-disassembly.*missing.*git clone"):
        tool.export_disassembly(missing, tool.DISASSEMBLY_COMMIT, scratch / "unused-export")
    if not tool.DISASSEMBLY_REPO.is_dir():
        pytest.skip("the disassembly clone is missing")
    with pytest.raises(tool.DisassemblyError, match="has no commit 0{40}"):
        tool.export_disassembly(tool.DISASSEMBLY_REPO, "0" * 40, scratch / "unused-export")


def _patch_bytes(name: str) -> set[int]:
    return {offset + i for offset, piece in PATCHES[name] for i in range(piece_length(piece))}


# A patch written over another's bytes, and only those: fp-entr-01-sides (B26) re-points
# fp-entr-01's jump; left out, the ROM keeps fp-entr-01's bytes.
OVERLAYS = {ENTR_01_SIDES: ENTR_01}


def test_each_patch_applies_on_the_ones_before() -> None:
    """No two patches write the same byte (but an overlay, over its own patch's bytes), so each
    one replaces PRG0's bytes only (whatever the patches before it did), which the base ROM's
    hash check already guarantees; and every original piece is read from PRG0 (a patch keeps or
    moves the original game's bytes)."""
    claimed: set[int] = set()
    for name in PATCHES:
        overlaid = _patch_bytes(OVERLAYS[name]) if name in OVERLAYS else set()
        assert not (_patch_bytes(name) - overlaid) & claimed, name
        claimed |= _patch_bytes(name)
    rom = vanilla()
    for name, pieces in PATCHES.items():
        for _, piece in pieces:
            if isinstance(piece, Original):
                assert piece_bytes(piece) == rom[piece.source:piece.source + piece.length], name


def _written(config: GameConfig, seed: int) -> set[int]:
    rom = vanilla()
    world = parse_rom(rom)
    generate_shapes(world, Rng(seed), ShapeOptions())
    patch = serialize_game_world(world, original_bins_from_rom(rom),
                                 hint_mode=config.hint_mode, config=config)
    return {offset + i for offset, data in patch.data.items() for i in range(len(data))}


def test_no_other_write_touches_the_patches() -> None:
    patched_bytes = {offset for name in PATCHES for offset in _patch_bytes(name)}
    for seed in (1, 2):
        others = _written(GameConfig(hint_mode=HintMode.CONSTERNATION), seed)
        assert not others & patched_bytes


def test_level_information_carries_the_exit_room_counts() -> None:
    """FP-ENTR-02's data: each dungeon's level information +$23 holds its
    exit-room count with bit 7 set, read back from the finished ROM."""
    rom = vanilla()
    world = parse_rom(rom)
    generate_shapes(world, Rng(3), ShapeOptions())
    expected = {level.level_num: level.exit_room_count() | EXIT_ROOM_COUNT_FLAG
                for level in world.levels}
    # CONSTERNATION: generate_shapes draws the pool's texts, which are for the extended bank; the
    # vanilla bank (Normal hints, whose texts are PRG0's own) holds 1,366 bytes and the community
    # texts of 2026-10-24 overflow it in this seed.
    config = GameConfig(features_b10=True, hint_mode=HintMode.CONSTERNATION)
    finished = parse_rom(serialize_to_rom(world, rom, config=config))
    assert {level.level_num: level.palette_raw[LEVEL_INFO_EXIT_ROOM_COUNT]
            for level in finished.levels} == expected


# --- the progressive patches follow their ZORA flags (PI-CODE-01, PI-CODE-04) ----------------

def _progressive_build() -> ModuleType:
    path = REPO / "asm" / "progressive" / "build.py"
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location("progressive_build", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _holds(rom: bytes, name: str, *, patched: bool) -> bool:
    """Every byte of the patch holds its patched value (or PRG0's, read from the player's ROM);
    the per-seed bytes aside."""
    seed_bytes = {PROGRESSIVE_ITEMS_BYTE, *range(ONE_TIME_WARES, ONE_TIME_WARES + 3)}
    return all(rom[offset + i] == (piece_bytes(piece) if patched else original_bytes(offset, piece_length(piece)))[i]
               for offset, piece in PATCHES[name] for i in range(piece_length(piece))
               if offset + i not in seed_bytes)


@pytest.mark.parametrize(("zora", "caves", "rooms", "on_byte"), [
    ("", False, False, None),        # both off: neither patch (and output unchanged)
    ("2.m", True, False, 0),         # Shop Items in the Item Pool: fp-prog-01, only the buy-once rule
    ("2.O", True, True, 1),          # Progressive Items: both
    ("2.19", True, True, 1),         # both flags
])
def test_the_progressive_patches_follow_their_flags(zora: str, caves: bool, rooms: bool, on_byte: int | None) -> None:
    from zora.flags.codec import decode, encode
    from zora.flags.fields import ThreeState
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom.base_rom import verify_base_rom
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))
    rom = generate_rom(flags, 1, verify_base_rom().read_bytes(), zora_flag_string=zora).rom
    assert _holds(rom, PROGRESSIVE_CAVES, patched=caves)
    assert _holds(rom, PROGRESSIVE_ROOM_ITEMS, patched=rooms)
    if on_byte is None:
        assert rom[PROGRESSIVE_ITEMS_BYTE:ONE_TIME_WARES + 3] == b"\xff" * 4
    else:
        assert rom[PROGRESSIVE_ITEMS_BYTE] == on_byte
        # PI-CODE-04: the one-time wares from the model's final shop stock are the ones the
        # finished ROM's shop tables give (asm/progressive/build.py reads them from the ROM), and
        # with Shop Items in the Item Pool the bait and blue potion shops 1-4 sell are pool items,
        # sold once (code_patches.one_time_wares' bait_in_pool rule, which that builder does not
        # know; seed 1 has a bait in shop 1 since the spare bait's fairy draws its price).
        bait_in_pool = zora_flags.decode(zora).shop_items_in_pool
        world = parse_rom(rom)
        expected = bytearray(_progressive_build().one_time_wares(rom))
        if bait_in_pool:
            for shop_number, destination in enumerate(SHOPS_BY_NUMBER[1:], start=1):
                shop = world.overworld.get_cave(destination, Shop)
                assert shop is not None
                for position, ware in enumerate(shop.items):
                    if ware.item in (Item.BAIT, Item.BLUE_POTION):
                        expected[position] |= 1 << shop_number
        assert rom[ONE_TIME_WARES:ONE_TIME_WARES + 3] == bytes(expected)
        assert rom[ONE_TIME_WARES:ONE_TIME_WARES + 3] == one_time_wares(world, bait_in_pool=bait_in_pool)


def test_left_out_patches() -> None:
    assert left_out_patches(True, False, False) == (PROGRESSIVE_CAVES, PROGRESSIVE_ROOM_ITEMS, START_ITEMS,
                                                    ENTR_01_SIDES, BOOK_TO_UNDERSTAND_NPCS, BLANK_HINTS)
    assert left_out_patches(False, False, True) == ("fp-book-01", PROGRESSIVE_ROOM_ITEMS, START_ITEMS, ENTR_01_SIDES,
                                                    BOOK_TO_UNDERSTAND_NPCS, BLANK_HINTS)
    assert left_out_patches(True, True, False) == (START_ITEMS, ENTR_01_SIDES, BOOK_TO_UNDERSTAND_NPCS, BLANK_HINTS)
    assert left_out_patches(True, True, False, start_items=True, start_rooms_moved=True,
                            book_to_understand_npcs=True, blank_hints=True) == ()
