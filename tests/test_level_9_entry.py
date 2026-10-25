"""Level 9 Entry (C08; features-behavior.md FP-TRIF-01 to FP-TRIF-06, the 2026-10-22 export): what
level 9's entrance asks for, the bytes and text that say so, and the acceptance walk and
Archipelago's logic model that judge by it.

  - C08 = 0 to 7 ask for 8 down to 1 pieces, C08 = 8 for nothing, with no draw; C08 = 9 draws the
    count from Triforce Range, C08 = 10 a count and that many levels, C08 = 11 an item (never the
    letter, nor the sword under Swordless: owner ruling 2026-10-22), each pass anew; C08 = 12 is
    resolved once per seed to 0, 8, 9, 10 or 11 (FL-DEP-04).
  - The bytes: none for eight pieces (PRG0's check); the call and a counting routine, the open
    comparison, the mask test, or the item's load and zero test (zora/rom/level_9_entrance.py).
  - The text names the count, the levels or the item; no hint does.
  - The acceptance walk opens level 9 after that many of levels 1 to 8, the chosen ones, or from
    the start; under an item, level 9's needs and E1's target hold the item (owner ruling).
  - Archipelago's logic model agrees with the acceptance check on generated seeds.
  - Level 9 Entrance = Level 4 sword (ZORA) needs Level 9 Entry at 8 triforces.
The page's locks: tests/test_flag_form.py.
Link meeting the entrance person: tests/test_level_9_entry_emulator.py."""
from collections import Counter
from dataclasses import replace
from functools import cache
from itertools import combinations

import pytest

from tests.needs import needs_base_rom
from tests.test_assignment import identity
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import Level9Requirement, ThreeState, WoodenSwordState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.acceptance_check import (
    DEFAULT_RULES,
    LEVEL9_ENTRY,
    LEVEL9_ITEM,
    AcceptanceCheck,
    acceptance_check,
)
from zora.generate.logic import LEVEL9_ENTRY_EVENT, EventTerm, logic_model, sweep, triforce_event
from zora.generate.pipeline import Built, FlagsRefused, build, finish, generate_rom, plan, shipped_logic_rules
from zora.generate.rng import Rng
from zora.generate.steps.level_9_entry import (
    Level9Entry,
    draw_level_9_gate,
    gate_items,
    refusal_text,
)
from zora.model.enums import Item
from zora.model.level_9_gate import (
    EIGHT_PIECES,
    GATE_ITEM_WORDS,
    GATE_ITEMS,
    OPEN_GATE,
    TRIFORCE_LEVELS,
    GateKind,
    item_gate,
    levels_gate,
    pieces_gate,
)
from zora.rom import level_9_entrance as entrance
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    DEFAULT_LEVEL_WORD,
    LEVEL_WORD_MAX_LENGTH,
    PlayerSettings,
    apply_player_settings,
)
from zora.rom.revision import moved_to_prg0_layout
from zora.rom.serialize.features import encoded_refusal_text
from zora.rom.serialize.text import _encode_quote
from zora_export.seed_document import seed_document_for
from zora_export.spoiler_log import spoiler_log

REFUSAL_TEXT_SIZE = 72
LINE_WIDTH = 24                       # the person's text box
DRAWS = range(200)
# FP-TRIF-06: each item's inventory byte, as the spec lists them
SPEC_ITEM_BYTES = {Item.WOOD_SWORD: 0x57, Item.RECORDER: 0x5C, Item.BLUE_CANDLE: 0x5B, Item.WOOD_ARROWS: 0x59,
                   Item.BOW: 0x5A, Item.MAGICAL_KEY: 0x64, Item.RAFT: 0x60, Item.LADDER: 0x63, Item.WAND: 0x5F,
                   Item.BOOK: 0x61, Item.POWER_BRACELET: 0x65}
GENERATED = range(13)
SEEDS = (1, 2)


def flags(c08: int, **options: int) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C08": c08, **options}))


@cache
def built(c08: int, seed: int) -> Built:
    return build(plan(flags(c08), seed), remember_repo_base_rom())


# --- the plan and the draws ---------------------------------------------------------------------

@pytest.mark.parametrize("c08", range(8))
def test_a_count_needs_no_draw(c08: int) -> None:
    entry = plan(flags(c08), 1).alternatives.level_9_entry
    assert not entry.draws and entry.fixed_gate == pieces_gate(8 - c08)
    assert (entry.fixed_gate == EIGHT_PIECES) is (c08 == 0)


def test_open_needs_no_draw() -> None:
    entry = plan(flags(Level9Requirement.OPEN), 1).alternatives.level_9_entry
    assert not entry.draws and entry.fixed_gate == OPEN_GATE


def test_the_range_is_read_only_by_triforce_range_and_specific_triforces() -> None:
    """FL-DEP-03: (C24, 8 - C25), swapped; kept out of the plan under every other value (inert)."""
    for c08 in GENERATED:
        entry = plan(flags(c08, C24=7, C25=4), 1).alternatives.level_9_entry
        if entry.requirement in (Level9Requirement.RANDOM_COUNT_IN_RANGE, Level9Requirement.SPECIFIC_PIECES):
            assert entry.piece_range == (4, 7)
        else:
            assert entry.piece_range == (0, 8), c08


def test_triforce_range_draws_every_count_in_the_range() -> None:
    entry = Level9Entry(Level9Requirement.RANDOM_COUNT_IN_RANGE, (2, 5))
    counts = Counter(draw_level_9_gate(entry, Rng(seed)).pieces for seed in DRAWS)
    assert set(counts) == {2, 3, 4, 5}
    assert {draw_level_9_gate(Level9Entry(Level9Requirement.RANDOM_COUNT_IN_RANGE, (6, 6)), Rng(seed))
            for seed in range(5)} == {pieces_gate(6)}


def test_specific_triforces_draw_that_many_levels() -> None:
    entry = Level9Entry(Level9Requirement.SPECIFIC_PIECES, (0, 8))
    gates = [draw_level_9_gate(entry, Rng(seed)) for seed in DRAWS]
    assert all(gate.kind is GateKind.LEVELS and len(gate.levels) == gate.pieces for gate in gates)
    assert all(gate.levels <= set(TRIFORCE_LEVELS) for gate in gates)
    assert {gate.pieces for gate in gates} == set(range(9))
    assert set().union(*(gate.levels for gate in gates)) == set(TRIFORCE_LEVELS)


@pytest.mark.parametrize("state", [WoodenSwordState.NORMAL, WoodenSwordState.SWORDLESS])
def test_other_item_never_draws_the_letter(state: WoodenSwordState) -> None:
    """Owner ruling 2026-10-22: the eleven items, the sword left out under Swordless (FP-TRIF-06)."""
    entry = Level9Entry(Level9Requirement.ITEM_INSTEAD_OF_PIECES, wooden_sword_state=state)
    drawn = {draw_level_9_gate(entry, Rng(seed)).item for seed in DRAWS}
    assert drawn == set(gate_items(state))
    assert Item.LETTER not in drawn
    assert (Item.WOOD_SWORD in drawn) is (state is not WoodenSwordState.SWORDLESS)


def test_random_resolves_once_per_seed_to_the_five_values() -> None:
    """FL-DEP-04: C08 = 12 resolves to 0, 8, 9, 10 or 11, never to 1 to 7."""
    resolved = Counter(plan(flags(Level9Requirement.RANDOM), seed).alternatives.level_9_entry.requirement
                       for seed in range(60))
    assert set(resolved) == {0, 8, 9, 10, 11}


# --- the bytes ----------------------------------------------------------------------------------

def test_eight_pieces_write_nothing() -> None:
    assert entrance.level_9_entrance_writes(EIGHT_PIECES) == []


@pytest.mark.parametrize("pieces", range(8))
def test_a_count_calls_the_counting_routine(pieces: int) -> None:
    writes = dict(entrance.level_9_entrance_writes(pieces_gate(pieces)))
    assert writes[entrance.ENTRANCE_CHECK] == bytes([0x20, 0x00, 0x9F])               # JSR $9F00
    routine = writes[entrance.ROUTINE]
    assert routine[entrance.COUNT_OPERAND - entrance.ROUTINE] == pieces
    assert entrance.ENTRANCE_COMPARISON not in writes                               # PRG0's CMP #$FF / BNE


def test_open_also_drops_the_comparison() -> None:
    """FP-TRIF-03: the count 0 and four NOPs at 0x04AB4 to 0x04AB7."""
    writes = dict(entrance.level_9_entrance_writes(OPEN_GATE))
    assert writes[entrance.ENTRANCE_COMPARISON] == bytes([0xEA] * 4)
    assert writes[entrance.ROUTINE][entrance.COUNT_OPERAND - entrance.ROUTINE] == 0


def test_the_chosen_levels_mask_lies_where_the_spec_says() -> None:
    """FP-TRIF-05: the mask at 0x05F14 and 0x05F16, bit 0 for level 1."""
    writes = dict(entrance.level_9_entrance_writes(levels_gate(frozenset({2, 6, 8}))))
    rom = bytearray(0x6000)
    for offset, data in writes.items():
        rom[offset:offset + len(data)] = data
    assert entrance.MASK_OPERANDS == (0x05F14, 0x05F16)
    assert [rom[offset] for offset in entrance.MASK_OPERANDS] == [0b10100010] * 2


@pytest.mark.parametrize("item", GATE_ITEMS)
def test_an_item_points_prg0s_load_at_its_byte(item: Item) -> None:
    """FP-TRIF-06: 0x04AB2 the item's byte, 0x04AB5 and 0x04AB6 $00 $F0; no routine."""
    assert entrance.level_9_entrance_writes(item_gate(item)) == [
        (0x04AB2, bytes([SPEC_ITEM_BYTES[item]])), (0x04AB5, bytes([0x00, 0xF0]))]


# --- the text -----------------------------------------------------------------------------------

def every_gate() -> list:
    gates = [pieces_gate(pieces) for pieces in range(9)] + [OPEN_GATE]
    gates += [levels_gate(frozenset(chosen)) for count in range(9) for chosen in combinations(TRIFORCE_LEVELS, count)]
    return gates + [item_gate(item) for item in GATE_ITEMS]


def test_every_text_fits_the_person_s_box() -> None:
    for gate in every_gate():
        text = refusal_text(gate)
        lines = text.split("\n")
        assert len(lines) <= 3 and all(len(line) <= LINE_WIDTH for line in lines), text
        assert len(_encode_quote("|".join(lines), center=True)) <= REFUSAL_TEXT_SIZE, text


def test_the_text_names_the_count_the_levels_or_the_item() -> None:
    assert refusal_text(EIGHT_PIECES) == "YOU NEED EIGHT\nTRIFORCE PIECES."           # every earlier release's
    assert refusal_text(pieces_gate(1)) == "YOU NEED ONE\nTRIFORCE PIECE."
    assert refusal_text(levels_gate(frozenset({8, 2, 6}))).endswith("\n2 6 8.")
    for item in GATE_ITEMS:
        assert GATE_ITEM_WORDS[item] in refusal_text(item_gate(item))


# --- generated seeds ----------------------------------------------------------------------------

@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("c08", GENERATED)
def test_each_value_generates_writes_its_gate_and_is_accepted(c08: int, seed: int) -> None:
    seed_built = built(c08, seed)
    world = seed_built.world
    gate = world.level_9_gate
    if c08 <= Level9Requirement.ONE_PIECE:
        assert gate == pieces_gate(8 - c08)
    elif c08 == Level9Requirement.OPEN:
        assert gate == OPEN_GATE
    elif c08 == Level9Requirement.ITEM_INSTEAD_OF_PIECES:
        assert gate.kind is GateKind.ITEM
    assert world.level9_refusal_text == refusal_text(gate)
    rom = finish(seed_built, remember_repo_base_rom())
    base = remember_repo_base_rom()
    for offset, data in entrance.level_9_entrance_writes(gate):
        assert rom[offset:offset + len(data)] == data
    if gate.is_eight_pieces:
        check = slice(entrance.ENTRANCE_CHECK, entrance.ENTRANCE_COMPARISON + len(entrance.NO_COMPARISON))
        assert rom[check] == base[check]                                     # PRG0's seven bytes
        assert rom[entrance.ROUTINE:entrance.ROUTINE + 35] == base[entrance.ROUTINE:entrance.ROUTINE + 35]
    result = seed_built.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    assert acceptance_check(world.levels, result.item_shuffle_result, world.overworld, result.overworld,
                            shipped_logic_rules(seed_built.plan, world)) is None


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("c08", [3, Level9Requirement.OPEN, Level9Requirement.RANDOM_COUNT_IN_RANGE,
                                 Level9Requirement.SPECIFIC_PIECES, Level9Requirement.ITEM_INSTEAD_OF_PIECES])
def test_the_logic_model_agrees_with_the_acceptance_check(c08: int, seed: int) -> None:
    """Archipelago's model: its Level 9 Entry event is any k Triforce events, the chosen levels', or
    nothing; under an item its sweep reaches the goal with the item, as the closure does."""
    seed_built = built(c08, seed)
    gate = seed_built.world.level_9_gate
    model = logic_model(seed_built)
    swept = sweep(model, identity(seed_built))
    assert swept.reaches_goal
    entry = model.events[LEVEL9_ENTRY_EVENT]
    if gate.kind is GateKind.LEVELS:
        assert entry == frozenset({frozenset(EventTerm(triforce_event(level)) for level in gate.levels)})
    elif gate.kind is GateKind.PIECES:
        assert all(len(clause) == gate.pieces for clause in entry)
        assert len(entry) == len(list(combinations(TRIFORCE_LEVELS, gate.pieces)))
    else:
        assert entry == frozenset({frozenset()})
    result = seed_built.result
    assert result.item_shuffle_result is not None and result.overworld is not None
    check = AcceptanceCheck(seed_built.world.levels, result.item_shuffle_result, seed_built.world.overworld,
                            result.overworld, shipped_logic_rules(seed_built.plan, seed_built.world))
    held, _completed = check.closure()
    assert LEVEL9_ENTRY in held
    assert (LEVEL9_ITEM in check.target()) is (gate.kind is GateKind.ITEM)


def test_level_9_s_completion_never_counts() -> None:
    """Owner ruling 2026-10-21: only levels 1 to 8 count toward a count."""
    rules = replace(DEFAULT_RULES, level_9_gate=pieces_gate(3))
    assert not rules.opens_level_9({1, 2, 9})
    assert rules.opens_level_9({1, 2, 5})
    chosen = replace(DEFAULT_RULES, level_9_gate=levels_gate(frozenset({2, 6})))
    assert not chosen.opens_level_9({1, 2, 3, 4, 5, 7, 8, 9}) and chosen.opens_level_9({2, 6})


def test_an_item_joins_level_9_s_needs_with_b25_on_or_off() -> None:
    for long_items in (True, False):
        rules = replace(DEFAULT_RULES, level_9_needs_long_items=long_items, level_9_gate=item_gate(Item.BOOK))
        assert LEVEL9_ITEM in rules.level_9_entry_needs


# --- the level-4-sword entrance ----------------------------------------------------

ASNB = zora_flags.encode(zora_flags.ZoraFlags(progressive_items=True, add_l4_sword=ThreeState.ON,
                                              l4_sword_in_level_2=True, level_9_entrance_sword=True))


def test_the_level_4_sword_entrance_needs_eight_triforces() -> None:
    assert zora_flags.ENTRANCE_NEEDS_EIGHT_PIECES not in [
        message for message, _fields in zora_flags.conflicts(zora_flags.decode(ASNB), decode(flags(0)))]
    for c08 in (3, Level9Requirement.RANDOM):
        found = zora_flags.conflicts(zora_flags.decode(ASNB), decode(flags(c08)))
        assert (zora_flags.ENTRANCE_NEEDS_EIGHT_PIECES, zora_flags.ENTRANCE_NEEDS_EIGHT_PIECES_FIELDS) in found
        with pytest.raises(FlagsRefused):
            plan(flags(c08), 1, ASNB)


# --- the level word, the parsed gate and the spoiler log (owner decisions, 2026-10-22) ----------

LEVEL_WORDS = ("PALACE", "DUNGEON", "MAZES", "AB CDEF")      # 7 characters, a word ending in S, a space


def test_the_template_is_the_level_word_s_default() -> None:
    assert entrance.DEFAULT_LEVEL_WORD == DEFAULT_LEVEL_WORD


def test_the_chosen_levels_text_fits_with_every_word_s_length() -> None:
    for word in (*LEVEL_WORDS, "X" * LEVEL_WORD_MAX_LENGTH):
        for count in range(1, 9):
            for chosen in combinations(TRIFORCE_LEVELS, count):
                text = entrance.chosen_levels_text(frozenset(chosen), word)
                lines = text.split("\n")
                assert len(lines) == 3 and all(len(line) <= LINE_WIDTH for line in lines), text
                assert len(encoded_refusal_text(text)) <= REFUSAL_TEXT_SIZE, text


@needs_base_rom
@pytest.mark.parametrize("word", LEVEL_WORDS)
def test_a_level_word_names_the_chosen_levels(word: str) -> None:
    """Specific Triforces: the person says the player's word; every other text keeps its own."""
    seed_built = built(Level9Requirement.SPECIFIC_PIECES, 2)
    levels = seed_built.world.level_9_gate.levels
    rom = finish(seed_built, remember_repo_base_rom())
    shown = parse_rom(apply_player_settings(rom, PlayerSettings(level_word=word))).level9_refusal_text
    assert [line.strip("~") for line in shown.split("\n")] == entrance.chosen_levels_text(levels, word).split("\n")
    plural = word if word.endswith("S") else f"{word}S"
    assert f"PIECES OF {plural}" in shown
    counted = finish(built(3, 1), remember_repo_base_rom())
    assert (parse_rom(apply_player_settings(counted, PlayerSettings(level_word=word))).level9_refusal_text
            == parse_rom(counted).level9_refusal_text)


@needs_base_rom
def test_a_level_word_names_the_chosen_levels_on_prg1_too() -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"{PRG1_ROM_PATH.name} is not beside the PRG0 base")
    rom = generate_rom(flags(Level9Requirement.SPECIFIC_PIECES), 2, PRG1_ROM_PATH.read_bytes()).rom
    image = moved_to_prg0_layout(apply_player_settings(rom, PlayerSettings(level_word="PALACE")))
    assert "PIECES OF PALACES" in parse_rom(image).level9_refusal_text


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("c08", GENERATED)
def test_the_rom_s_gate_parses_back(c08: int, seed: int) -> None:
    """The seed document reads the gate from the ROM (parse_rom), as every other field."""
    seed_built = built(c08, seed)
    rom = finish(seed_built, remember_repo_base_rom())
    assert parse_rom(rom, seed_built.plan.config).level_9_gate == seed_built.world.level_9_gate


SPOILER_CASES = {
    (0, 1): "Level 9: triforce pieces needed: 8",
    (3, 1): "Level 9: triforce pieces needed: 5",
    (Level9Requirement.OPEN, 1): "Level 9: open, no triforce pieces needed",
    (Level9Requirement.SPECIFIC_PIECES, 2): "Level 9: needs the triforce pieces of levels 2, 6, 8",
    (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 2): "Level 9: needs this item: Wand (no triforce pieces)",
    (Level9Requirement.RANDOM, 2): "Level 9: triforce pieces needed: 2 (Level 9 Entry: ? -> Triforce Range)",
    (Level9Requirement.RANDOM, 7): "Level 9: open, no triforce pieces needed (Level 9 Entry: ? -> Open Level 9)",
}


@needs_base_rom
@pytest.mark.parametrize(("c08", "seed"), list(SPOILER_CASES))
def test_the_spoiler_log_states_the_entrance_s_requirement(c08: int, seed: int) -> None:
    rom = generate_rom(flags(c08), seed, remember_repo_base_rom()).rom
    document = seed_document_for(rom, flags(c08), seed)
    assert SPOILER_CASES[c08, seed] in spoiler_log(document).splitlines()
    gate = parse_rom(rom).level_9_gate
    assert document["requirements"]["level9Triforces"] == gate.pieces
    assert ("level9Levels" in document["requirements"]) is (gate.kind is GateKind.LEVELS)
    assert ("level9Item" in document["requirements"]) is (gate.kind is GateKind.ITEM)
