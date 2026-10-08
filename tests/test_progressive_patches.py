"""The progressive-items patches of asm/progressive/ (docs/progressive-patches.md),
without the emulator: the build and its bytes, the free space, the hook
sites, and each routine run on its own in a small 6502 interpreter
(tests/mini6502.py), which shows what a routine keeps (X, [00], [01]) and
returns for every item and inventory state.

The patches are not wired into the serializer yet. Each test writes them
over a finished ZORA ROM (generate_rom, the public API) with
asm/progressive/build.py's helpers; tests/test_progressive_emulator.py plays
the same ROMs."""
import importlib.util
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from itertools import product
from pathlib import Path
from types import ModuleType

import pytest

from tests.mini6502 import CPU
from tests.test_feature_patches import vanilla
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import original_bytes, piece_length
from zora.rom.layout import ARMOS_ITEM_ADDRESS, ASM_NOTHING_CODE_PATCH_OFFSET, COAST_ITEM_ADDRESS, NES_HEADER_SIZE

REPO = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _module("progressive_build", REPO / "asm" / "progressive" / "build.py")
data = build.load_data()

SEEDS = (1, 2, 3)
RANDOMIZE_MAGICAL_SWORD = "1.D"      # a ZORA flag string whose ROMs use the $0E "no item" code
BANK_SIZE = 0x4000

# CPU RAM and work RAM (the pinned disassembly's src/Variables.inc, CaveVars.inc)
ROOM_ITEM_ID = 0xAB
ROOM_ID = 0xEB
OBJ_TYPE = 0x34F
CAVE_FLAGS = 0x413
CAVE_ITEM_IDS = 0x422
CAVE_PRICES = 0x430
ITEMS = 0x657
POTION = 0x65E                       # 1: blue, 2: red
INV_BOOMERANG, INV_MAGIC_BOOMERANG = 0x674, 0x675
SHOP_BOUGHT_FLAGS = ITEMS + 0x20      # fp-prog-01's saved RAM (docs/progressive-patches.md "RAM")
LEVEL_BLOCK_ATTRS_F = 0x6AFE
# Bank 1's RAM code (ItemIdToSlot, ItemIdToDescriptor, ...): loaded from $A500, run at $6C90.
RAM_CODE_LOAD, RAM_CODE_RUN = 0xA500, 0x6C90
RAM_CODE_SIZE = 0x8000 - RAM_CODE_RUN

JSR, JMP, NOP, CMP_ABSOLUTE = 0x20, 0x4C, 0xEA, 0xCD
LDY_ABSOLUTE, BNE, CLC, RTS = 0xAC, 0xD0, 0x18, 0x60


# --- the upgrade lines, in game terms ---------------------------------------------

@dataclass(frozen=True)
class Line:
    """An upgrade line: its item IDs by level and its Items slot."""
    name: str
    items: tuple[int, ...]
    slot: int


SWORD = Line("sword", (0x01, 0x02, 0x03), 0x00)
CANDLE = Line("candle", (0x06, 0x07), 0x04)
ARROW = Line("arrow", (0x08, 0x09), 0x02)
RING = Line("ring", (0x12, 0x13), 0x0B)
GRADED_LINES = (SWORD, CANDLE, ARROW, RING)
WOODEN_BOOMERANG, MAGICAL_BOOMERANG = 0x1D, 0x1E
BOOMERANGS = (WOODEN_BOOMERANG, MAGICAL_BOOMERANG)
LINE_OF = {item: line for line in GRADED_LINES for item in line.items}
CAVE_NO_ITEM = 0x3F
BLUE_POTION, RED_POTION, HEART_CONTAINER, BOMBS = 0x1F, 0x20, 0x1A, 0x00


@dataclass(frozen=True)
class Inventory:
    """The inventory ResolveProgressive reads: each graded line's level
    and the two boomerangs."""
    levels: tuple[int, ...] = (0, 0, 0, 0)        # GRADED_LINES order
    wooden_boomerang: int = 0
    magical_boomerang: int = 0

    def level(self, line: Line) -> int:
        return self.levels[GRADED_LINES.index(line)]


def inventories() -> Iterator[Inventory]:
    ranges = [range(len(line.items) + 1) for line in GRADED_LINES]
    for levels in product(*ranges):
        yield Inventory(levels)
    for wooden, magical in product((0, 1), repeat=2):
        yield Inventory(wooden_boomerang=wooden, magical_boomerang=magical)


def expected_resolve(item: int, inventory: Inventory) -> tuple[int, bool, bool]:
    """(item shown and given, in a line, the line's top level held): the
    next level of the item's line, or the top level once it is held."""
    if item in LINE_OF:
        line = LINE_OF[item]
        level = inventory.level(line)
        return line.items[min(level, len(line.items) - 1)], True, level >= len(line.items)
    if item in BOOMERANGS:
        # The magical boomerang once the wooden one is held; the line's top
        # is the magical boomerang held (with or without the wooden one).
        return BOOMERANGS[inventory.wooden_boomerang], True, bool(inventory.magical_boomerang)
    return item, False, False


# --- ROMs --------------------------------------------------------------------------

@cache
def finished(seed: int, zora_flags: str = "") -> bytes:
    """ZORA's output for the MVP baseline flags (level encoding off) and `seed`."""
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, vanilla(), zora_flag_string=zora_flags).rom


@cache
def patched(progressive_items: bool = True, zora_flags: str = "") -> bytes:
    return bytes(build.progressive_rom(finished(1, zora_flags), progressive_items))


def bank_of(offset: int) -> int:
    return (offset - NES_HEADER_SIZE) // BANK_SIZE


def cpu_address(offset: int) -> int:
    bank = bank_of(offset)
    return offset - NES_HEADER_SIZE - bank * BANK_SIZE + (0xC000 if bank == 7 else 0x8000)


def word(rom: bytes, offset: int) -> int:
    return rom[offset] | rom[offset + 1] << 8


def cpu_for(rom: bytes, bank: int, inventory: Inventory | None = None) -> CPU:
    """A CPU with `bank` switched in, bank 1's RAM code in work RAM and the
    inventory in Items."""
    cpu = CPU(rom, bank)
    load = NES_HEADER_SIZE + 1 * BANK_SIZE + RAM_CODE_LOAD - 0x8000
    cpu.load_work_ram(RAM_CODE_RUN, rom[load:load + RAM_CODE_SIZE])
    inventory = inventory or Inventory()
    for line in GRADED_LINES:
        cpu[ITEMS + line.slot] = inventory.level(line)
    cpu[INV_BOOMERANG] = inventory.wooden_boomerang
    cpu[INV_MAGIC_BOOMERANG] = inventory.magical_boomerang
    return cpu


# --- hook sites ----------------------------------------------------------------------

@dataclass(frozen=True)
class Hook:
    """A hook: the PRG0 instructions it replaces (file offset and length; their bytes are
    read from the player's ROM) and the JSR plus NOPs that replace them, of the same length."""
    patch: str
    offset: int
    length: int
    what: str


HOOKS = {
    # InitCaveContinue: STA CaveFlags
    "cave flags": Hook("fp-prog-01", NES_HEADER_SIZE + 1 * BANK_SIZE + 0x0648, 3,
                       "StoreCaveFlagsAndFixUpWares"),
    # UpdateCavePersonState_TalkOrShopOrDoorCharge @Take: JSR SetRoomFlagUWItemState
    "take ware": Hook("fp-prog-01", NES_HEADER_SIZE + 1 * BANK_SIZE + 0x090F, 3,
                      "TakeWareAndMarkBought"),
    # CreateRoomObjects: STA RoomItemId / LDA LevelBlockAttrsF, Y
    "room item": Hook("fp-prog-02", NES_HEADER_SIZE + 5 * BANK_SIZE + 0x3854, 5,
                      "StoreRoomItemAtNextLevel"),
    # CreateRoomObjects @MakeHeartContainerOW: STA RoomItemId / LDA #$C0
    "coast item": Hook("fp-prog-02", NES_HEADER_SIZE + 5 * BANK_SIZE + 0x388B, 4,
                       "StoreCoastItemAtNextLevel"),
    # InitArmosOrFlyingGhini: STA RoomItemId / JSR GetRoomFlagUWItemState
    "Armos item": Hook("fp-prog-02", NES_HEADER_SIZE + 4 * BANK_SIZE + 0x0CF6, 5,
                       "StoreArmosItemAtNextLevel"),
}


def hook_target(rom: bytes, hook: Hook) -> int:
    """The CPU address the hook's JSR calls."""
    return word(rom, hook.offset + 1)


# --- the build -------------------------------------------------------------------------

def test_data_matches_a_fresh_build() -> None:
    """asm/progressive/progressive_data.py is what the two patch folders assemble to,
    on top of the whole of asm/series.txt; the build also checks each new
    segment against its free-space range (build.check_segments)."""
    if not (shutil.which("ca65") and shutil.which("ld65") and build.tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    vanilla()
    assert build.render(build.build_all()) == build.OUTPUT.read_text()


def test_new_bytes_sit_in_the_planned_free_space_which_zora_output_leaves_blank() -> None:
    """Every patch byte outside the five hook sites lies in one of the four
    planned ranges (bank 1 $BE40 and $BEE0, bank 5 $BA40, bank 4 $B480 within
    $B46F-$BEFF), and finished ZORA ROMs are $FF there (three seeds, and a
    ROM with Randomize Magical Sword, the $0E "no item" code)."""
    hook_bytes = {hook.offset + i for hook in HOOKS.values() for i in range(hook.length)}
    spaces = [space.file_range() for space in build.FREE_SPACE.values()]
    for name, runs in data.PATCHES.items():
        for offset, piece in runs:
            for byte in range(offset, offset + piece_length(piece)):
                assert byte in hook_bytes or any(byte in space for space in spaces), (name, hex(byte))
    roms = [finished(seed) for seed in SEEDS] + [finished(1, RANDOMIZE_MAGICAL_SWORD)]
    for rom in roms:
        for space in spaces:
            assert set(rom[space.start:space.stop]) == {0xFF}


def test_finished_roms_hold_every_byte_the_patches_replace() -> None:
    """No seed-varying write lands on a patched byte: the patches apply to
    finished ROMs of several seeds and to one with the $0E "no item" code
    (apply_patches refuses a ROM whose bytes differ from the build's)."""
    for rom in [finished(seed) for seed in SEEDS] + [finished(1, RANDOMIZE_MAGICAL_SWORD)]:
        build.apply_patches(rom)


def test_the_per_seed_bytes() -> None:
    """ZORA_B1_ProgressiveItems ($01 in the build) and ZORA_B1_OneTimeWares
    (blank in the build) are what the serializer would write per seed; the
    test helper writes the on/off byte and the one-time wares from the shop
    stock, one bit per shop (1 << shop number) per ware position."""
    plain = build.apply_patches(finished(1))
    on, wares = data.SYMBOLS["ZORA_B1_ProgressiveItems"], data.SYMBOLS["ZORA_B1_OneTimeWares"]
    assert plain[on] == 0x01 and plain[wares:wares + 3] == bytes(3)
    shop_a, shop_d = build.SHOP_TYPES[1], build.SHOP_TYPES[4]
    stocked = build.with_ware(build.with_ware(finished(1), shop_a, 0, HEART_CONTAINER), shop_d, 2, BOMBS)
    expected = build.one_time_wares(stocked)
    assert expected[0] & 1 << 1 and not expected[2] & 1 << 4
    written = build.write_seed_bytes(build.apply_patches(stocked), progressive_items=False)
    assert written[on] == 0 and written[wares:wares + 3] == expected


# --- the hook sites and the "no item" operand -------------------------------------------

def test_each_hook_replaces_whole_instructions_with_a_jsr_and_nops() -> None:
    """Hook sizes: each hook replaces the bytes of the PRG0 instructions it
    stands for (STA abs = 3 bytes; STA zp + LDA abs,Y = 5; STA zp + LDA # =
    4; STA zp + JSR = 5) with a JSR and NOPs of the same length, so every
    following instruction stays where it was; the Armos and coast item
    bytes (the LDA operands the serializer writes) stay before their hooks."""
    zora = finished(1)
    rom = patched()
    for name, hook in HOOKS.items():
        size = hook.length
        assert zora[hook.offset:hook.offset + size] == original_bytes(hook.offset, size), name
        assert rom[hook.offset] == JSR, name
        assert set(rom[hook.offset + 3:hook.offset + size]) <= {NOP}, name
        assert 0x8000 <= hook_target(rom, hook) < 0xC000, name              # in the hook's own bank
    assert ARMOS_ITEM_ADDRESS + 1 == HOOKS["Armos item"].offset
    assert COAST_ITEM_ADDRESS + 1 == HOOKS["coast item"].offset


def test_the_room_hook_reads_the_no_item_code_where_the_serializer_writes_it() -> None:
    """The plan's gotcha: CreateRoomObjects + 20 is CMP #$03 (C9 03 at file
    0x1785E), and the serializer writes its operand ($0E with the ZORA
    remap). The room hook compares with that operand (CMP $B84F), so it
    follows whichever code the ROM uses."""
    assert data.NOTHING_CODE_OPERAND == ASM_NOTHING_CODE_PATCH_OFFSET
    for zora_flags, code in (("", 0x03), (RANDOMIZE_MAGICAL_SWORD, 0x0E)):
        rom = finished(1, zora_flags)
        assert rom[ASM_NOTHING_CODE_PATCH_OFFSET - 1:ASM_NOTHING_CODE_PATCH_OFFSET + 1] == bytes([0xC9, code])
        assert build.nothing_code(rom) == code
    rom = patched()
    room_hook = cpu_address_to_offset(hook_target(rom, HOOKS["room item"]), 5)
    operand = cpu_address(ASM_NOTHING_CODE_PATCH_OFFSET)
    assert rom[room_hook:room_hook + 3] == bytes([CMP_ABSOLUTE, operand & 0xFF, operand >> 8])


def cpu_address_to_offset(address: int, bank: int) -> int:
    return NES_HEADER_SIZE + bank * BANK_SIZE + address - 0x8000


def test_the_three_copies_of_resolve_progressive_are_byte_identical() -> None:
    """ResolveProgressive's body is the same bytes in banks 1, 4 and 5; bank
    1's routine is its on/off check (LDY ZORA_B1_ProgressiveItems, BNE to
    the body, CLC, RTS) followed by that body."""
    rom = patched()
    bodies = {bank: rom[first:end] for bank, (first, end) in data.RESOLVE_COPIES.items()}
    assert set(bodies) == {1, 4, 5}
    assert bodies[1] == bodies[4] == bodies[5]
    first = data.RESOLVE_COPIES[1][0]
    on = cpu_address(data.SYMBOLS["ZORA_B1_ProgressiveItems"])
    check = bytes([LDY_ABSOLUTE, on & 0xFF, on >> 8, BNE, 0x02, CLC, RTS])
    assert rom[first - len(check):first] == check


# --- ResolveProgressive, run on its own -----------------------------------------------------

def resolve_entries(rom: bytes) -> dict[int, int]:
    """Bank -> the CPU address of its ResolveProgressive (bank 1's on/off check)."""
    entries = {bank: cpu_address(first) for bank, (first, _) in data.RESOLVE_COPIES.items()}
    entries[1] -= 7
    return entries


def run_resolve(rom: bytes, bank: int, item: int, inventory: Inventory, x: int = 0x5A) -> CPU:
    cpu = cpu_for(rom, bank, inventory)
    cpu.a, cpu.x, cpu.y = item, x, 0xC3
    cpu.call(resolve_entries(rom)[bank])
    return cpu


def test_resolve_progressive_gives_each_lines_next_level_in_every_bank() -> None:
    """For every item ID $00-$3F and every inventory of every line, each copy
    returns the next level of the item's line (C set, [01] nonzero at the
    top level), or the ID unchanged with C clear for an item in no line;
    X is kept. Quirk (plan): every line ID is below $1F, so the potions
    ($1F, $20; the red potion's descriptor reads as graded), the clock, a
    heart and a fairy are never swapped."""
    rom = patched()
    states = list(inventories())
    for bank, item in product((1, 4, 5), range(0x40)):
        for inventory in states:
            cpu = run_resolve(rom, bank, item, inventory)
            shown, in_line, at_top = expected_resolve(item, inventory)
            assert (cpu.a, cpu.carry, cpu.x) == (shown, in_line, 0x5A), (bank, hex(item), inventory)
            if in_line:
                assert bool(cpu[0x01]) == at_top, (bank, hex(item), inventory)


def test_resolve_progressive_with_the_off_byte_changes_nothing() -> None:
    """With ZORA_B1_ProgressiveItems = 0 bank 1's copy returns every ID
    unchanged with C clear, so caves show their wares as placed and only
    the buy-once rule runs."""
    rom = patched(progressive_items=False)
    for item, inventory in product(range(0x40), (Inventory((1, 1, 1, 1)), Inventory(wooden_boomerang=1))):
        cpu = run_resolve(rom, 1, item, inventory)
        assert (cpu.a, cpu.carry, cpu.x) == (item, False, 0x5A)


def test_every_line_is_graded_and_below_the_limit() -> None:
    """The plan's line rule against PRG0's tables: the graded items
    (ItemIdToDescriptor $2x) below $1F are exactly the four graded lines,
    each line's IDs are consecutive with one Items slot, and the ID after
    each line's top level is in another slot."""
    rom = patched()
    cpu = cpu_for(rom, 1)
    slot_table, descriptor_table = 0x72A4, 0x72C8              # ItemIdToSlot, ItemIdToDescriptor (RAM code)
    assert word(rom, cpu_address_to_offset(resolve_entries(rom)[5], 5) + 15) == slot_table   # LDA ItemIdToSlot, Y
    graded = {item for item in range(0x1F) if cpu[descriptor_table + item] & 0xF0 == 0x20}
    assert graded == set(LINE_OF)
    for line in GRADED_LINES:
        assert [cpu[slot_table + item] for item in line.items] == [line.slot] * len(line.items)
        assert cpu[slot_table + line.items[-1] + 1] != line.slot
        assert [cpu[descriptor_table + item] & 0x0F for item in line.items] == list(range(1, len(line.items) + 1))
    assert cpu[descriptor_table + RED_POTION] & 0xF0 == 0x20       # why the limit is $1F, not $24


# --- the hooks, run on their own -----------------------------------------------------------------

SCRATCH = (0xA5, 0x3C)               # [00] and [01] before a hook
KEPT_X = 0x5A


def run_hook(rom: bytes, hook: Hook, cpu: CPU) -> CPU:
    cpu.x = KEPT_X
    cpu[0x00], cpu[0x01] = SCRATCH
    cpu.call(hook_target(rom, hook))
    return cpu


def test_the_room_hook_under_both_no_item_codes() -> None:
    """StoreRoomItemAtNextLevel: every room item $00-$1F is stored at its
    line's next level, except the ROM's "no item" code ($03, or $0E with the
    remap), which is stored as it is; with the remap, $03 is the magical
    sword and upgrades like any sword. Returns the room's LevelBlockAttrsF
    byte with Y = RoomId, and keeps X, [00] and [01]."""
    for zora_flags, code in (("", 0x03), (RANDOMIZE_MAGICAL_SWORD, 0x0E)):
        rom = patched(zora_flags=zora_flags)
        for item, inventory in product(range(0x20), (Inventory(), Inventory((1, 1, 1, 1)), Inventory((3, 2, 2, 2)))):
            cpu = cpu_for(rom, 5, inventory)
            room = 0x37
            cpu[ROOM_ID], cpu.y, cpu.a = room, room, item
            cpu[LEVEL_BLOCK_ATTRS_F + room] = 0x47
            run_hook(rom, HOOKS["room item"], cpu)
            stored = item if item == code else expected_resolve(item, inventory)[0]
            assert cpu[ROOM_ITEM_ID] == stored, (zora_flags, hex(item), inventory)
            assert (cpu.a, cpu.y, cpu.x, cpu[0x00], cpu[0x01]) == (0x47, room, KEPT_X, *SCRATCH)
        assert expected_resolve(0x03, Inventory((1, 0, 0, 0)))[0] == 0x02


def test_the_coast_hook() -> None:
    """StoreCoastItemAtNextLevel: the coast item stored at its line's next
    level; returns A = $C0 (the item's Y, as LDA #$C0 left it) and keeps X,
    [00] and [01]."""
    rom = patched()
    for item, inventory in product(range(0x40), (Inventory(), Inventory((2, 1, 0, 2)))):
        cpu = cpu_for(rom, 5, inventory)
        cpu.a = item
        run_hook(rom, HOOKS["coast item"], cpu)
        assert cpu[ROOM_ITEM_ID] == expected_resolve(item, inventory)[0]
        assert (cpu.a, cpu.x, cpu[0x00], cpu[0x01]) == (0xC0, KEPT_X, *SCRATCH)


def test_the_armos_hook() -> None:
    """StoreArmosItemAtNextLevel: the Armos item stored at its line's next
    level, then GetRoomFlagUWItemState runs with X, [00] (the Armos code's
    stairs tile) and [01] as they were, and its result is returned for the
    BNE after the hook."""
    rom = patched()
    get_flag = word(finished(1), HOOKS["Armos item"].offset + 3)    # PRG0's JSR GetRoomFlagUWItemState
    for item, taken in product(range(0x40), (0x00, 0x10)):
        inventory = Inventory((1, 0, 1, 0), wooden_boomerang=1)
        seen: list[tuple[int, int, int]] = []

        def room_flag(cpu: CPU, taken: int = taken, seen: list[tuple[int, int, int]] = seen) -> None:
            seen.append((cpu.x, cpu[0x00], cpu[0x01]))
            cpu.a = taken
            cpu.p = cpu.p & ~0x02 | (0 if taken else 0x02)

        cpu = cpu_for(rom, 4, inventory)
        cpu.stubs[get_flag] = room_flag
        cpu.a = item
        run_hook(rom, HOOKS["Armos item"], cpu)
        assert cpu[ROOM_ITEM_ID] == expected_resolve(item, inventory)[0]
        assert seen == [(KEPT_X, *SCRATCH)]
        assert cpu.a == taken and bool(cpu.p & 0x02) == (not taken)
        assert (cpu.x, cpu[0x00], cpu[0x01]) == (KEPT_X, *SCRATCH)


# --- the cave hooks (bank 1), run on their own --------------------------------------------------------

POTION_SHOP, SHOP_A, SHOP_D = 0x74, 0x77, 0x7A
WOOD_SWORD_CAVE = 0x6A
SHOP_BIT = {POTION_SHOP: 0x01, SHOP_A: 0x02, SHOP_D: 0x10}       # LevelMasks[shop number]


def run_cave_init(rom: bytes, cave_type: int, wares: tuple[int, int, int], inventory: Inventory,
                  bought: tuple[int, int, int] = (0, 0, 0), potion: int = 0) -> CPU:
    cpu = cpu_for(rom, 1, inventory)
    cpu[POTION] = potion
    cpu[OBJ_TYPE + 1] = cave_type
    for ware, (item, flag_bits) in enumerate(zip(wares, (0x40, 0x80, 0xC0), strict=True)):
        cpu[CAVE_ITEM_IDS + ware] = flag_bits | item
        cpu[CAVE_PRICES + ware] = 10 + ware
        cpu[SHOP_BOUGHT_FLAGS + ware] = bought[ware]
    cpu.a = 0x6E
    cpu.x = 0x03                                           # InitCaveContinue leaves X = 3 after its loop
    cpu.call(hook_target(rom, HOOKS["cave flags"]))
    assert (cpu.a, cpu[CAVE_FLAGS], cpu.x) == (0x6E, 0x6E, 0x03)
    return cpu


def ware_items(cpu: CPU) -> list[int]:
    return [cpu[CAVE_ITEM_IDS + ware] & 0x3F for ware in range(3)]


def test_the_cave_hook_shows_each_ware_at_its_next_level() -> None:
    """StoreCaveFlagsAndFixUpWares: CaveFlags is stored and returned in A,
    X is kept, each ware's cave flags (top two bits) stay; a shop hides an
    upgrade whose line is at the top level (no item, price 0); a cave that
    gives items away shows the top level instead; other wares, and the
    potion shop's potions for every potion held, are left as placed."""
    rom = patched()
    for line, level in ((graded, level) for graded in GRADED_LINES for level in range(len(graded.items) + 1)):
        inventory = Inventory(tuple(level if other == line else 0 for other in GRADED_LINES))
        for cave_type in (SHOP_A, WOOD_SWORD_CAVE):
            cpu = run_cave_init(rom, cave_type, (line.items[0], BOMBS, CAVE_NO_ITEM), inventory)
            top = level >= len(line.items)
            if top and cave_type == SHOP_A:
                assert ware_items(cpu) == [CAVE_NO_ITEM, BOMBS, CAVE_NO_ITEM] and cpu[CAVE_PRICES] == 0
            else:
                assert ware_items(cpu) == [line.items[min(level, len(line.items) - 1)], BOMBS, CAVE_NO_ITEM]
                assert cpu[CAVE_PRICES] == 10
            assert [cpu[CAVE_ITEM_IDS + ware] & 0xC0 for ware in range(3)] == [0x40, 0x80, 0xC0]
    for potion in range(3):
        cpu = run_cave_init(rom, POTION_SHOP, (BLUE_POTION, RED_POTION, CAVE_NO_ITEM), Inventory(),
                            potion=potion)
        assert ware_items(cpu) == [BLUE_POTION, RED_POTION, CAVE_NO_ITEM], potion


def test_the_cave_hook_hides_wares_bought_in_this_shop_only() -> None:
    """A ware whose bought bit (Items+$20 + position, this shop's bit) is
    set is hidden in that shop, whatever it holds; the same position in
    another shop, and caves that are not shops, ignore the bit."""
    rom = patched()
    wares = (HEART_CONTAINER, SWORD.items[0], BOMBS)
    bought = (SHOP_BIT[SHOP_A], SHOP_BIT[SHOP_A], 0)
    cpu = run_cave_init(rom, SHOP_A, wares, Inventory(), bought)
    assert ware_items(cpu) == [CAVE_NO_ITEM, CAVE_NO_ITEM, BOMBS]
    assert [cpu[CAVE_PRICES + ware] for ware in range(3)] == [0, 0, 12]
    for other in (SHOP_D, WOOD_SWORD_CAVE):
        assert ware_items(run_cave_init(rom, other, wares, Inventory(), bought)) == list(wares)


def test_the_take_hook_marks_one_time_wares_bought() -> None:
    """TakeWareAndMarkBought: SetRoomFlagUWItemState still runs; a shop ware
    marked in ZORA_B1_OneTimeWares sets this shop's bit in its position's
    bought byte, a re-buyable ware does not, and a cave that is not a shop
    marks nothing; X is kept."""
    one_time = bytes([SHOP_BIT[SHOP_A], 0, SHOP_BIT[SHOP_D]])
    rom = build.write_seed_bytes(patched(), wares=one_time)
    set_flag = word(finished(1), HOOKS["take ware"].offset + 1)    # PRG0's JSR SetRoomFlagUWItemState
    for cave_type, ware in product((SHOP_A, SHOP_D, POTION_SHOP, WOOD_SWORD_CAVE), range(3)):
        calls: list[int] = []
        cpu = cpu_for(rom, 1)

        def room_flag(cpu: CPU, calls: list[int] = calls) -> None:
            calls.append(cpu.x)
        cpu.stubs[set_flag] = room_flag
        cpu[OBJ_TYPE + 1] = cave_type
        cpu.x = ware
        cpu.call(hook_target(rom, HOOKS["take ware"]))
        assert calls == [ware] and cpu.x == ware
        marked = SHOP_BIT.get(cave_type, 0) & one_time[ware]
        assert [cpu[SHOP_BOUGHT_FLAGS + i] for i in range(3)] == [marked if i == ware else 0 for i in range(3)]


def test_routines_run_in_their_own_bank() -> None:
    """Each hook calls code in its own bank: the routine a hook calls lies
    in its patch's segment in that bank (a switched bank is only in while
    its own code runs)."""
    rom = patched()
    for name, hook in HOOKS.items():
        bank = bank_of(hook.offset)
        target = cpu_address_to_offset(hook_target(rom, hook), bank)
        spaces = [space for space in build.FREE_SPACE.values() if space.bank == bank]
        assert any(target in space.file_range() for space in spaces), name



def test_the_patches_share_no_byte_with_the_player_settings() -> None:
    """The progressive patches and the player-setting patches
    (asm/settings/) write different bytes, so both can go on one ROM."""
    settings = _module("player_settings_data", REPO / "asm" / "settings" / "player_settings_data.py")
    setting_bytes = {offset + i for choices in settings.SETTINGS.values() for runs in choices.values()
                     for offset, run in runs for i in range(piece_length(run))}
    progressive_bytes = {offset + i for runs in data.PATCHES.values() for offset, piece in runs
                         for i in range(piece_length(piece))}
    assert not setting_bytes & progressive_bytes
