"""Starting items (features-behavior.md FP-START-02 to FP-START-05; zora/generate/steps/start_items.py,
zora/rom/start_items.py): the chosen items in the fixed order, the limit's uniform draw, the
starting table each item set and start hearts make, and generated seeds: the table in both starts
and a new file, the patch only with start items, the hearts in the table, the limit and Random."""
from collections import Counter
from functools import cache
from itertools import combinations

import pytest

from tests.emulator import ITEMS, Emulator
from tests.test_feature_patches import vanilla
from zora.flags.codec import decode, encode
from zora.flags.fields import START_ITEM_FIELDS, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, resolve_question_marks
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.start_items import START_ITEM_ORDER, chosen_start_items, keep_at_most, start_items
from zora.model.enums import Item
from zora.rom.base_rom import original_bytes
from zora.rom.code_patches import PRG0_START_ITEMS, START_ITEMS_SIZE, start_items_writes
from zora.rom.parse.rom_file import parse_rom
from zora.rom.start_items import HEART_VALUES_INDEX, START_ITEM_SLOTS, items_in_table, start_table
from zora_measure.checkpoints.start_items import HOPLA_FLAGS, HOPLA_ITEMS, START_ITEMS_ALL_FLAGS

THREE = (Item.RECORDER, Item.RAFT, Item.POWER_BRACELET)       # Hopla's, in the fixed order
DRAWS = 3000


def test_the_fixed_order_names_every_start_item_field_once() -> None:
    assert sorted(field.id for field, _ in START_ITEM_ORDER) == sorted(field.id for field in START_ITEM_FIELDS)
    assert {item for _, item in START_ITEM_ORDER} == set(START_ITEM_SLOTS)


def test_the_chosen_items_follow_the_fixed_order() -> None:
    settings = decode(START_ITEMS_ALL_FLAGS)
    assert chosen_start_items(settings) == THREE
    assert start_items(settings, 7, START_ITEMS_ALL_FLAGS) == THREE      # Max Start Items: All


def test_no_draw_unless_items_are_dropped() -> None:
    nothing = ScriptedRng([])
    assert keep_at_most(THREE, None, nothing) == THREE
    assert keep_at_most(THREE, 3, nothing) == THREE
    assert keep_at_most(THREE, 0, nothing) == ()
    assert keep_at_most((), 1, nothing) == ()


@pytest.mark.parametrize("limit", [1, 2])
def test_every_set_of_the_limit_is_equally_likely(limit: int) -> None:
    """Over DRAWS seeds, each of the C(3, limit) sets comes up within 5 standard deviations of its
    share, and every kept set keeps the fixed order."""
    counts = Counter(keep_at_most(THREE, limit, Rng(seed)) for seed in range(DRAWS))
    sets = list(combinations(THREE, limit))
    assert set(counts) == set(sets)
    share = DRAWS / len(sets)
    spread = (DRAWS * (1 / len(sets)) * (1 - 1 / len(sets))) ** 0.5
    assert all(abs(counts[kept] - share) < 5 * spread for kept in sets), counts


def test_hoplas_seeds_keep_one_of_three() -> None:
    settings = decode(HOPLA_FLAGS)
    kept = Counter(start_items(settings, seed, HOPLA_FLAGS) for seed in range(300))
    assert set(kept) == {(item,) for item in HOPLA_ITEMS}


def test_a_random_field_is_off_or_on() -> None:
    """Start Raft: Random (B57 = 2) resolved by its coin (FL-DEP-04) is either way a valid choice."""
    flags = encode(decode(START_ITEMS_ALL_FLAGS).updated(toggles={"B57": ThreeState.POSSIBLE}))
    rafts = Counter(Item.RAFT in chosen_start_items(resolve_question_marks(decode(flags), seed, flags))
                    for seed in range(200))
    assert rafts[True] > 60 and rafts[False] > 60


def test_the_table_keeps_the_better_of_two() -> None:
    table = start_table([Item.WHITE_SWORD, Item.WOOD_SWORD, Item.RED_CANDLE, Item.BLUE_CANDLE, Item.BOMBS], 3, 3)
    assert (table[0], table[1], table[4]) == (2, 8, 2)
    assert items_in_table(table) == (Item.WHITE_SWORD, Item.BOMBS, Item.RED_CANDLE)
    assert start_table(items_in_table(table), 3, 3) == table


def test_no_item_and_three_hearts_is_prg0s_table() -> None:
    assert start_table([], 3, 3) == PRG0_START_ITEMS
    assert items_in_table(PRG0_START_ITEMS) == ()


def test_each_item_raises_only_its_slot_and_the_hearts_follow_c16() -> None:
    for item, (slot, value) in START_ITEM_SLOTS.items():
        table = start_table([item], 4, 3)
        expected = bytearray(PRG0_START_ITEMS)
        expected[slot], expected[HEART_VALUES_INDEX] = value, 0x32
        assert table == bytes(expected), item
        assert items_in_table(table) == (item,)


# --- generated seeds ----------------------------------------------------------------------------

def with_flags(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options=options, toggles=toggles))


@cache
def generated(flags: str, seed: int) -> bytes:
    return generate_rom(flags, seed, vanilla()).rom


def test_without_start_items_the_starting_routines_are_prg0s() -> None:
    """Max Start Items: All (C17 = 0) with no start item chosen keeps no item: the patch is not
    written, the second-quest switch too keeps PRG0's routine."""
    rom = generated(with_flags(options={"C17": 0}), 1)
    assert all(rom[offset:offset + len(data)] == original_bytes(offset, len(data))
               for offset, data in start_items_writes(PRG0_START_ITEMS))
    assert parse_rom(rom).start_items == ()


@pytest.mark.parametrize("seed", [1, 2])
def test_a_seed_starts_with_its_items(seed: int) -> None:
    """The start-items-all string: the three items in the table of both starts, and in a new file."""
    rom = generated(START_ITEMS_ALL_FLAGS, seed)
    world = parse_rom(rom)
    expected = start_table(THREE, 3, 3)
    assert set(world.start_items) == set(THREE)
    assert world.starting_items_new_file == world.starting_items_second_quest == expected
    emu = Emulator(rom)
    emu.new_game()
    assert bytes(emu[ITEMS + i] for i in range(START_ITEMS_SIZE)) == expected


def test_four_hearts_go_in_the_table() -> None:
    """Starting Hearts 4 (C16 = 3) with a start item: the hearts byte is $32 in the table, and the
    hooks replace PRG0's routines (no operand is written beside them)."""
    flags = with_flags(options={"C16": 3, "C17": 0}, toggles={"B57": ThreeState.ON})
    world = parse_rom(generated(flags, 1))
    assert world.start_items == (Item.RAFT,)
    assert world.starting_items_new_file == start_table([Item.RAFT], 4, 3)
    assert (world.new_file_heart_containers, world.new_file_full_hearts) == (4, 3)


def test_hoplas_limit_keeps_one() -> None:
    """Max Start Items: 1 (C17 = 2) with Hopla's three: each seed starts with exactly one."""
    flags = with_flags(options={"C17": 2},
                       toggles=dict.fromkeys(("B57", "B60", "B64"), ThreeState.ON))
    kept = {parse_rom(generated(flags, seed)).start_items for seed in range(6)}
    assert kept <= {(item,) for item in THREE} and len(kept) > 1


def test_a_random_start_item_is_generated() -> None:
    """Start Raft: Random (B57 = 2) is supported: over a few seeds it comes up both ways."""
    flags = with_flags(options={"C17": 0}, toggles={"B57": ThreeState.POSSIBLE})
    assert {parse_rom(generated(flags, seed)).start_items for seed in range(8)} == {(), (Item.RAFT,)}
