"""The ROM ranges z1rr-coop's EverDrive N8 Pro patch uses (docs/rom-map.md "Reserved for
z1rr-coop") stay untouched: no ZORA patch, player setting, ZORA flag patch or fixed-site write
touches them, and ZORA's output holds PRG0's bytes there for every flag and setting value we can
enumerate. The patch is applied on top of a ZORA ROM, so a write there would break co-op on real
hardware.

The default run checks the patch data, the builders' free-space slots and a few finished ROMs;
`pytest -m slow` also sweeps each produced flag value (FL-OFF-07's turn-off values, the
alternative values and every ZORA flag) one at a time."""
import importlib.util
import re
import shutil
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.test_feature_patches import vanilla
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import ALTERNATIVE_OPTIONS, OWNER_TURN_OFF_TOGGLES, TURN_OFF_OPTIONS, TURN_OFF_TOGGLES
from zora.generate.pipeline import generate_rom
from zora.rom import level_encoding
from zora.rom.base_rom import Piece, piece_length
from zora.rom.code_patch_data import PATCHES as SERIES_PATCHES
from zora.rom.flags2_patch_data import PATCHES as FLAG_PATCHES
from zora.rom.layout import (
    NES_HEADER_SIZE,
    OVERWORLD_WIZZROBE_PATCH,
    TITLE_ROW_LENGTH,
    TITLE_SEED_ROW_ADDRESS,
    TITLE_VERSION_ROW_ADDRESS,
)
from zora.rom.player_settings import (
    DeathWarp,
    LowHealthBeep,
    Music,
    PlayerSettings,
    SelectSwap,
    apply_player_settings,
    written_offsets,
)

REPO = Path(__file__).resolve().parent.parent

FIXED_BANK = 7
BANK_SIZE = 0x4000
SWITCHED_BANK_BASE = 0x8000
FIXED_BANK_BASE = 0xC000


@dataclass(frozen=True)
class Reserved:
    """One of z1rr-coop's ranges: CPU addresses `first`-`last` in `bank`."""
    bank: int
    first: int
    last: int
    what: str

    def file_range(self) -> range:
        base = FIXED_BANK_BASE if self.bank == FIXED_BANK else SWITCHED_BANK_BASE
        start = NES_HEADER_SIZE + self.bank * BANK_SIZE + self.first - base
        return range(start, start + self.last - self.first + 1)

    def __str__(self) -> str:
        return f"bank {self.bank} ${self.first:04X}-${self.last:04X} ({self.what})"


# z1rr-coop 2.0 beta 8's blocks (the owner's figures from its patch). Each is reserved whole:
# unchanged bytes inside a block are part of the co-op code.
RESERVED = (
    Reserved(1, 0xA233, 0xA235, "in-place hook"),
    Reserved(1, 0xA430, 0xA449, "PRG0's unused $FF block"),
    Reserved(4, 0xB46F, 0xB882, "bank 4's linker gap, 1,044 bytes"),
    Reserved(5, 0xB366, 0xB369, "in-place hook in InitLinkSpeed"),
    Reserved(5, 0xB8F0, 0xB901, "bank 5's linker gap"),
    Reserved(6, 0xAAE8, 0xAAEF, "title-screen data the co-op patch overwrites"),
    Reserved(6, 0xB100, 0xB14C, "bank 6's linker gap"),
    Reserved(7, 0xE65A, 0xE65D, "in-place hook in ReadOneController"),
    Reserved(7, 0xED8A, 0xED93, "in-place hook in UpdateHeartsAndRupees"),
    Reserved(7, 0xFAE4, 0xFAEE, "PRG0's unused $FF run"),
    Reserved(7, 0xFFD4, 0xFFDB, "NMI entry"),
    Reserved(7, 0xFFFA, 0xFFFB, "NMI vector"),
)
# The co-op hooks replace whole instructions: these spans are the PRG0 instructions they touch.
# The hook at $ED8A starts on the operand of the instruction at $ED89, so ZORA must leave $ED89
# too; the others start and end on instruction boundaries.
HOOK_INSTRUCTIONS = (
    Reserved(1, 0xA233, 0xA235, "co-op hook's instruction"),
    Reserved(5, 0xB366, 0xB369, "co-op hook's instructions"),
    Reserved(7, 0xE65A, 0xE65D, "co-op hook's instructions"),
    Reserved(7, 0xED89, 0xED93, "co-op hook's instructions, from the LDA whose operand it starts on"),
)
RESERVED_BYTES = {offset: area for area in RESERVED + HOOK_INSTRUCTIONS for offset in area.file_range()}

# With "Encode level data" on, the private encoder rewrites the level data region and two bank-6
# sites (docs/rom-map.md "Other fixed-address writes"); its module is not in every tree.
LEVEL_ENCODING_SITES = (
    range(level_encoding.LEVEL_DATA_START, level_encoding.LEVEL_DATA_END),
    range(0x1803A, 0x1803A + 20),      # LevelBlockAddrsQ2
    range(0x1807C, 0x1807C + 3),       # the JSR in InitMode2_Sub0
)


def written(pieces: tuple[tuple[int, Piece], ...] | list[tuple[int, Piece]]) -> set[int]:
    return {offset + i for offset, piece in pieces for i in range(piece_length(piece))}


def hits(offsets: set[int] | range) -> list[str]:
    """The reserved ranges `offsets` touch, with the first offset found in each."""
    found: dict[Reserved, int] = {}
    for offset in sorted(offsets):
        if offset in RESERVED_BYTES:
            found.setdefault(RESERVED_BYTES[offset], offset)
    return [f"0x{offset:05X} in {area}" for area, offset in found.items()]


def _module(name: str, path: Path) -> ModuleType | None:
    if not path.exists():
        return None                  # asm/ is left out of some trees
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_ranges_are_recorded_in_the_rom_map() -> None:
    rom_map = REPO / "docs" / "rom-map.md"
    if not rom_map.exists():
        pytest.skip("docs/rom-map.md is not in this tree")
    section = rom_map.read_text().partition("## Reserved for z1rr-coop")[2].partition("\n## ")[0]
    rows = {(int(bank), int(first, 16), int(last, 16)) for bank, first, last in
            re.findall(r"^\| (\d) \| \$([0-9A-F]{4})-\$([0-9A-F]{4}) \|", section, re.MULTILINE)}
    assert rows == {(area.bank, area.first, area.last) for area in RESERVED}


def test_the_hook_spans_are_whole_instructions() -> None:
    """Each HOOK_INSTRUCTIONS span starts and ends on PRG0 instruction boundaries (the pinned
    disassembly's lines) and covers its co-op hook."""
    tool = _module("coop_asm_patches", REPO / "scripts" / "asm_patches.py")
    if tool is None or not (shutil.which("ca65") and shutil.which("ld65") and tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    lines = tool.SourceTree(tool.scratch("coop-hooks")).lines()
    starts = set(lines)
    ends = {offset + line.size for offset, line in lines.items()}
    for span in HOOK_INSTRUCTIONS:
        hook = next(area for area in RESERVED if area.bank == span.bank and span.first <= area.first <= span.last)
        assert set(hook.file_range()) <= set(span.file_range()), span
        assert span.file_range().start in starts and span.file_range().stop in ends, span


@pytest.mark.parametrize("name", list(SERIES_PATCHES))
def test_no_series_patch_writes_a_reserved_byte(name: str) -> None:
    """The code patches (asm/series.txt, progressive items included), per-seed bytes and all."""
    assert not hits(written(SERIES_PATCHES[name])), name


@pytest.mark.parametrize("name", list(FLAG_PATCHES))
def test_no_zora_flag_patch_writes_a_reserved_byte(name: str) -> None:
    assert not hits(written(FLAG_PATCHES[name])), name


@pytest.mark.parametrize("setting", ["select_swap", "low_health_beep", "death_warp", "reduce_flashing",
                                     "tunic_colours", "heart_colour", "music", "level_word",
                                     "boss_sound_word"])
def test_no_player_setting_writes_a_reserved_byte(setting: str) -> None:
    """Every byte any choice of the setting may write."""
    assert not hits(written_offsets(setting)), setting


def test_no_fixed_site_writes_a_reserved_byte() -> None:
    """The overworld red Wizzrobe routine, the title screen's two rows (FP-TITLE-01: fixed
    24-byte rows either side of the co-op's title bytes) and the level encoding's region and
    sites."""
    assert not hits(written(OVERWORLD_WIZZROBE_PATCH))
    for row in (TITLE_SEED_ROW_ADDRESS, TITLE_VERSION_ROW_ADDRESS):
        assert not hits(range(row, row + TITLE_ROW_LENGTH)), hex(row)
    for site in LEVEL_ENCODING_SITES:
        assert not hits(site), site


def test_no_builder_slot_overlaps_a_reserved_byte() -> None:
    """The free-space slots the patch builders may fill (asm/progressive, asm/flags2), so a patch
    that grows inside its slot stays clear too."""
    for path in (REPO / "asm" / "progressive" / "build.py", REPO / "asm" / "flags2" / "build.py"):
        builder = _module(f"coop_{path.parent.name}_build", path)
        if builder is None:
            pytest.skip("asm/ is not in this tree")
        for segment, space in builder.FREE_SPACE.items():
            assert not hits(space.file_range()), segment


# --- finished ROMs -------------------------------------------------------------------------

OWNER_FLAGS_ON: dict[str, Any] = dict.fromkeys(zora_flags.OWNER_2_0_FIELDS, ThreeState.ON)
EVERY_OWNER_FLAG_ON = zora_flags.encode(replace(
    zora_flags.DEFAULT, progressive_items=True, shop_items_in_pool=True, **OWNER_FLAGS_ON))
# Progressive Items refuses Extra Candles (B09), and Extra Power Bracelet Blocks refuses
# Shuffle "Take Any Road" Caves (B04).
BASELINE_FOR_OWNER_FLAGS = {"B09": ThreeState.OFF, "B04": ThreeState.OFF}
# A choice away from each default (tunic and heart colours at other palette values).
OTHER_PLAYER_SETTINGS = (
    PlayerSettings(SelectSwap.OFF, LowHealthBeep.KEPT, DeathWarp.CONTROLLER2_UP_A, True,
                   (0x01, 0x02, 0x03), 0x30, Music.OFF, "PALACE", "RANDOM"),
    PlayerSettings(SelectSwap.SWAP_ONLY, death_warp=DeathWarp.CONTROLLER1_UP_SELECT, level_word="DEN"),
)
SEEDS = (1, 2)


def z1r_with(base: str = MVP_BASELINE_LEVEL_ENCODING_OFF, toggles: dict[str, ThreeState] | None = None,
             options: dict[str, int] | None = None) -> str:
    return encode(decode(base).updated(options=options or {}, toggles=toggles or {}))


@cache
def finished(flag_string: str, seed: int, zora_flag_string: str = "") -> bytes:
    return generate_rom(flag_string, seed, vanilla(), zora_flag_string=zora_flag_string).rom


def assert_reserved_bytes_are_prg0(rom: bytes, label: str) -> None:
    original = vanilla()
    changed = {offset for offset in RESERVED_BYTES if rom[offset] != original[offset]}
    assert not changed, (label, hits(changed))


def every_turn_off_string() -> str:
    return z1r_with(toggles=dict.fromkeys(TURN_OFF_TOGGLES + OWNER_TURN_OFF_TOGGLES, ThreeState.OFF),
                    options={field_id: min(values) for field_id, values in TURN_OFF_OPTIONS.items()})


FINISHED_CASES = {
    "baseline": (MVP_BASELINE_LEVEL_ENCODING_OFF, ""),
    "every owner flag on": (z1r_with(toggles=BASELINE_FOR_OWNER_FLAGS), EVERY_OWNER_FLAG_ON),
    "every turn-off value, every owner flag on": (every_turn_off_string(), EVERY_OWNER_FLAG_ON),
}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FINISHED_CASES))
def test_finished_roms_hold_prg0_in_the_reserved_ranges(case: str, seed: int) -> None:
    flag_string, zora_flag_string = FINISHED_CASES[case]
    assert_reserved_bytes_are_prg0(finished(flag_string, seed, zora_flag_string), case)


def test_level_encoding_leaves_the_reserved_ranges() -> None:
    if not level_encoding.is_available():
        pytest.skip("the private level-encoding module is not installed")
    flag_string = z1r_with(MVP_BASELINE, toggles=BASELINE_FOR_OWNER_FLAGS)
    assert_reserved_bytes_are_prg0(finished(flag_string, 1, EVERY_OWNER_FLAG_ON), "level encoding")


@pytest.mark.parametrize("settings", OTHER_PLAYER_SETTINGS, ids=["off-kept-pad2", "swap-only"])
def test_player_settings_leave_the_reserved_ranges(settings: PlayerSettings) -> None:
    flag_string, zora_flag_string = FINISHED_CASES["every owner flag on"]
    rom = finished(flag_string, 1, zora_flag_string)
    assert_reserved_bytes_are_prg0(apply_player_settings(rom, settings), str(settings))


def produced_values() -> dict[str, tuple[str, str]]:
    """One case per produced flag value away from the baseline: each turn-off and alternative
    value (FL-OFF-07, FL-ALT-02 to 04; C17's every limit) and each ZORA flag on (the version-1
    sword hearts cap at each choice)."""
    cases: dict[str, tuple[str, str]] = {}
    for toggle in TURN_OFF_TOGGLES + OWNER_TURN_OFF_TOGGLES:
        # B23 off is produced only together with B22 off (as in FL-OFF-01's Check string).
        off = ("B22", "B23") if toggle == "B23" else (toggle,)
        cases[f"{toggle} off"] = (z1r_with(toggles=dict.fromkeys(off, ThreeState.OFF)), "")
    for table in (TURN_OFF_OPTIONS, ALTERNATIVE_OPTIONS):
        for field_id, values in table.items():
            for value in sorted(values):
                cases[f"{field_id}={value}"] = (z1r_with(options={field_id: value}), "")
    owner_baseline = z1r_with(toggles=BASELINE_FOR_OWNER_FLAGS)
    zora_values: list[tuple[str, dict[str, Any]]] = [
        # Randomize Magical Sword refuses a cap above 12 hearts.
        ("randomize_magical_sword", {"randomize_magical_sword": True, "magical_sword_hearts_highest": 12}),
        ("randomize_letter", {"randomize_letter": True}),
        ("progressive_items", {"progressive_items": True}),
        ("shop_items_in_pool", {"shop_items_in_pool": True}),
        *((f"sword hearts {cap}", {"magical_sword_hearts_highest": cap}) for cap in zora_flags.HEARTS_CAP_CHOICES),
        *((name, {name: ThreeState.ON, "progressive_items": name == "add_l4_sword"})
          for name in zora_flags.OWNER_2_0_FIELDS),
    ]
    for label, changes in zora_values:
        cases[label] = (owner_baseline, zora_flags.encode(replace(zora_flags.DEFAULT, **changes)))
    return cases


PRODUCED_VALUES = produced_values()


@pytest.mark.slow
@pytest.mark.parametrize("case", list(PRODUCED_VALUES))
def test_each_produced_value_leaves_the_reserved_ranges(case: str) -> None:
    flag_string, zora_flag_string = PRODUCED_VALUES[case]
    assert_reserved_bytes_are_prg0(finished(flag_string, 1, zora_flag_string), case)


# --- Archipelago's slot identity (Phase 4c) ----------------------------------------------------

def test_the_archipelago_slot_identity_is_clear() -> None:
    """Its 32 bytes in bank 0 (docs/rom-map.md "Archipelago slot identity") are PRG0's free $FF,
    clear of z1rr-coop's blocks, the level encoding's region and sites, every patch's bytes and
    every builder's free-space slot (ASNB's too, when its builder is in the tree)."""
    from zora.rom.slot_identity import SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_SIZE
    slot = range(SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE)
    assert not hits(slot)
    assert all(not set(slot) & set(site) for site in LEVEL_ENCODING_SITES)
    for patches in (SERIES_PATCHES, FLAG_PATCHES):
        assert all(not written(pieces) & set(slot) for pieces in patches.values())
    for path in (REPO / "asm" / name / "build.py" for name in ("progressive", "flags2", "asnb")):
        builder = _module(f"slot_{path.parent.name}_build", path)
        if builder is not None:
            assert all(not set(space.file_range()) & set(slot) for space in builder.FREE_SPACE.values()), path
    assert set(vanilla()[slot.start:slot.stop]) == {0xFF}
    rom_map = REPO / "docs" / "rom-map.md"
    if rom_map.exists():
        assert f"0x{slot.start:05X}-0x{slot.stop - 1:05X}" in rom_map.read_text()


def test_an_external_rom_with_a_slot_name_leaves_the_reserved_ranges() -> None:
    from tests.test_assignment import identity
    from zora import archipelago
    from zora.model.item_names import ITEM_NAMES
    result = archipelago.build_from_strings(*FINISHED_CASES["every owner flag on"], 1, vanilla())
    assignment = {place: ITEM_NAMES[item] for place, item in identity(result.state).items()}  # type: ignore[index]
    rom = archipelago.finish(result, assignment, ap_name=b"Player-One")
    assert archipelago.rom_identity(rom) is not None
    assert_reserved_bytes_are_prg0(rom, "External mode with a slot name")
