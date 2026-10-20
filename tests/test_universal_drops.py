"""Allow Universal Drops In Shapes (B91 on and possible; shapes-behavior.md SH-ROOM-16, SH-STAIR-08,
FL-DEP-04). The merged T5 list, the staircase key's first match, the flags, the plan and the page
run without the ROM; the finished-ROM checks at the end need the base ROM. The corpus figures come
from `python3 scripts/compare_corpus.py --set b91` (and b91-possible)."""
from collections import Counter
from functools import cache

import pytest

from zora import archipelago
from zora.archipelago import OptionsConflict, flag_strings
from zora.flags import form as flag_form
from zora.flags.codec import decode, encode
from zora.flags.fields import UNIVERSAL_DROPS_IN_SHAPES, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support, unsupported_fields
from zora.generate.pipeline import generate_rom, plan
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.stairs import _key_slot
from zora.generate.shapes.t5_positions import T5_BASE, T5_UNIVERSAL, first_item_slot, item_slots_for, t5_row
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.universal_drops import (
    UNIVERSAL_DROPS_FLAGS,
    UNIVERSAL_DROPS_POSSIBLE_FLAGS,
    positions_in_rows,
    rooms_without_base_row,
)

needs_rom = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")
# SH-ROOM-16: the screen types with no base row, which get their universal row
WITHOUT_BASE_ROW = (0x01, 0x07, 0x0B, 0x10, 0x1A, 0x22, 0x27)
# A level's four standard positions (T6's format: packed $XY screen positions)
LEVEL_POSITIONS = [0x89, 0x2C, 0xD6, 0x26]          # 137, 44, 214, 38


# --- the merged list (SH-ROOM-16) -------------------------------------------------------------------

def test_the_merged_row_is_the_base_row_then_the_new_universal_positions() -> None:
    for screen_type in set(T5_BASE) | set(T5_UNIVERSAL):
        base = T5_BASE.get(screen_type, ())
        merged = t5_row(screen_type, universal_drops=True)
        assert merged[:len(base)] == base
        added = merged[len(base):]
        assert added == tuple(position for position in T5_UNIVERSAL.get(screen_type, ()) if position not in base)
        assert len(set(merged)) == len(merged)
        assert t5_row(screen_type, universal_drops=False) == base


def test_seven_screen_types_get_only_their_universal_row() -> None:
    assert tuple(sorted(set(T5_UNIVERSAL) - set(T5_BASE))) == WITHOUT_BASE_ROW
    for screen_type in WITHOUT_BASE_ROW:
        assert t5_row(screen_type, universal_drops=False) == ()
        assert t5_row(screen_type, universal_drops=True) == T5_UNIVERSAL[screen_type]
        assert item_slots_for(screen_type, LEVEL_POSITIONS, universal_drops=False) == ()


def test_the_random_rooms_read_the_merged_row() -> None:
    """SH-ROOM-16 item 1: a room keeps an item when a standard position is in the merged row."""
    # $08's base row is $89 only; its universal row adds $2C, $26 and $D6 (among others)
    assert item_slots_for(0x08, LEVEL_POSITIONS, universal_drops=False) == (0,)
    assert item_slots_for(0x08, LEVEL_POSITIONS, universal_drops=True) == (0, 1, 2, 3)
    for screen_type in set(T5_BASE) | set(T5_UNIVERSAL):
        with_b91 = set(item_slots_for(screen_type, LEVEL_POSITIONS, universal_drops=True))
        assert set(item_slots_for(screen_type, LEVEL_POSITIONS, universal_drops=False)) <= with_b91


def test_the_key_is_the_first_match_and_base_positions_win() -> None:
    """SH-ROOM-16 item 3 and SH-STAIR-08: the row's positions in order, and for each the level's
    standard positions 0 to 3; a base position beats every universal one."""
    # $1C's base row is $D6 alone (slot 2 here); the universal row starts with $2C (slot 1)
    assert t5_row(0x1C, universal_drops=True)[0] == 0xD6
    assert first_item_slot(0x1C, LEVEL_POSITIONS, universal_drops=True) == 2
    # $1A has no base row: its universal row's first match, $2C before $26
    assert first_item_slot(0x1A, LEVEL_POSITIONS, universal_drops=True) == 1
    # nothing matches: no key position
    assert first_item_slot(0x1A, [0x00, 0x01, 0x02, 0x03], universal_drops=True) is None


def test_the_stair_key_takes_the_first_match() -> None:
    """SH-STAIR-08 and SH-ROOM-16 item 3 (owner ruling, 2026-10-15: with B91 off too): the row's
    positions in order, each against the level's four standard positions in order, with no draw
    (_key_slot takes no number generator)."""
    # $00's base row is 135, 137, 153, 172: 135 comes first though the table lists 137 first
    assert _key_slot(0x00, [137, 135, 0x22, 0x33], ShapeOptions()) == 1
    assert _key_slot(0x1C, LEVEL_POSITIONS, ShapeOptions(universal_drops=True)) == 2


# --- the flag string, the support matrix and the plan ------------------------------------------------

@pytest.mark.parametrize("flags, state", [(UNIVERSAL_DROPS_FLAGS, ThreeState.ON),
                                          (UNIVERSAL_DROPS_POSSIBLE_FLAGS, ThreeState.POSSIBLE)])
def test_the_corpus_strings_are_cp5_with_only_b91_changed(flags: str, state: ThreeState) -> None:
    settings = decode(flags)
    assert settings == decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={UNIVERSAL_DROPS_IN_SHAPES: state})
    assert encode(settings) == flags
    assert support(settings)[UNIVERSAL_DROPS_IN_SHAPES.id] is Support.SUPPORTED
    assert unsupported_fields(settings) == []


def test_every_b91_value_is_supported() -> None:
    assert set(flag_form.supported_values(UNIVERSAL_DROPS_IN_SHAPES)) == set(ThreeState)


def test_the_plan_turns_the_merged_list_on() -> None:
    assert plan(UNIVERSAL_DROPS_FLAGS, 1).shape_options.universal_drops
    assert not plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1).shape_options.universal_drops


def test_possible_is_a_coin_per_seed() -> None:
    """FL-DEP-04: B91 at 2 is on or off with equal chance per seed, the same for one seed."""
    sides = Counter(plan(UNIVERSAL_DROPS_POSSIBLE_FLAGS, seed).shape_options.universal_drops for seed in range(1, 301))
    assert 110 < sides[True] < 190, sides
    assert all(plan(UNIVERSAL_DROPS_POSSIBLE_FLAGS, seed).shape_options.universal_drops
               is plan(UNIVERSAL_DROPS_POSSIBLE_FLAGS, seed).shape_options.universal_drops for seed in range(1, 6))


# --- the page and Archipelago ----------------------------------------------------------------------

@pytest.mark.parametrize("flags", [UNIVERSAL_DROPS_FLAGS, UNIVERSAL_DROPS_POSSIBLE_FLAGS])
def test_the_page_offers_on_and_random(flags: str) -> None:
    state = flag_form.form_state(flags)
    assert not state["fields"][UNIVERSAL_DROPS_IN_SHAPES.id]["problem"]
    assert state["generateRefusals"] == []


@pytest.mark.parametrize("state", [ThreeState.ON, ThreeState.POSSIBLE])
def test_archipelago_offers_on_and_random(state: ThreeState) -> None:
    """On and Random passed their logic scan (2026-10-16) and are offered."""
    assert state not in archipelago.HELD_BACK.get(UNIVERSAL_DROPS_IN_SHAPES.id, frozenset())
    flags, _zora = flag_strings({UNIVERSAL_DROPS_IN_SHAPES.id: int(state)})
    assert decode(flags).toggle(UNIVERSAL_DROPS_IN_SHAPES.id) == state


# --- finished ROMs (need the base ROM) --------------------------------------------------------------

@cache
def _finished(flags: str, seed: int) -> GameWorld:
    return parse_rom(generate_rom(flags, seed, remember_repo_base_rom()).rom)


@needs_rom
def test_finished_roms_seat_items_on_the_merged_rows() -> None:
    """SH-ROOM-16's Check: with B91 on, item rooms on screen types without a base row occur (867
    of 1,000 corpus ROMs have one), and almost every item room's position is in the merged row."""
    seeds = range(1, 7)
    assert sum(rooms_without_base_row(_finished(UNIVERSAL_DROPS_FLAGS, seed)) for seed in seeds) > 0
    for seed in seeds:
        merged, base, total = positions_in_rows(_finished(UNIVERSAL_DROPS_FLAGS, seed))
        assert merged >= base and merged >= 0.95 * total
    assert rooms_without_base_row(_finished(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)) == 0
