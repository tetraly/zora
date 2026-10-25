"""The ROM space table (asm/rom_space.toml, asm/rom_space.py; docs/rom-map.md): PRG0's free space, the
reservations, each segment's slot, the bytes ZORA's Python writes in free space and the bytes two
owners share. One overlap check covers the five builders' bytes, the slots, the sites and the
reservations; finished ROMs write free space only where the table says."""
import importlib
import importlib.util
import os
import shutil
import sys
import tomllib
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.needs import needs_base_rom
from tests.test_coop_reserved import FINISHED_CASES, OTHER_PLAYER_SETTINGS, PRODUCED_VALUES, finished, z1r_with
from tests.test_feature_patches import vanilla
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.rom.player_settings import apply_player_settings

REPO = Path(__file__).resolve().parent.parent
ASM = REPO / "asm"


def load(name: str, path: Path) -> ModuleType:
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree")
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def rom_space() -> Any:
    return load("rom_space", ASM / "rom_space.py")


# --- the table -------------------------------------------------------------------------------------

def test_the_overlap_check_passes() -> None:
    """Every byte two owners claim is a [[shared]] row's, every builder byte in free space is in its
    owner's slot, and every slot lies in free space."""
    assert rom_space().problems() == []


def test_the_overlap_check_finds_a_clash() -> None:
    """A patch writing into z1rr-coop's bank-4 block, or into free space outside its slots, is named."""
    space = rom_space()
    written = dict(space.builder_bytes())
    written["series:new-patch"] = {space.file_offset(4, 0xB500), space.file_offset(3, 0xB000)}
    found = space.problems(written=written)
    assert any("series:new-patch, z1rr-coop with no [[shared]] row" in problem for problem in found)
    assert any("bank 3 $B000" in problem and "outside its slots" in problem for problem in found)


@needs_base_rom
def test_free_space_is_free_in_prg0() -> None:
    original = vanilla()
    for area in rom_space().table().free:
        assert set(original[area.file_range().start:area.file_range().stop]) == {0xFF}, str(area)


def test_every_segment_has_its_slot() -> None:
    """Each segment of every patch folder starts at its slot's first byte (a segment the build placed
    is in asm/placements.toml instead)."""
    space = rom_space().table()
    for path in sorted(ASM.rglob("patch.toml")):
        for segment in tomllib.loads(path.read_text()).get("segment", []):
            if "start" in segment:
                assert space.slot(segment["name"], segment["bank"], segment["start"]), (path, segment["name"])


def test_the_builders_free_space_is_the_table_slots() -> None:
    """asm/flags2, asm/asnb and asm/progressive check their segments against FREE_SPACE: the same
    ranges as the table's slots."""
    space = rom_space().table()
    for name in ("flags2", "asnb", "progressive"):
        builder = load(f"rom_space_{name}_build", ASM / name / "build.py")
        ranges = {**builder.FREE_SPACE, **getattr(builder, "GROWTH", {})}
        for segment, area in ranges.items():
            slot = space.slot(segment, area.bank, area.first)
            assert slot and slot.last == area.last, (name, segment)


def test_sites_are_their_modules_constants() -> None:
    for site in rom_space().table().sites:
        if site.source:
            module, constant = site.source.split(":")
            assert getattr(importlib.import_module(module), constant) == site.file_range().start, site


def _cpu_range(area: Any) -> str:
    return f"${area.first:04X}-${area.last:04X}" if area.last != area.first else f"${area.first:04X}"


def test_the_rom_map_agrees_with_the_table() -> None:
    """docs/rom-map.md is checked against the table: each free range is a row of its "Free space in
    PRG0" table, and each slot, placement and site range is written on the page."""
    rom_map = REPO / "docs" / "rom-map.md"
    if not rom_map.exists():
        pytest.skip("docs/rom-map.md is not in this tree")
    text = rom_map.read_text()
    free_section = text.partition("## Free space in PRG0")[2].partition("\n## ")[0]
    space = rom_space()
    for area in space.table().free:
        assert f"| {_cpu_range(area)} |" in free_section, str(area)
    placed = (area for row in space.placements() for area in row.areas())
    for area in (*space.table().slots, *space.table().sites, *placed):
        assert _cpu_range(area) in text, str(area)


# --- shared bytes and the flag rules ----------------------------------------------------------------

def _flag_strings(flags: dict[str, dict[str, Any]]) -> tuple[str, str]:
    toggles = {field: ThreeState.ON for field, value in flags.get("z1r", {}).items() if value == "on"}
    options = {field: value for field, value in flags.get("z1r", {}).items() if value != "on"}
    zora: dict[str, Any] = {field: ThreeState.ON if value == "on" else value
                            for field, value in flags.get("zora", {}).items()}
    flag_string = z1r_with(toggles=toggles, options=options)
    return flag_string, zora_flags.encode(zora_flags.ZoraFlags(**zora)) if zora else ""


@needs_base_rom
@pytest.mark.parametrize("index", [index for index, shared in enumerate(rom_space().table().shared) if shared.flags]
                         if (ASM / "rom_space.py").exists() else [])
def test_chained_writers_go_together(index: int) -> None:
    """A chained row's flags (all its writers on at once) are accepted and every shared byte is
    written: the writers build on each other rather than one of them being refused."""
    shared = rom_space().table().shared[index]
    assert shared.together == "chained"
    flag_string, zora_flag_string = _flag_strings(shared.flags)
    rom = finished(flag_string, 1, zora_flag_string)
    original = vanilla()
    for area in shared.areas:
        span = slice(area.file_range().start, area.file_range().stop)
        assert rom[span] != original[span], (str(area), sorted(shared.owners))


def test_exclusive_rows_name_a_refusing_rule() -> None:
    """An "exclusive" row names the zora_flags check that refuses its writers together."""
    for shared in rom_space().table().shared:
        if shared.together == "exclusive":
            check = shared.flags.get("refused_by")
            assert check and callable(getattr(zora_flags, check, None)), sorted(shared.owners)


# --- finished ROMs -----------------------------------------------------------------------------

@cache
def claimed_free_bytes() -> frozenset[int]:
    space = rom_space()
    free = {offset for area in space.table().free for offset in area.file_range()}
    return frozenset(free & set(space.claims(space.table(), space.builder_bytes())))


def unclaimed_writes(rom: bytes) -> list[str]:
    space = rom_space()
    original = vanilla()
    free = {offset for area in space.table().free for offset in area.file_range()}
    loose = [offset for offset in free - claimed_free_bytes() if rom[offset] != original[offset]]
    return [f"bank {bank} ${address:04X}" for bank, address in map(space.cpu_address, sorted(loose))][:5]


FAST_CASES = {**FINISHED_CASES, **{case: PRODUCED_VALUES[case] for case in ("C19=1", "C19=2", "C07=3", "C08=1")
                                   if case in PRODUCED_VALUES}}


@needs_base_rom
@pytest.mark.parametrize("case", list(FAST_CASES))
def test_finished_roms_write_free_space_only_where_claimed(case: str) -> None:
    flag_string, zora_flag_string = FAST_CASES[case]
    rom = finished(flag_string, 1, zora_flag_string)
    assert unclaimed_writes(rom) == [], case
    for settings in OTHER_PLAYER_SETTINGS:
        assert unclaimed_writes(apply_player_settings(rom, settings)) == [], (case, str(settings))


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("case", list(PRODUCED_VALUES))
def test_each_produced_value_writes_free_space_only_where_claimed(case: str) -> None:
    flag_string, zora_flag_string = PRODUCED_VALUES[case]
    assert unclaimed_writes(finished(flag_string, 1, zora_flag_string)) == [], case


# --- placing new segments (asm/placements.toml) -------------------------------------------------------

@pytest.fixture
def lock_file() -> Any:
    """An empty placements file of the test's own under temp/ (never the committed one)."""
    folder = REPO / "temp" / f"rom-space-test-{os.getpid()}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "placements.toml"
    path.unlink(missing_ok=True)
    yield path
    shutil.rmtree(folder, ignore_errors=True)


def test_the_committed_placements_are_each_free_and_recorded() -> None:
    """Every row of asm/placements.toml lies in free space no other claim touches (the overlap check
    counts them as slots) and names a segment some patch.toml leaves without a start."""
    space = rom_space()
    unpinned = {segment["name"] for path in ASM.rglob("patch.toml")
                for segment in tomllib.loads(path.read_text()).get("segment", []) if "start" not in segment}
    assert {row.segment for row in space.placements()} == unpinned


def test_a_new_segment_takes_the_lowest_free_unclaimed_aligned_bytes(lock_file: Path) -> None:
    space = rom_space()
    placement = space.place(space.Request("ZORA_TEST_A", "series:test-a", (5,), 0x20), lock_file)
    assert placement.banks == (5,) and placement.start % space.DEFAULT_ALIGN == 0
    claimed = space.claims(space.table(), space.builder_bytes())
    window = range(space.file_offset(5, placement.start), space.file_offset(5, placement.start) + 0x20)
    assert not set(window) & set(claimed)
    # nothing lower in bank 5's free space would have fitted
    free = {offset for area in space.table().free for offset in area.file_range()}
    for start in range(0xB8A0, placement.start, space.DEFAULT_ALIGN):
        assert not space._fits(claimed, free, 5, start, 0x20), hex(start)


def test_adding_a_patch_never_moves_a_placed_one(lock_file: Path) -> None:
    space = rom_space()
    first = space.place(space.Request("ZORA_TEST_A", "series:test-a", (5,), 0x20), lock_file)
    second = space.place(space.Request("ZORA_TEST_B", "series:test-b", (5,), 0x20), lock_file)
    assert space.place(space.Request("ZORA_TEST_A", "series:test-a", (5,), 0x20), lock_file) == first
    assert set(first.areas()[0].file_range()).isdisjoint(second.areas()[0].file_range())
    assert [row.segment for row in space.placements(lock_file)] == ["ZORA_TEST_A", "ZORA_TEST_B"]


def test_a_changed_segment_must_be_moved_on_purpose(lock_file: Path) -> None:
    space = rom_space()
    space.place(space.Request("ZORA_TEST_A", "series:test-a", (5,), 0x20), lock_file)
    with pytest.raises(space.PlacementError, match="delete the row"):
        space.place(space.Request("ZORA_TEST_A", "series:test-a", (5,), 0x40), lock_file)


def test_a_pooled_segment_takes_the_first_bank_with_room(lock_file: Path) -> None:
    """Bank 7 has no 64 free bytes left: a segment that may go in bank 7 or bank 3 goes in bank 3."""
    space = rom_space()
    placement = space.place(space.Request("ZORA_TEST_POOL", "series:test-pool", (7, 3), 0x40), lock_file)
    assert placement.banks == (3,)


# Today no address is free in all of banks 0-6: bank 1's free space is full from $B770 (the extended
# hint text, then fp-prog-01), bank 2's gaps between its slots meet claims in bank 0 or z1rr-coop's
# bank-4 block, and $BFC0-$BFF9, free in every bank, is ASNB's. The mechanism is tested on four banks.
MIRRORED_BANKS = (0, 3, 5, 6)


def test_a_mirrored_segment_takes_one_address_free_in_every_bank(lock_file: Path) -> None:
    """A common window, as the wider item codes need: about 40 bytes at the same address in each bank."""
    space = rom_space()
    banks = MIRRORED_BANKS
    placement = space.place(space.Request("ZORA_TEST_WINDOW", "series:test-window", banks, 0x28, mirrored=True),
                            lock_file)
    assert placement.banks == banks
    claimed = space.claims(space.table(), space.builder_bytes())
    for area in placement.areas():
        assert not set(area.file_range()) & set(claimed), str(area)
    assert space.problems(placed=placement.areas(), written={**space.builder_bytes(),
                                                             "series:test-window": set()}) == []


def test_a_placed_segment_is_built_where_it_was_placed(lock_file: Path) -> None:
    """A patch with a placed segment and a mirrored one, built with ca65/ld65 on PRG0: its bytes land
    at the recorded addresses, in each bank for the mirrored one."""
    tool = load("asm_patches_rom_space", REPO / "scripts" / "asm_patches.py")
    if not (shutil.which("ca65") and shutil.which("ld65") and tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    folder = lock_file.parent / "test-placed"
    folder.mkdir()
    (folder / "patch.toml").write_text('[[segment]]\nname = "ZORA_TEST_PLACED"\nbank = 5\nsize = 0x10\n\n'
                                       '[[segment]]\nname = "ZORA_TEST_MIRROR"\nmirrored = [0, 3, 5, 6]\n'
                                       'size = 0x10\n')
    (folder / "bank_05.s").write_text('.SEGMENT "ZORA_TEST_PLACED"\nTestPlaced:\n    LDA #$5A\n    RTS\n')
    (folder / "mirrored.s").write_text('.SEGMENT "ZORA_TEST_MIRROR_B{BANK}"\nTestMirror:\n    LDA #${BANK}\n    RTS\n')
    vanilla()
    patch = tool.load_patch(folder, lock_file)
    image = tool.SourceTree(tool.scratch("rom-space-test")).apply(patch)
    placed, mirror = (next(row for row in rom_space().placements(lock_file) if row.segment == name)
                      for name in ("ZORA_TEST_PLACED", "ZORA_TEST_MIRROR"))
    offset = rom_space().file_offset(5, placed.start)
    assert image[offset:offset + 3] == bytes([0xA9, 0x5A, 0x60])
    for bank in MIRRORED_BANKS:
        offset = rom_space().file_offset(bank, mirror.start)
        assert image[offset:offset + 3] == bytes([0xA9, bank, 0x60]), bank
