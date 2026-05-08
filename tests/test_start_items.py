"""Tests for the Start Items generator and ROM patcher.

Patcher correctness is verified byte-for-byte against the reference
randomizer's ROMs in analysis/roms/. Generator correctness is verified
via the standard determinism / dedup / cap properties.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flags.flags_generated import (
    Flags,
    MaxStartItems,
    StartHearts,
    StartTriforce,
    Tristate,
)
from zora.data_model import Item
from zora.game_config import GameConfig
from zora.patches.start_items import (
    ASM_STUB_LOAD_SAVE,
    ASM_STUB_NEW_SAVE,
    HOOK_LOAD_SAVE_OFFSET,
    HOOK_NEW_SAVE_OFFSET,
    INVENTORY_TABLE_OFFSET,
    StartItemsPatch,
    _build_inventory_table,
    _encode_hearts,
)
from zora.rng import SeededRng
from zora.start_item_generator import StartItemResult, generate_start_items


REF_ROMS = Path(__file__).parent.parent / "analysis" / "roms"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def test_generator_default_flags_grants_nothing() -> None:
    flags = Flags()
    rng = SeededRng(42)
    result = generate_start_items(flags, rng)
    assert result.items == ()
    assert result.start_hearts == 3
    assert result.triforce_mask == 0
    assert result.bombs_granted is False


def test_generator_is_deterministic() -> None:
    flags = Flags(
        start_wood_sword=Tristate.ON,
        start_bow=Tristate.ON,
        start_recorder=Tristate.RANDOM,
        start_triforce=StartTriforce.RANDOM,
    )
    a = generate_start_items(flags, SeededRng(123))
    b = generate_start_items(flags, SeededRng(123))
    assert a == b


def test_generator_dedups_sword_tiers() -> None:
    flags = Flags(
        start_wood_sword=Tristate.ON,
        start_white_sword=Tristate.ON,
        start_magical_sword=Tristate.ON,
    )
    result = generate_start_items(flags, SeededRng(0))
    swords = [i for i in result.items
              if i in (Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD)]
    assert swords == [Item.MAGICAL_SWORD], "only highest sword tier should be kept"


def test_generator_dedups_ring_tiers() -> None:
    flags = Flags(start_blue_ring=Tristate.ON, start_red_ring=Tristate.ON)
    result = generate_start_items(flags, SeededRng(0))
    rings = [i for i in result.items if i in (Item.BLUE_RING, Item.RED_RING)]
    assert rings == [Item.RED_RING]


def test_generator_max_start_items_cap() -> None:
    flags = Flags(
        start_wood_sword=Tristate.ON,
        start_bow=Tristate.ON,
        start_recorder=Tristate.ON,
        start_raft=Tristate.ON,
        start_book=Tristate.ON,
        max_start_items=MaxStartItems.N_2,
    )
    result = generate_start_items(flags, SeededRng(7))
    assert len(result.items) == 2


def test_generator_max_start_items_all_keeps_everything() -> None:
    flags = Flags(
        start_wood_sword=Tristate.ON,
        start_bow=Tristate.ON,
        start_recorder=Tristate.ON,
        max_start_items=MaxStartItems.ALL,
    )
    result = generate_start_items(flags, SeededRng(0))
    assert set(result.items) == {Item.WOOD_SWORD, Item.BOW, Item.RECORDER}


def test_generator_bombs_separated_from_items() -> None:
    flags = Flags(start_bombs=Tristate.ON, start_bow=Tristate.ON)
    result = generate_start_items(flags, SeededRng(0))
    assert Item.BOMBS not in result.items
    assert Item.BOW in result.items
    assert result.bombs_granted is True


def test_generator_triforce_count_matches_mask() -> None:
    flags = Flags(start_triforce=StartTriforce.T_5)
    result = generate_start_items(flags, SeededRng(0))
    assert bin(result.triforce_mask).count("1") == 5


# ---------------------------------------------------------------------------
# Hearts encoding (formula confirmed against reference ROMs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hearts,expected", [
    (1,  0x00),
    (3,  0x22),   # vanilla
    (6,  0x52),
    (8,  0x72),
    (16, 0xF2),
])
def test_encode_hearts_matches_reference(hearts: int, expected: int) -> None:
    assert _encode_hearts(hearts) == expected


# ---------------------------------------------------------------------------
# Inventory table — slot map & vanilla bytes
# ---------------------------------------------------------------------------


def test_inventory_table_default_is_vanilla_layout() -> None:
    cfg = GameConfig(start_items=StartItemResult())
    table = _build_inventory_table(cfg)
    assert len(table) == 40
    assert table[24] == 0x22                  # 3 hearts/3 containers
    assert table[25] == 0xFF                  # HeartPartial — full first heart
    assert table[26] == 0x00                  # no triforce
    assert table[37] == 0x08                  # MaxBombs always = 8
    assert table[1] == 0x00                   # no bombs in pocket
    # All other slots are zero.
    nonzero = {i for i, b in enumerate(table) if b != 0}
    assert nonzero == {24, 25, 37}


def test_inventory_table_slots_for_each_item() -> None:
    """Every Item-to-slot mapping puts the byte where Variables.inc says."""
    cases = [
        (Item.WOOD_SWORD,        0,  1),
        (Item.WHITE_SWORD,       0,  2),
        (Item.MAGICAL_SWORD,     0,  3),
        (Item.WOOD_ARROWS,       2,  1),
        (Item.SILVER_ARROWS,     2,  2),
        (Item.BOW,               3,  1),
        (Item.BLUE_CANDLE,       4,  1),
        (Item.RED_CANDLE,        4,  2),
        (Item.RECORDER,          5,  1),
        (Item.BAIT,              6,  1),
        (Item.WAND,              8,  1),
        (Item.RAFT,              9,  1),
        (Item.BOOK,              10, 1),
        (Item.BLUE_RING,         11, 1),
        (Item.RED_RING,          11, 2),
        (Item.LADDER,            12, 1),
        (Item.MAGICAL_KEY,       13, 1),
        (Item.POWER_BRACELET,    14, 1),
        (Item.LETTER,            15, 1),
        (Item.WOOD_BOOMERANG,    29, 1),
        (Item.MAGICAL_BOOMERANG, 30, 1),
        (Item.MAGICAL_SHIELD,    31, 1),
    ]
    for item, slot, expected in cases:
        cfg = GameConfig(start_items=StartItemResult(items=(item,)))
        table = _build_inventory_table(cfg)
        assert table[slot] == expected, f"{item.name} should set slot {slot}={expected}, got {table[slot]}"


# ---------------------------------------------------------------------------
# End-to-end byte-exact comparison against reference randomizer ROMs.
# ---------------------------------------------------------------------------


_OFFSETS = [
    HOOK_NEW_SAVE_OFFSET,
    ASM_STUB_NEW_SAVE,
    INVENTORY_TABLE_OFFSET,
    ASM_STUB_LOAD_SAVE,
    HOOK_LOAD_SAVE_OFFSET,
]


# (rom_filename, expected_StartItemResult)
_REFERENCE_CASES: list[tuple[str, StartItemResult]] = [
    ("base_101_8m6YW18uL.nes",
     StartItemResult()),
    ("base_539179633954_7txrf!RTXNTBE064cxe7gKz28zBFqk5snL.nes",
     StartItemResult(items=(Item.WHITE_SWORD,), start_hearts=6, triforce_mask=0x86)),
    ("base_1_1bD6gR6qd8d4LEXu9g6HMo7WRt2N18uL.nes",
     StartItemResult(items=(Item.RECORDER,))),
    ("base_1_IPYfDzh5usl5BgEAmt9cumwM8gCcN18uL.nes",
     StartItemResult(items=(Item.WAND,))),
    ("base_1_XPNE92HY2t1S4rIjE25nbibfMio18uL.nes",
     StartItemResult(bombs_granted=True)),
    ("base_1_D2Uo8!4GgJVWhjA2Uy0lOzfiQZge9PHo18uL.nes",
     StartItemResult(items=(Item.WOOD_BOOMERANG,))),
    ("base_1_LYzCA!kv8EEpTqo1YSUpM0MfIChFtkABt518uL.nes",
     StartItemResult(items=(Item.MAGICAL_SHIELD,))),
    ("base_1_4G1086pg.nes",
     StartItemResult(start_hearts=1)),
    ("base_1_UVjtHFE50.nes",
     StartItemResult(start_hearts=8)),
    ("base_1_12I80IoMNg.nes",
     StartItemResult(start_hearts=16)),
]


@pytest.mark.parametrize("rom_filename,expected_start_items",
                         _REFERENCE_CASES,
                         ids=[c[0] for c in _REFERENCE_CASES])
def test_patcher_matches_reference_rom(
    rom_filename: str, expected_start_items: StartItemResult,
) -> None:
    rom_path = REF_ROMS / rom_filename
    if not rom_path.exists():
        pytest.skip(f"reference ROM not present: {rom_filename}")
    rom = rom_path.read_bytes()

    cfg = GameConfig(start_items=expected_start_items)
    edits = StartItemsPatch().get_edits_for_config(cfg)
    by_offset = {e.offset: e.new_bytes for e in edits}

    for off in _OFFSETS:
        ours = by_offset[off]
        theirs = rom[off:off + len(ours)]
        assert ours == theirs, (
            f"@0x{off:05X}: ours={ours.hex(' ')} theirs={theirs.hex(' ')}"
        )
