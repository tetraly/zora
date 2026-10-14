"""The ROM side of All Swords No Boards (docs/design/asnb.md section 3; asm/asnb/):
asm/asnb/asnb_data.py matches a fresh build; the seven TakeGradeWithL4 and the seven l4-sword-look
copies are the same bytes at the same address in banks 0-6, and the three ResolveProgressive copies
the same bytes with sword-cap; what each routine returns and keeps, run on tests/mini6502.py
(l4-sword-look: the palette row and item slot the A box, the world's items and the swing are drawn
with, for sword levels 1-4, levels 1-3 as ZORA draws them without it); no byte written by two
patches (these, the series, the flag patches, the player settings, the overworld Wizzrobe
routine); none of z1rr-coop's reserved bytes or the level encoding's sites written; ZORA's
output holds each patch its flags ask for (zora/rom/owner_patches.py) and leaves the others'
bytes as it has them without them. The patches in play: tests/test_asnb_emulator.py."""
import importlib.util
import shutil
from itertools import combinations, product
from pathlib import Path
from types import ModuleType

import pytest

from tests.mini6502 import CPU
from tests.test_coop_reserved import FINISHED_CASES, LEVEL_ENCODING_SITES, finished, hits, written
from tests.test_feature_patches import vanilla
from tests.test_progressive_patches import (
    BANK_SIZE,
    ITEMS,
    JSR,
    NOP,
    RAM_CODE_LOAD,
    RAM_CODE_RUN,
    SWORD,
    Inventory,
    cpu_address,
    cpu_for,
    expected_resolve,
    inventories,
    patched,
    resolve_entries,
)
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.rom.base_rom import Original, original_bytes, piece_bytes
from zora.rom.code_patch_data import PATCHES as SERIES_PATCHES
from zora.rom.layout import NES_HEADER_SIZE, OVERWORLD_WIZZROBE_PATCH
from zora.rom.owner_patches import RETIRED_PATCHES

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


build = _module("asnb_build", REPO / "asm" / "asnb" / "build.py")
data = build.load_data()
flags2 = _module("asnb_flags2_build", REPO / "asm" / "flags2" / "build.py").load_data()
settings = _module("zora.rom._asm_player_settings_data", REPO / "asm" / "settings" / "player_settings_data.py")

TAKE_BANKS = range(7)
TAKE_ADDRESS = 0xBFE0
GRADED_TAKE_HOOK = 0x06D04             # HandleClass2: LDA $0A / CMP Items, Y
LEVEL_9_GATE_HOOK = 0x04AB1            # InitUnderworldPersonC: LDA InvTriforce / CMP #$FF / BNE @Exit
HANDLE_CLASS_2 = 0xACF4                # bank 1, in the RAM code block
ITEM_SLOT_SWORD = 0x00
ITEM_SLOT_RING = 0x0B                  # HandleClass2 recolors Link after a ring: not run here
MAGICAL_SWORD_GRADE, L4_SWORD_LEVEL = 0x03, 0x04
GRADE_ADDRESS = 0x0A                   # [0A]: the grade TakeItem takes
CMP_IMMEDIATE, LDA_ABSOLUTE, BCC = 0xC9, 0xAD, 0x90
INV_SWORD = ITEMS + ITEM_SLOT_SWORD
# l4-sword-look (CPU addresses: bank 7, the RAM code block, and the copies in banks 0-6)
LOOK_ADDRESS = 0xBFC0                  # LookSwordInWorld; SwingRowWithL4 follows it
SWING_ROW = 0xBFD4
SWING_HOOK = 0x1F7FB                   # UpdateSwordOrRod's @CalcSwordAttrs: CLC / ADC Items / SEC / SBC #$01
WORLD_HOOK = 0x1E73E                   # AnimateItemObject's JMP DrawItemBySlot
ANIMATE_ITEM_OBJECT = 0xE70E
DRAW_ITEM_IN_INVENTORY = 0xE735
WRITE_STATIC_ITEM_SPRITES = 0x790C     # Anim_WriteStaticItemSpritesWithAttributes: A attributes, Y item slot
FETCH_OBJECT_POSITION = 0xFA93         # Anim_FetchObjPosForSpriteDescriptor
JMP_ABSOLUTE = 0x4C
SWORD_OBJECT_SLOT, ROOM_ITEM_OBJECT_SLOT = 0x0D, 0x13
FLASHING_ITEM_SLOTS = {0x16, 0x19, 0x1A, 0x1B}     # DrawItemBySlot's LSR path, which mini6502 lacks
ITEM_IDS = range(0x24)
ITEM_ID_TO_SLOT = 0x72A4               # ItemIdToSlot, in the RAM code block
MAGICAL_SWORD_ITEM, MAGICAL_SWORD_ICON_SLOT, WHITE_SWORD_ROW = 0x03, 0x20, 1
SWORD_LEVELS = range(1, L4_SWORD_LEVEL + 1)
SWING_BASE_ATTRIBUTES = (0x00, 0x80)  # RDirectionToWeaponBaseAttribute: down flips vertically
SWORD_CAP_SLOTS = {1: build.GROWTH["ZORA_FP_PROG_01_RESOLVE"], 4: build.GROWTH["ZORA_FP_PROG_02_ARMOS"],
                   5: build.GROWTH["ZORA_FP_PROG_02_ROOM"]}


def asnb_rom(sword_line_to_l4: bool = True) -> bytes:
    """ZORA's output (seed 1) with the progressive patches and the three ASNB patches."""
    return bytes(build.apply_patches(patched(), sword_line_to_l4=sword_line_to_l4))


def series_image() -> bytes:
    """PRG0 with every series patch written: the ZORA build, outside the serializer's data."""
    out = bytearray(vanilla())
    for pieces in SERIES_PATCHES.values():
        for offset, piece in pieces:
            new = piece_bytes(piece)
            out[offset:offset + len(new)] = new
    return bytes(out)


# --- the build -------------------------------------------------------------------------

def test_module_matches_a_fresh_build() -> None:
    if not (shutil.which("ca65") and shutil.which("ld65") and build.tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    vanilla()
    assert build.render(build.build_all()) == build.OUTPUT.read_text()


def test_every_patch_is_built() -> None:
    assert tuple(data.PATCHES) == build.PATCHES == ("take-l4", "sword-cap", "level-9-gate", "l4-sword-look")
    assert all(data.PATCHES[name] for name in build.PATCHES)


def test_kept_bytes_are_read_from_prg0() -> None:
    rom = vanilla()
    for name, pieces in data.PATCHES.items():
        for _, piece in pieces:
            if isinstance(piece, Original):
                assert original_bytes(piece.source, piece.length) == rom[piece.source:piece.source + piece.length], name


# --- 3a: TakeGradeWithL4 ----------------------------------------------------------------

def test_the_take_copies_are_identical_at_one_address_in_banks_0_to_6() -> None:
    """TakeItem runs from work RAM with any of banks 0-6 in: each holds the same routine at
    $BFE0, and the hook calls it there."""
    rom = asnb_rom()
    assert set(data.TAKE_COPIES) == set(TAKE_BANKS)
    copies = {bank: rom[first:end] for bank, (first, end) in data.TAKE_COPIES.items()}
    assert len(set(copies.values())) == 1
    assert {cpu_address(first) for first, _ in data.TAKE_COPIES.values()} == {TAKE_ADDRESS}
    assert {bank for bank, (first, _) in data.TAKE_COPIES.items()
            if (first - NES_HEADER_SIZE) // BANK_SIZE == bank} == set(TAKE_BANKS)
    hook = bytes([JSR, TAKE_ADDRESS & 0xFF, TAKE_ADDRESS >> 8, NOP, NOP])
    assert rom[GRADED_TAKE_HOOK:GRADED_TAKE_HOOK + len(hook)] == hook


def expected_take(slot: int, grade: int, held: int) -> int:
    """The grade stored: level 4 for the magical sword taken at sword level 3."""
    return L4_SWORD_LEVEL if (slot, grade, held) == (ITEM_SLOT_SWORD, MAGICAL_SWORD_GRADE, 3) else grade


@pytest.mark.parametrize("bank", list(TAKE_BANKS))
def test_take_grade_with_l4_returns_the_grade_and_its_compare(bank: int) -> None:
    """For each slot, grade and level held: A is the grade to store and C its compare with the
    slot's level (the BCC after the hook skips the store when lower); X and Y are kept."""
    rom = asnb_rom()
    for slot, grade, held in product((ITEM_SLOT_SWORD, 0x02, 0x04, ITEM_SLOT_RING), range(5), range(5)):
        cpu = cpu_for(rom, bank)
        cpu[ITEMS + slot] = held
        cpu[GRADE_ADDRESS] = grade
        cpu.x, cpu.y = 0x5A, slot
        cpu.call(TAKE_ADDRESS)
        stored = expected_take(slot, grade, held)
        assert (cpu.a, cpu.carry, cpu.x, cpu.y) == (stored, stored >= held, 0x5A, slot), (slot, grade, held)


@pytest.mark.parametrize("bank", list(TAKE_BANKS))
def test_handle_class_2_gives_level_4_with_any_bank_in(bank: int) -> None:
    """TakeItem's graded store, run from work RAM with each bank switched in: the magical sword
    at sword level 3 gives level 4; at levels 0-2 a sword grade raises the level as before; at
    level 4 nothing lowers it."""
    rom = asnb_rom()
    entry = RAM_CODE_RUN + HANDLE_CLASS_2 - RAM_CODE_LOAD
    for grade, held in product(range(1, 4), range(5)):
        cpu = cpu_for(rom, bank, Inventory((held, 0, 0, 0)))
        cpu[GRADE_ADDRESS] = grade
        cpu.y = ITEM_SLOT_SWORD
        cpu.call(entry)
        assert cpu[INV_SWORD] == max(held, expected_take(ITEM_SLOT_SWORD, grade, held)), (grade, held)


# --- 3b: the sword line tops out at level 4 ------------------------------------------------

@pytest.mark.parametrize("sword_line_to_l4", [True, False])
def test_the_three_resolve_copies_are_byte_identical(sword_line_to_l4: bool) -> None:
    """With sword-cap the body is the same bytes in banks 1, 4 and 5 (each per-seed operand at
    the same place in it), inside the copy's slot; bank 1's on/off check stays in front."""
    rom = asnb_rom(sword_line_to_l4)
    bodies = {bank: rom[first:end] for bank, (first, end) in data.RESOLVE_COPIES.items()}
    assert set(bodies) == {1, 4, 5}
    assert bodies[1] == bodies[4] == bodies[5]
    places = {data.SYMBOLS[f"ZORA_B{bank}_SwordLineToL4"] - first for bank, (first, _) in data.RESOLVE_COPIES.items()}
    assert len(places) == 1
    for bank, (first, end) in data.RESOLVE_COPIES.items():
        assert first in SWORD_CAP_SLOTS[bank].file_range() and end - 1 in SWORD_CAP_SLOTS[bank].file_range()
        operand = data.SYMBOLS[f"ZORA_B{bank}_SwordLineToL4"]
        assert (rom[operand - 1], rom[operand]) == (CMP_IMMEDIATE, int(sword_line_to_l4)), bank


def expected_with_cap(item: int, inventory: Inventory) -> tuple[int, bool, bool]:
    """expected_resolve with the sword line topping out at level 4: up to level 3 a sword item
    shows its next level ($03 at level 3, not the top), at level 4 the magical sword as the top."""
    shown, in_line, at_top = expected_resolve(item, inventory)
    if item in SWORD.items:
        return shown, in_line, inventory.level(SWORD) >= L4_SWORD_LEVEL
    return shown, in_line, at_top


def run_resolve(rom: bytes, bank: int, item: int, inventory: Inventory) -> CPU:
    cpu = cpu_for(rom, bank, inventory)
    cpu.a, cpu.x, cpu.y = item, 0x5A, 0xC3
    cpu.call(resolve_entries(rom)[bank])
    return cpu


@pytest.mark.parametrize("sword_line_to_l4", [True, False])
def test_resolve_progressive_with_sword_cap_in_every_bank(sword_line_to_l4: bool) -> None:
    """For every item ID $00-$3F and every inventory (the sword up to level 4): with the byte
    $01 the sword line's top is level 4, every other line as before; with $00 every line as
    before (tests/test_progressive_patches.py). X is kept."""
    rom = asnb_rom(sword_line_to_l4)
    expected = expected_with_cap if sword_line_to_l4 else expected_resolve
    states = list(inventories())
    for bank, item in product((1, 4, 5), range(0x40)):
        for inventory in states:
            cpu = run_resolve(rom, bank, item, inventory)
            shown, in_line, at_top = expected(item, inventory)
            assert (cpu.a, cpu.carry, cpu.x) == (shown, in_line, 0x5A), (bank, hex(item), inventory)
            if in_line:
                assert bool(cpu[0x01]) == at_top, (bank, hex(item), inventory)


ZERO_PAGE_PATTERN = 0xC7


@pytest.mark.parametrize("bank", [1, 4, 5])
def test_resolve_progressive_with_sword_cap_uses_only_00_and_01(bank: int) -> None:
    rom = asnb_rom()
    for item, level in product(SWORD.items, range(L4_SWORD_LEVEL + 1)):
        cpu = cpu_for(rom, bank, Inventory((level, 0, 0, 0)))
        for address in range(0x100):
            cpu[address] = ZERO_PAGE_PATTERN
        cpu.a, cpu.x, cpu.y = item, 0x5A, 0xC3
        cpu.call(resolve_entries(rom)[bank])
        assert [address for address in range(0x02, 0x100) if cpu[address] != ZERO_PAGE_PATTERN] == []


# --- 3c: the level-9 gate --------------------------------------------------------------------

def test_the_gate_reads_the_sword_level() -> None:
    """InitUnderworldPersonC's LDA InvTriforce / CMP #$FF / BNE @Exit becomes LDA InvSword /
    CMP #$04 / BCC @Exit, the same branch target."""
    rom, original = asnb_rom(), vanilla()
    site = slice(LEVEL_9_GATE_HOOK, LEVEL_9_GATE_HOOK + 7)
    assert rom[site] == bytes([LDA_ABSOLUTE, INV_SWORD & 0xFF, INV_SWORD >> 8, CMP_IMMEDIATE, L4_SWORD_LEVEL,
                               BCC, original[LEVEL_9_GATE_HOOK + 6]])


# --- l4-sword-look: level 4 looks like the magical sword in the white sword's colors ----------------

def look_rom() -> bytes:
    """ZORA's output (seed 1) with the progressive patches and l4-sword-look alone."""
    return bytes(build.apply_patches(patched(), ("l4-sword-look",)))


def test_the_look_copies_are_identical_at_one_address_in_banks_0_to_6() -> None:
    """AnimateItemObject and the swing run with any of banks 0-6 in: each holds the same two
    routines at $BFC0, inside the 32-byte slot, and the hooks call them there."""
    rom = look_rom()
    assert set(data.LOOK_COPIES) == set(TAKE_BANKS)
    copies = {bank: rom[first:end] for bank, (first, end) in data.LOOK_COPIES.items()}
    assert len(set(copies.values())) == 1
    assert {cpu_address(first) for first, _ in data.LOOK_COPIES.values()} == {LOOK_ADDRESS}
    assert {(first - NES_HEADER_SIZE) // BANK_SIZE for first, _ in data.LOOK_COPIES.values()} == set(TAKE_BANKS)
    assert all(end - first <= 32 for first, end in data.LOOK_COPIES.values())
    assert rom[WORLD_HOOK:WORLD_HOOK + 3] == bytes([JMP_ABSOLUTE, LOOK_ADDRESS & 0xFF, LOOK_ADDRESS >> 8])
    assert rom[SWING_HOOK:SWING_HOOK + 7] == bytes([JSR, SWING_ROW & 0xFF, SWING_ROW >> 8, NOP, NOP, NOP, NOP])


def drawn(cpu: CPU, entry: int) -> tuple[int, int]:
    """Run a draw routine to its sprite writer: (palette row and flips, item slot) it draws with."""
    seen: list[tuple[int, int]] = []
    cpu.stubs[WRITE_STATIC_ITEM_SPRITES] = lambda cpu: seen.append((cpu.a, cpu.y))
    cpu.stubs[FETCH_OBJECT_POSITION] = lambda cpu: None
    cpu.call(entry)
    assert len(seen) == 1
    return seen[0]


def a_box(rom: bytes, bank: int, level: int) -> tuple[int, int]:
    """The status bar's sword at `level` (DrawStatusBarSword: DrawItemInInventory, X and Y slot 0)."""
    cpu = cpu_for(rom, bank, Inventory((level, 0, 0, 0)))
    cpu.x = cpu.y = ITEM_SLOT_SWORD
    return drawn(cpu, DRAW_ITEM_IN_INVENTORY)


def world_item(rom: bytes, bank: int, item: int, level: int) -> tuple[int, int]:
    """A room, cave or shop item, or the item Link holds up (AnimateItemObject, A the item ID)."""
    cpu = cpu_for(rom, bank, Inventory((level, 0, 0, 0)))
    cpu.a, cpu.x = item, ROOM_ITEM_OBJECT_SLOT
    return drawn(cpu, ANIMATE_ITEM_OBJECT)


@pytest.mark.parametrize("bank", list(TAKE_BANKS))
def test_the_a_box_draws_level_4_as_the_magical_sword_in_row_1(bank: int) -> None:
    """Levels 1-3 as ZORA draws them without the patch (rows 0, 1 and 2; the magical sword's icon
    at level 3); level 4 the magical sword's icon in the white sword's row 1 (row 3, the plain
    sword's icon, without the patch)."""
    rom, today = look_rom(), patched()
    for level in SWORD_LEVELS[:-1]:
        assert a_box(rom, bank, level) == a_box(today, bank, level), level
    assert a_box(today, bank, L4_SWORD_LEVEL) == (3, ITEM_SLOT_SWORD)
    assert a_box(rom, bank, L4_SWORD_LEVEL) == (WHITE_SWORD_ROW, MAGICAL_SWORD_ICON_SLOT)


@pytest.mark.parametrize("bank", list(TAKE_BANKS))
def test_world_items_draw_the_l4_sword_with_level_4s_look(bank: int) -> None:
    """Every item (but the flashing ones, which mini6502 can't draw) at sword levels 0-4 is drawn
    as without the patch, except the magical sword at sword level 3 or 4: the magical sword's icon
    in row 1 (row 2 without the patch)."""
    rom, today = look_rom(), patched()
    slots = cpu_for(rom, bank)
    for item, level in product(ITEM_IDS, range(L4_SWORD_LEVEL + 1)):
        if slots[ITEM_ID_TO_SLOT + item] in FLASHING_ITEM_SLOTS:
            continue
        before = world_item(today, bank, item, level)
        if item == MAGICAL_SWORD_ITEM and level >= MAGICAL_SWORD_GRADE:
            assert before == (2, MAGICAL_SWORD_ICON_SLOT)
            assert world_item(rom, bank, item, level) == (WHITE_SWORD_ROW, MAGICAL_SWORD_ICON_SLOT), level
        else:
            assert world_item(rom, bank, item, level) == before, (hex(item), level)


@pytest.mark.parametrize("bank", list(TAKE_BANKS))
def test_the_swing_takes_row_1_at_level_4(bank: int) -> None:
    """SwingRowWithL4 returns the base attribute ORed with the row, levels 1-3 as PRG0's base +
    level - 1, level 4 row 1; X is the sword's object slot again, Y kept."""
    rom = look_rom()
    for base, level in product(SWING_BASE_ATTRIBUTES, SWORD_LEVELS):
        cpu = cpu_for(rom, bank, Inventory((level, 0, 0, 0)))
        cpu.a, cpu.x, cpu.y = base, SWORD_OBJECT_SLOT, 0x02
        cpu.call(SWING_ROW)
        row = WHITE_SWORD_ROW if level == L4_SWORD_LEVEL else level - 1
        assert (cpu.a, cpu.x, cpu.y) == (base | row, SWORD_OBJECT_SLOT, 0x02), (base, level)


# --- no shared bytes, no reserved bytes ---------------------------------------------------------

def test_no_two_patches_write_the_same_byte() -> None:
    """Between these patches, and between each of them and the series, the flag patches (but the
    retired l4-sword-take, which no flag writes: l4-sword-look reuses its bank 7 and bank 1
    bytes), every player setting's choices and
    the overworld red Wizzrobe routine. sword-cap rewrites fp-prog-01's and fp-prog-02's own code
    and lengthens it inside its slots, and writes no other series byte."""
    others = {f"series {name}": written(pieces) for name, pieces in SERIES_PATCHES.items()}
    others.update({f"flags2 {name}": written(pieces) for name, pieces in flags2.PATCHES.items()
                   if name not in RETIRED_PATCHES})
    for setting, choices in settings.SETTINGS.items():
        others[f"setting {setting}"] = set().union(*(written(runs) for runs in choices.values()))
    others["overworld Wizzrobe routine"] = written(OVERWORLD_WIZZROBE_PATCH)
    for (name_a, a), (name_b, b) in combinations(data.PATCHES.items(), 2):
        assert not written(a) & written(b), (name_a, name_b)
    progressive = others.pop("series fp-prog-01") | others.pop("series fp-prog-02")
    slots = {offset for space in SWORD_CAP_SLOTS.values() for offset in space.file_range()}
    for name, pieces in data.PATCHES.items():
        for other, offsets in others.items():
            assert not written(pieces) & offsets, (name, other)
    assert not (written(data.PATCHES["take-l4"]) | written(data.PATCHES["level-9-gate"])) & progressive
    assert written(data.PATCHES["sword-cap"]) <= progressive | slots


def test_no_patch_writes_a_reserved_or_level_encoding_byte() -> None:
    """z1rr-coop's reserved ranges (tests/test_coop_reserved.py) and the level encoding's sites."""
    encoding = {offset for site in LEVEL_ENCODING_SITES for offset in site}
    for name, pieces in data.PATCHES.items():
        assert not hits(written(pieces)), name
        assert not written(pieces) & encoding, name
    for segment, space in {**build.FREE_SPACE, **build.GROWTH}.items():
        assert not hits(space.file_range()), segment


def written_bytes(name: str, sword_line_to_l4: bool = True) -> dict[int, int]:
    """What patch `name` writes, byte by byte; for sword-cap with its per-seed operands set."""
    out = {offset + i: value for offset, piece in data.PATCHES[name] for i, value in enumerate(piece_bytes(piece))}
    if name == "sword-cap":
        out.update(dict.fromkeys(data.SYMBOLS.values(), build.SWORD_LINE_TO_L4 if sword_line_to_l4 else 0))
    return out


def expected_patches(zora_flag_string: str) -> set[str]:
    """The ASNB patches ZORA writes for a ZORA flag string (zora/rom/owner_patches.py): take-l4,
    sword-cap and l4-sword-look with Add L4 Sword on, level-9-gate with Level 9 Entrance = Level 4
    sword."""
    flags = zora_flags.decode(zora_flag_string) if zora_flag_string else zora_flags.DEFAULT
    names = {"take-l4", "sword-cap", "l4-sword-look"} if flags.add_l4_sword is ThreeState.ON else set()
    return names | ({"level-9-gate"} if getattr(flags, "level_9_entrance_sword", False) else set())


@pytest.mark.parametrize("case", list(FINISHED_CASES))
def test_zora_output_writes_the_patches_its_flags_ask_for(case: str) -> None:
    """In ZORA's output (the co-op test's finished cases: the baseline, every owner flag on, and
    every turn-off value with every owner flag on), each patch its flags ask for is written, sword-cap
    with its operands $01, and each other lands on the bytes ZORA writes without it: take-l4 and
    level-9-gate on PRG0's (the take slots blank), sword-cap on the ZORA build's (with Progressive
    Items on) or PRG0's (with it off, where fp-prog-02 is left out)."""
    flag_string, zora_flag_string = FINISHED_CASES[case]
    rom, original, series = finished(flag_string, 1, zora_flag_string), vanilla(), series_image()
    wanted = expected_patches(zora_flag_string)
    for name in build.PATCHES:
        expected = written_bytes(name)
        if name in wanted:
            assert {offset: rom[offset] for offset in expected} == expected, name
            continue
        unwritten = series if name == "sword-cap" and zora_flag_string else original
        assert all(rom[offset] == unwritten[offset] for offset in expected), name
    if "take-l4" not in wanted:
        for space in build.FREE_SPACE.values():
            assert set(rom[space.file_range().start:space.file_range().stop]) == {0xFF}


def test_the_baseline_writes_no_asnb_patch() -> None:
    assert expected_patches(FINISHED_CASES["baseline"][1]) == set()
