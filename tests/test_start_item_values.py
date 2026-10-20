"""The fourteen further start items (flags-behavior.md FL-SUP-01, features-behavior.md FP-START-02 to
FP-START-04; the d8cf117 export): the Bow, the Magical Key, the Ladder, the Wand, the Book of Magic,
the wooden, white and magical swords, the wooden and silver arrows, the red candle, the blue and red
rings and the magical shield, on and Random (B58, B62, B65-B72, B74-B76, B85 = 1, 2). Each only sets
its byte of the starting table, which a new file copies into Items; its Random coin comes from the
start items' own stream; the Ladder changes which free item the cave pass under B03 counts."""
from collections import Counter
from functools import cache

import pytest

from tests.emulator import INV_BOOK, INV_MAP, ITEMS, STATUS_BAR_ROWS, Emulator
from tests.test_book_to_understand_npcs import BOOK_FLAGS, _record_text, _shown_characters
from tests.test_feature_patches import _prg0_world, vanilla
from tests.test_progressive_emulator import CAVE_MODE, Game
from zora.flags.codec import decode, encode
from zora.flags.fields import START_ITEM_FIELDS, TOGGLES_BY_ID, Settings, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support, unsupported_fields
from zora.generate import pipeline
from zora.generate.pipeline import generate_rom, resolve_question_marks
from zora.generate.rng import Rng
from zora.generate.steps.start_items import (
    START_ITEM_ORDER,
    chosen_start_items,
    resolve_start_item_coins,
    start_items,
)
from zora.generate.steps.wood_sword_behind_blocks import free_item, wood_sword_extra_screens
from zora.model.enums import Destination, Item
from zora.rom.code_patches import START_ITEMS_SIZE
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.start_items import START_ITEM_SLOTS, start_table
from zora_measure.checkpoints.overworld_quests import wood_sword_widened

ITEM_OF_FIELD = {field.id: item for field, item in START_ITEM_ORDER}
# The fourteen this export supports, each with the spec's one-field strings (FL-SUP-01 Check: CP-5
# with C17 = 0 and the field on, then at possible)
FURTHER_START_ITEMS = {
    "B58": ("BH9ZnCPHNGtHUlxY7gABM0qgIyVazJV", "MPcJVDA7jEDlrNinCLs6tafJ3LwazJV"),
    "B62": ("EK0etxAA1Fu9qC!Ch3txVzVP9TznazJV", "Sdtbxp8gcUTmsHqE44nQm8YnGPOVazJV"),
    "B65": ("68WhRUdYcOH0GhCsmbRCRB7uM0abMazJV", "CH2FB9BvaLWh!aHbMtpPP6RLgzcceazJV"),
    "B66": ("IPYnvolHYImOjTMJyBCcN1ko0xedwazJV", "ap6S8nRNSAWTv8aUk3MEGog90rkhnazJV"),
    "B67": ("tDf6Mm7TM2GZ5oofVwVrAabV0lqleazJV", "1lRJ41iAl3eVoepUAqYyhsvNY0U7xDazJV"),
    "B68": ("2dey1heE1mFl3Cq9hABQYaF9b0CQ7nazJV", "5GIuvhSNsu4TnssBE93o6hEUj!MHgVazJV"),
    "B69": ("7txrohGXj0uCXXuCm7xAfoDpszW9EDazJV", "FmuiTgi0FOMNlX!HO4aIL8BqIwzktMazJV"),
    "B70": ("NfrZ8g8TmlpYzY5M01DQ0T9qjuSLXVazJV", "lKi78eRtMtD5eYNZrs7n1T3s0ms8UwazJV"),
    "B71": ("17!Yg8clHx!bdJYfnii292SytIfGwSMazJV", "2F!6L8XgVjLmEJZXSHDmF5Sgx9IVJKeazJV"),
    "B72": ("3Nzf08SbjUhwqJaP6qkVL8SO!!wjhCwazJV", "6lyJ08DNNnlReJd05XIhdHRYBYrPpqnazJV"),
    "B74": ("UQos06Wmyv8zJJvDxND3eHLZTRGCnGnazJV", "yrcj04LjsdeWbKHelbEpEZDt7QVN0yVazJV"),
    "B75": ("1SHQa02AgmM93tKf4ZpGZpr6BmPkXFfDazJV", "2uYr8!weXTWehkLmM0ULqbhk7jNT0xkMazJV"),
    "B76": ("4LqGi!q7OAh9KbMtdS9R6NYN3gLBVepVazJV", "8hfXQ!WXxHBfEAQESm9gui6GsXELyl3wazJV"),
    "B85": ("LYzCA!kvGw3tfUE2r!HxVBfiHfx4KcRdueazJV", "h6xOL!UpP9Ii8K14PRmlrC1MZsdKDCqjEDazJV"),
}
SPEC_SEED = 7                    # FL-SUP-01 Check: seed 7 of each on string keeps exactly its item
# FP-START-04's start-Ladder run: CP-5 with B03 on, B65 on and C17 = 0
START_LADDER_FLAGS = "68WhRUdYcOH0GhCsnapdNGisrKrKXvzJV"
# The other "?" fields of the MVP, whose draws a start item's coin must not move
OTHER_POSSIBLE = ("B01", "B03", "B08", "B30", "B48", "B49", "B81", "B91")
SEEDS = range(200)


def with_flags(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C17": 0, **(options or {})},
                                                                     toggles=toggles))


def all_start_items_at(state: ThreeState) -> dict[str, ThreeState]:
    return dict.fromkeys((field.id for field in START_ITEM_FIELDS), state)


# --- support -----------------------------------------------------------------------------------

@pytest.mark.parametrize("field_id", FURTHER_START_ITEMS)
def test_the_specs_strings_are_supported(field_id: str) -> None:
    """FL-SUP-01's Check: each one-field string, on and at possible, has no unsupported field; and
    on, the seed keeps exactly that item."""
    on, possible = (decode(flags) for flags in FURTHER_START_ITEMS[field_id])
    assert unsupported_fields(on) == unsupported_fields(possible) == []
    assert on.toggle(TOGGLES_BY_ID[field_id]) is ThreeState.ON
    assert possible.toggle(TOGGLES_BY_ID[field_id]) is ThreeState.POSSIBLE
    on_flags = FURTHER_START_ITEMS[field_id][0]
    assert start_items(resolve_question_marks(on, SPEC_SEED, on_flags), SPEC_SEED, on_flags) == (
        ITEM_OF_FIELD[field_id],)


def test_every_start_item_is_supported_on_and_random() -> None:
    for state in (ThreeState.ON, ThreeState.POSSIBLE):
        settings = decode(with_flags(toggles=all_start_items_at(state)))
        assert all(support(settings)[field.id] is Support.SUPPORTED for field in START_ITEM_FIELDS)


# --- each item in the starting inventory (emulator) ---------------------------------------------

# The fourteen in three ROMs, as one slot keeps the better of two (FP-START-03): the lesser sword,
# arrow and ring with the rest, then the better ones, then the magical sword.
ITEM_GROUPS = (
    ("B68", "B71", "B75", "B58", "B62", "B65", "B66", "B67", "B74", "B85"),
    ("B69", "B72", "B76"),
    ("B70",),
)


@cache
def generated(flags: str, seed: int) -> bytes:
    return generate_rom(flags, seed, vanilla()).rom


@pytest.mark.parametrize("fields", ITEM_GROUPS, ids=["+".join(group) for group in ITEM_GROUPS])
def test_each_item_is_in_a_new_files_inventory(fields: tuple[str, ...]) -> None:
    """FP-START-03: the table holds each item's value in its slot and FP-START-01's elsewhere, in the
    ROM and in a new file's Items."""
    items = [ITEM_OF_FIELD[field_id] for field_id in fields]
    rom = generated(with_flags(toggles=dict.fromkeys(fields, ThreeState.ON)), 1)
    world = parse_rom(rom)
    expected = start_table(items, 3, 3)
    assert set(world.start_items) == set(items)
    assert world.starting_items_new_file == world.starting_items_second_quest == expected
    emu = Emulator(rom)
    emu.new_game()
    in_play = bytes(emu[ITEMS + offset] for offset in range(START_ITEMS_SIZE))
    assert in_play == expected
    for item in items:
        slot, value = START_ITEM_SLOTS[item]
        assert in_play[slot] == value


# --- Random's coin ------------------------------------------------------------------------------

def resolved(flags: str, seed: int) -> Settings:
    return resolve_question_marks(decode(flags), seed, flags)


@pytest.mark.parametrize("field_id", FURTHER_START_ITEMS)
def test_a_random_field_comes_up_both_ways(field_id: str) -> None:
    flags = with_flags(toggles={field_id: ThreeState.POSSIBLE})
    kept = Counter(ITEM_OF_FIELD[field_id] in chosen_start_items(resolved(flags, seed)) for seed in SEEDS)
    assert kept[True] > 70 and kept[False] > 70


def test_a_coin_does_not_depend_on_the_other_start_items() -> None:
    """FP-START-02: one coin per field in the fixed order whatever the field's value, so within one
    string's streams a field's outcome is the same whether the others are off, on or Random."""
    flags = with_flags()
    others_off = decode(flags)
    others_on = others_off.updated(toggles=all_start_items_at(ThreeState.ON))
    for seed in range(50):
        for field_id in FURTHER_START_ITEMS:
            random = {field_id: ThreeState.POSSIBLE}
            outcomes = {resolve_start_item_coins(settings.updated(toggles=random), seed, flags).toggle(
                TOGGLES_BY_ID[field_id]) for settings in (others_off, others_on, others_off.updated(
                    toggles={**all_start_items_at(ThreeState.POSSIBLE), **random}))}
            assert len(outcomes) == 1


class CountingRng(Rng):
    """A "?" stream that counts its draws."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.draws = 0

    def below(self, n: int) -> int:
        self.draws += 1
        return super().below(n)


def test_start_items_draw_nothing_from_the_question_mark_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """A start item at Random takes its coin from the start items' own stream: the "?" stream draws
    once for each other "?" field and never for a start item."""
    streams: list[CountingRng] = []

    def counting_stream(seed: int, flag_string: str) -> CountingRng:
        streams.append(CountingRng(seed))
        return streams[-1]

    monkeypatch.setattr(pipeline, "question_mark_rng", counting_stream)
    others = dict.fromkeys(OTHER_POSSIBLE, ThreeState.POSSIBLE)
    flags = with_flags(toggles={**others, **all_start_items_at(ThreeState.POSSIBLE)})
    for seed in range(20):
        settings = resolved(flags, seed)
        assert all(settings.toggle(field) is not ThreeState.POSSIBLE for field in START_ITEM_FIELDS)
        assert streams[-1].draws == len(OTHER_POSSIBLE)


# --- the Ladder and the cave pass (OW-CAVE-07, FP-START-04) -------------------------------------

def test_a_start_ladder_makes_the_pass_count_the_coast_item() -> None:
    """OW-CAVE-07's quirk: with a starting Ladder the Armos item is ignored, even when it is not the
    Ladder; only the coast item and the starting inventory count."""
    ladder = frozenset({Item.LADDER})
    assert free_item(int(Item.POWER_BRACELET), int(Item.RAFT)) is Item.POWER_BRACELET
    assert free_item(int(Item.POWER_BRACELET), int(Item.RAFT), ladder) is Item.RAFT
    assert free_item(int(Item.RED_CANDLE), int(Item.HEART_CONTAINER), ladder) is None
    overworld = parse_rom(vanilla()).overworld
    assert wood_sword_extra_screens(overworld, int(Item.RED_CANDLE), int(Item.HEART_CONTAINER), ladder) == frozenset()


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_start_ladder_runs_cave_stands_on_the_widened_set(seed: int) -> None:
    """FP-START-04's Check on a few seeds (all 400: temp/merge/ladder_check.py): the start table is
    FP-START-01's with the Ladder byte at 1, and code 16 stands on the widened set computed with the
    coast item as the free item."""
    world = parse_rom(generated(START_LADDER_FLAGS, seed))
    assert world.start_items == (Item.LADDER,)
    assert world.starting_items_new_file == start_table([Item.LADDER], 3, 3)
    assert wood_sword_widened(world)["on the widened set"]


# --- the Book from the first screen (B48, B49) --------------------------------------------------

def _status_bar_in_level_1(rom: bytes, level_map: bool = False, clear_book: bool = False) -> bytes:
    emu = Emulator(rom)
    emu.new_game()
    if clear_book:
        emu[INV_BOOK] = 0
    emu[INV_MAP] = 1 if level_map else 0                  # level 1's map bit
    emu.walk_into_level_1()
    return emu.nametable(*STATUS_BAR_ROWS)


def test_a_start_book_counts_as_the_level_map() -> None:
    """The Book counts as the map of every level (B49, FP-BOOK-01) for a start Book: a new file holds
    it, and level 1 shows the map as with level 1's map; without it, none (PRG0's level 1, on PRG0's
    overworld, which walk_into_level_1 needs)."""
    world = _prg0_world()
    world.start_items = (Item.BOOK,)
    rom = serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=True, book_is_an_atlas=True))
    start_book = _status_bar_in_level_1(rom)
    assert start_book == _status_bar_in_level_1(rom, level_map=True, clear_book=True)
    assert start_book != _status_bar_in_level_1(rom, clear_book=True)


def test_a_start_book_lets_the_player_understand_people() -> None:
    """Book to Understand NPCs (B48, HT-BOOK-01) with a start Book: from a new file, the white-sword
    cave's person shows its own text, not text 0."""
    flags = encode(decode(BOOK_FLAGS).updated(options={"C17": 0}, toggles={"B67": ThreeState.ON}))
    rom = generated(flags, 0)
    assert parse_rom(rom).start_items == (Item.BOOK,)
    screen = next(screen.screen_num for screen in parse_rom(rom).overworld.screens
                  if screen.destination == Destination.WHITE_SWORD_CAVE)
    game = Game(rom)
    assert game.emu[INV_BOOK] == 1                         # from the table, nothing taken
    game.go_to_screen(screen)
    game.start_mode(CAVE_MODE)
    selector, shown = _record_text(game.emu)
    assert selector != 0
    assert shown == _shown_characters(rom, selector) != _shown_characters(rom, 0)
