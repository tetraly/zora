"""The hint texts' overflow region (zora/rom/layout.py hint_text_regions; docs/rom-map.md, bank 1's
free-space row) is free for them: PRG0's PersonText block after the pointer table, up to the
refusal text (0x0405C-0x04545 for 38 pointers, 0x0406A-0x04545 for Consternation's 45). Nothing
else may use it:
- z1rr-coop reserves none of it (tests/test_coop_reserved.py's table);
- no code patch, ZORA flag patch, ASNB patch, player setting or fixed site writes there (the level
  word rewrites hint lines in place: it is the hint text's own setting);
- the two texts outside the hint block, slot 27's toll text and slot 34's refusal text, lie
  outside it, and in a finished ROM every other PersonTextAddrs entry points at a hint text in the
  extended bank or this region, so no PRG0 text there is still read."""
from functools import cache

import pytest

from tests.test_coop_reserved import RESERVED, hits, written
from zora.rom.asnb_patch_data import PATCHES as ASNB_PATCHES
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patch_data import PATCHES as SERIES_PATCHES
from zora.rom.flags2_patch_data import PATCHES as FLAG_PATCHES
from zora.rom.layout import (
    CONSTERNATION_HINT_SLOTS,
    EXT_HINT_DATA_ROM_END,
    EXT_HINT_DATA_ROM_START,
    HINT_SHOP_QUOTES_ADDRESS,
    NUM_QUOTES,
    OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS,
    OVERWORLD_WIZZROBE_PATCH,
    QUOTE_DATA_ADDRESS,
    REFUSAL_TEXT_ADDRESS,
    REFUSAL_TEXT_POINTER_ADDRESS,
    REFUSAL_TEXT_SIZE,
    TITLE_ROW_LENGTH,
    TITLE_SEED_ROW_ADDRESS,
    TITLE_VERSION_ROW_ADDRESS,
    TOLL_TEXT_ADDRESS,
    TOLL_TEXT_POINTER_ADDRESS,
    TOLL_TEXT_SIZE,
    UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE,
    cpu_address_in_bank1,
    hint_text_regions,
)
from zora.rom.player_settings import written_offsets
from zora.rom.slot_identity import SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_SIZE

POINTER_SIZE = 2
WHITE_SWORD_SELECTOR_INDEX = 2       # the overworld selector the white-sword cave's text uses
HINT_SHOP_SELECTORS = 6              # two hint shops, three offers each
TOLL_SLOT, REFUSAL_SLOT = 27, 34
# Every pointer count a mode writes: PRG0's 38 (the vanilla hint bank) and Consternation's 45
POINTER_COUNTS = (NUM_QUOTES, CONSTERNATION_HINT_SLOTS)


def overflow_region(pointer_count: int) -> range:
    start, end = hint_text_regions(pointer_count)[1]
    return range(start, end)


EVERY_OVERFLOW_BYTE = {offset for count in POINTER_COUNTS for offset in overflow_region(count)}


def test_the_region_is_the_persontext_block_after_the_pointer_table() -> None:
    for count in POINTER_COUNTS:
        region = overflow_region(count)
        assert region.start == QUOTE_DATA_ADDRESS + POINTER_SIZE * count and region.stop == REFUSAL_TEXT_ADDRESS
    assert overflow_region(CONSTERNATION_HINT_SLOTS) == range(0x0406A, 0x04546)
    assert overflow_region(NUM_QUOTES) == range(0x0405C, 0x04546)


def test_z1rr_coop_reserves_none_of_it() -> None:
    assert RESERVED and not hits(EVERY_OVERFLOW_BYTE)
    assert not any(EVERY_OVERFLOW_BYTE & set(area.file_range()) for area in RESERVED)


@pytest.mark.parametrize(("family", "patches"), [("series", SERIES_PATCHES), ("ZORA flag", FLAG_PATCHES),
                                                  ("ASNB", ASNB_PATCHES)])
def test_no_patch_writes_there(family: str, patches: dict[str, tuple]) -> None:
    for name, pieces in patches.items():
        assert not written(pieces) & EVERY_OVERFLOW_BYTE, f"{family} patch {name}"


@pytest.mark.parametrize("setting", ["select_swap", "low_health_beep", "death_warp", "reduce_flashing",
                                     "tunic_colours", "heart_colour", "music", "boss_sound_word"])
def test_no_player_setting_writes_there(setting: str) -> None:
    """The level word (not listed) rewrites hint lines in place, in both regions: the hints'
    own text, which keeps its length and pointer."""
    assert not written_offsets(setting) & EVERY_OVERFLOW_BYTE, setting


def test_no_fixed_site_lies_there() -> None:
    sites = {
        "toll text": range(TOLL_TEXT_ADDRESS, TOLL_TEXT_ADDRESS + TOLL_TEXT_SIZE),
        "refusal text": range(REFUSAL_TEXT_ADDRESS, REFUSAL_TEXT_ADDRESS + REFUSAL_TEXT_SIZE),
        "toll pointer": range(TOLL_TEXT_POINTER_ADDRESS, TOLL_TEXT_POINTER_ADDRESS + POINTER_SIZE),
        "refusal pointer": range(REFUSAL_TEXT_POINTER_ADDRESS, REFUSAL_TEXT_POINTER_ADDRESS + POINTER_SIZE),
        # the selector writes of zora/rom/serialize/text.py (HT-SEL-01/02)
        "white-sword selector": range(OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + WHITE_SWORD_SELECTOR_INDEX,
                                      OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + WHITE_SWORD_SELECTOR_INDEX + 1),
        "hint-shop selectors": range(HINT_SHOP_QUOTES_ADDRESS, HINT_SHOP_QUOTES_ADDRESS + HINT_SHOP_SELECTORS),
        **{f"underworld selectors {name}": range(address, address + UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE)
           for name, address in (("A", UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS),
                                 ("B", UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS))},
        "extended hint bank": range(EXT_HINT_DATA_ROM_START, EXT_HINT_DATA_ROM_END),
        "slot identity": range(SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE),
        "title seed row": range(TITLE_SEED_ROW_ADDRESS, TITLE_SEED_ROW_ADDRESS + TITLE_ROW_LENGTH),
        "title version row": range(TITLE_VERSION_ROW_ADDRESS, TITLE_VERSION_ROW_ADDRESS + TITLE_ROW_LENGTH),
    }
    for name, site in sites.items():
        assert not set(site) & EVERY_OVERFLOW_BYTE, name
    assert not written(OVERWORLD_WIZZROBE_PATCH) & EVERY_OVERFLOW_BYTE


@cache
def _finished_pointers(seed: int) -> tuple[int, ...]:
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom.parse.rom_file import parse_rom
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, remember_repo_base_rom()).rom)
    assert world.hint_pointers is not None
    return world.hint_pointers


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_hint_pointer_points_at_a_hint_text(seed: int) -> None:
    """No PRG0 text in the region is still read: every pointer but the toll's and the
    refusal's points into the extended bank or the overflow region."""
    bank = range(cpu_address_in_bank1(EXT_HINT_DATA_ROM_START), cpu_address_in_bank1(EXT_HINT_DATA_ROM_END))
    region = overflow_region(CONSTERNATION_HINT_SLOTS)
    overflow = range(cpu_address_in_bank1(region.start), cpu_address_in_bank1(region.stop))
    for slot, pointer in enumerate(_finished_pointers(seed)):
        if slot in (TOLL_SLOT, REFUSAL_SLOT):
            continue
        assert pointer in bank or pointer in overflow, (slot, hex(pointer))
