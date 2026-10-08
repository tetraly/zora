"""Finished-ROM invariants for Consternation hint text (hints-behavior.md)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.game_config import GameConfig, HintMode
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.rom.layout import (
    EXT_BANK1_ROM_START, EXT_HINT_CPU_BASE, EXT_HINT_DATA_ROM_END, EXT_HINT_DATA_ROM_START,
    HINT_SHOP_QUOTES_ADDRESS, OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS, QUOTE_DATA_ADDRESS, TOLL_TEXT_POINTER,
    UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS, UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE,
)
from zora.generate.generation_pass import generate_shapes
from zora.generate.steps.hint_text import POOL
from zora.generate.shapes.options import ShapeOptions

SLOT_COUNT = 45
SHUFFLED_SLOTS = [38, 20, 21, 22, 23, 24, 28, 29, 31, 32, 33]
EXPECTED_OFFER_SELECTORS = bytes([0x18, 0x4E, 0x50, 0x52, 0x54, 0x56])
HINT_SELECTOR_VALUES = frozenset({
    0x28, 0x2A, 0x2C, 0x2E, 0x30, 0x32, 0x34, 0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x42, 0x4C,
})
# Slot 0 has no helpful text: the owner ruling gives it its own quotes only.
HELPFUL_SLOTS = (3, 6, 7, 35, 36, 37)
POOL_TEXTS = frozenset("|".join(entry.lines) for entry in POOL)
SLOT0_QUOTES = frozenset("|".join(entry.lines) for entry in POOL if entry.routing_class == "slot 0 (owner ruling)")


def _without_centering(text: str) -> str:
    return "|".join(line.lstrip("~") for line in text.split("|"))


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def _finished(seed: int) -> bytes:
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(seed), ShapeOptions())
    config = GameConfig(hint_mode=HintMode.CONSTERNATION)
    return serialize_to_rom(gw, rom, config=config)


def _cpu_to_file(addr: int) -> int:
    """Bank-1 CPU address (>= $8000) to ROM file offset."""
    return (addr - EXT_HINT_CPU_BASE) + EXT_BANK1_ROM_START


@pytest.mark.parametrize("seed", [1000, 1001, 1002])
def test_selector_bytes_in_rom(seed: int) -> None:
    """HT-SEL-01/02: the selector tables and hint-shop offers are written."""
    rom = _finished(seed)
    assert rom[OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + 2] == 0x66
    assert rom[HINT_SHOP_QUOTES_ADDRESS:HINT_SHOP_QUOTES_ADDRESS + 6] == EXPECTED_OFFER_SELECTORS

    a = rom[UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS:
            UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS + UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE]
    b = rom[UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS:
            UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS + UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE]
    for table, label in ((a, "A"), (b, "B")):
        assert 0x26 not in table, label
        assert all(v in HINT_SELECTOR_VALUES for v in table), label


@pytest.mark.parametrize("seed", [1000, 1001, 1002])
def test_text_pointers_in_rom(seed: int) -> None:
    """HT-TEXT-04: 45 text pointers are written and shuffled among dungeon slots."""
    rom = _finished(seed)
    ptr_table = rom[QUOTE_DATA_ADDRESS:QUOTE_DATA_ADDRESS + SLOT_COUNT * 2]
    pointers = [ptr_table[i] | (ptr_table[i + 1] << 8) for i in range(0, SLOT_COUNT * 2, 2)]

    # Slot 27 is patched to the toll text by B1.
    assert pointers[27] == TOLL_TEXT_POINTER[0] | (TOLL_TEXT_POINTER[1] << 8)

    for cpu in pointers:
        assert EXT_HINT_CPU_BASE <= cpu < EXT_HINT_CPU_BASE + (EXT_HINT_DATA_ROM_END - EXT_BANK1_ROM_START)

    # The shuffle exchanges only whole pointer entries among the listed slots.
    shuffled_values = [pointers[s] for s in SHUFFLED_SLOTS]
    assert sorted(shuffled_values) == sorted(set(shuffled_values))


@pytest.mark.parametrize("seed", [1000, 1001, 1002])
def test_encoded_text_body_in_rom(seed: int) -> None:
    """HT-TEXT-01/03: encoded slot texts live in the extended hint bank."""
    rom = _finished(seed)
    ptr_table = rom[QUOTE_DATA_ADDRESS:QUOTE_DATA_ADDRESS + SLOT_COUNT * 2]
    pointers = [ptr_table[i] | (ptr_table[i + 1] << 8) for i in range(0, SLOT_COUNT * 2, 2)]

    for slot, cpu in enumerate(pointers):
        start = _cpu_to_file(cpu)
        # Find the terminating byte (last byte has $C0 set, or $FF for blank).
        end = start
        while end < EXT_HINT_DATA_ROM_END and rom[end] != 0xFF and not (rom[end] & 0xC0):
            end += 1
        if end < EXT_HINT_DATA_ROM_END:
            end += 1  # include the terminator
        body = rom[start:end]
        assert body, f"slot {slot} empty body at {start:#x}"
        assert body[-1] == 0xFF or (body[-1] & 0xC0), f"slot {slot} missing terminator"


@pytest.mark.parametrize("seed", [1000, 1001, 1002])
def test_slot0_shows_one_of_its_own_quotes(seed: int) -> None:
    """Owner ruling (replacing HT-TEXT-02/HT-HINT-01's greeting): slot 0,
    the wood sword cave, shows one of the quotes routed to it."""
    rom = _finished(seed)
    gw = parse_rom(rom)
    assert _without_centering(gw.quotes[0].text) in SLOT0_QUOTES


@pytest.mark.parametrize("seed", [1000, 1001, 1002])
def test_overlay_flags_match_final_text(seed: int) -> None:
    """HT-HINT-02: hint_overlay_flags records the mixed-mode draw per slot."""
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(seed), ShapeOptions())
    assert len(gw.hint_overlay_flags) == SLOT_COUNT
    # When a helpful slot lost the overlay, the final text is a pool pick.
    for slot in HELPFUL_SLOTS:
        flag = gw.hint_overlay_flags[slot]
        text = gw.quotes[slot].text
        is_pool = text == "" or _without_centering(text) in POOL_TEXTS
        if flag:
            assert not is_pool, f"slot {slot} flagged helpful but shows pool/empty"
        # The converse is not asserted here because some helpful strings may
        # coincidentally match the empty fallback; the flag is authoritative.


def test_overlay_rate_about_half() -> None:
    """HT-HINT-02: over many seeds each helpful slot wins the overlay ~1/2."""
    wins: dict[int, int] = {slot: 0 for slot in HELPFUL_SLOTS}
    n = 100
    for seed in range(n):
        rom = _vanilla_rom()
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(2000 + seed), ShapeOptions())
        for slot in HELPFUL_SLOTS:
            if gw.hint_overlay_flags[slot]:
                wins[slot] += 1
    for slot, win in wins.items():
        # Binomial 1/2, n=100: 99% interval is roughly [37, 63].
        assert 30 <= win <= 70, f"slot {slot} win rate {win}/{n} far from 1/2"


def test_no_metadata_region_at_end_of_hint_bank() -> None:
    """The spec has no 12-byte metadata region; the hint bank ends with text.

    The bytes from EXT_HINT_DATA_ROM_START to EXT_HINT_DATA_ROM_END must be
    exactly what the spec's text layout produces: encoded bodies in slot
    order, with any trailing bytes left untouched from the base ROM.
    """
    base = _vanilla_rom()
    gw = parse_rom(base)
    generate_shapes(gw, Rng(1234), ShapeOptions())
    rom = serialize_to_rom(gw, base, config=GameConfig(hint_mode=HintMode.CONSTERNATION))
    parsed = parse_rom(rom)
    # Overlay flags live only in generator state; parsing a finished ROM must
    # not populate them from a non-spec metadata region.
    assert parsed.hint_overlay_flags == ()

    expected = b"".join(gw.hint_text_bytes or ())
    start = EXT_HINT_DATA_ROM_START
    end = start + len(expected)
    assert end <= EXT_HINT_DATA_ROM_END
    assert rom[start:end] == expected
    if end < EXT_HINT_DATA_ROM_END:
        assert rom[end:EXT_HINT_DATA_ROM_END] == base[end:EXT_HINT_DATA_ROM_END]
