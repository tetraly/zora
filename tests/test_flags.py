"""The flag string codec, dependency rules and support matrix (docs/spec/flags-behavior.md, B11).

The checkpoint table, the FL-PRE-05 preset tables and the FL-SUP-02/03 support tables come from
tests/flags_spec_fixture.py, extracted from the spec by tests/flags_spec_tables.py, so this file
runs without docs/spec/; tests/test_spec_fixtures.py checks the fixture against the spec.
"""
import re

import pytest

# The spec tables are left out of releases (release/allowlist.txt): this file skips there.
spec = pytest.importorskip("tests.flags_spec_fixture", reason="the spec tables are not in this tree")
flags_spec_tables = pytest.importorskip("tests.flags_spec_tables", reason="the spec tables are not in this tree")
from zora.flags.codec import ALPHABET, _format_base63, canonicalize, distinct_string_count
from zora.flags.dependencies import (
    boss_hit_point_change, chosen_start_items, enemy_hit_point_change, magical_sword_hearts,
    piece_count_range, pieces_needed, start_item_limit, starting_hearts, starting_pieces, white_sword_hearts,
)
from zora.flags.fields import (
    INERT_TOGGLES, OPTIONS_BY_ID, OptionField, STARTING_HEARTS_RANDOM, START_SCREEN, ToggleField,
)
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF, PRESETS, PUBLISHED_VARIANT_C
from zora.flags.fields import (
    ARMOS_PIN, BOMB_UPGRADE_PERSON_SHUFFLE, BOSS_HIT_POINTS, CAVE_SHUFFLE, COAST_PIN, DUNGEON_LAYOUT_SOURCE,
    DUNGEON_MONSTER_SHUFFLE, DUNGEON_ROOM_SHUFFLE, ENEMY_HIT_POINTS, GANON_AND_ZELDA_SHUFFLE,
    GANON_MUST_BE_BEATEN, HUNGRY_GORIYA_SHUFFLE, IMPORTANT_ITEMS_IN_LEVEL_9, LEVEL_9_REQUIREMENT,
    MAGICAL_SWORD_HIGHEST, MAGICAL_SWORD_LOWEST, MONSTERS_BETWEEN_LEVELS, OPTION_FIELDS, PIECE_RANGE_HIGH,
    PIECE_RANGE_LOW, PIN_FIELDS, START_ITEM_LIMIT, START_ROOM_MAY_MOVE, STARTING_HEARTS,
    TAKE_ANY_ROAD_SHUFFLE, TOGGLE_FIELDS, ENCODE_LEVEL_DATA, WHITE_SWORD_CAVE_PIN, WHITE_SWORD_HIGHEST,
    WHITE_SWORD_LOWEST, WOODEN_SWORD_CAVE_MOVES, WOODEN_SWORD_STATE, CaveShuffle, DungeonLayoutSource,
    DungeonRoomShuffle, HitPointChange, Level9Requirement, PinnedItem, Settings, ThreeState,
    WoodenSwordState,
)
from zora.flags.codec import FlagStringError, decode, encode
from zora.flags.support import (
    OWNER_TURN_OFF_TOGGLES, TURN_OFF_OPTIONS, TURN_OFF_TOGGLES, Support, is_fully_supported,
    mvp_baseline_settings, support,
    unsupported_fields,
)
from zora.flags.dependencies import (
    UnresolvedError, apply_dependencies, check_dependencies, correct_merchant_toll, generation_settings,
    is_resolved,
    missing_prerequisites, refusals, resolve,
)
from zora.generate.alternative_values import AlternativeValues
from zora.generate.pipeline import FlagsRefused, plan
from zora.generate.rng import Rng

PRESET_NAMES = flags_spec_tables.PRESET_NAMES


def _leading_int(cell: str) -> int:
    match = re.match(r"\d+", cell)
    assert match, cell
    return int(match.group())


# --- the checkpoint table -------------------------------------------------------------------------

CHECKPOINT_ROWS = {row[0]: row for row in spec.CHECKPOINT_ROWS}


def _checkpoint_input(cell: str) -> str:
    return "" if cell == "(empty)" else cell.strip("`")


# --- the preset tables (FL-PRE-05) ----------------------------------------------------------------

_THREE_STATE_WORDS = {"off": ThreeState.OFF, "ON": ThreeState.ON, "poss": ThreeState.POSSIBLE}


def preset_settings_from_spec(preset: str) -> Settings:
    column = PRESET_NAMES.index(preset) + 2
    options = {row[0]: _leading_int(row[column]) for row in spec.PRESET_OPTION_ROWS}
    toggles = {row[0]: _THREE_STATE_WORDS[row[column]] for row in spec.PRESET_TOGGLE_ROWS}
    return Settings.zero().updated(options=options, toggles=toggles)


# --- the support tables (FL-SUP-02, FL-SUP-03) ----------------------------------------------------

SUPPORT_OPTION_ROWS = spec.SUPPORT_OPTION_ROWS
SUPPORT_TOGGLE_ROWS = spec.SUPPORT_TOGGLE_ROWS
# FL-OFF-07: | ID | Setting | MVP baseline | Turn-off value | Entry |
TURN_OFF_ROWS = spec.TURN_OFF_ROWS
NO_TURN_OFF = "-"


def turn_off_values(row: list[str]) -> set[int]:
    """The last column of an FL-SUP-02 or FL-SUP-03 row ("Also supported") as values."""
    cell = row[4]
    if cell == NO_TURN_OFF:
        return set()
    if cell.startswith("off"):
        return {ThreeState.OFF}
    if cell.startswith("every other index"):
        return set(range(OPTIONS_BY_ID[row[0]].count)) - {_leading_int(row[2])}
    return {_leading_int(cell)}
# "A value of off means the feature is not produced" (FL-SUP-03); three option rows say so too.
NOT_PRODUCED_TOGGLE_ROWS = [row[0] for row in SUPPORT_TOGGLE_ROWS if row[2] == "off"]
NOT_PRODUCED_OPTION_ROWS = [row[0] for row in SUPPORT_OPTION_ROWS if "not produced" in row[3]]


def _settings(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> Settings:
    return mvp_baseline_settings().updated(options=options or {}, toggles=toggles or {})


# =================================================================================================
# FL-ENC: the format
# =================================================================================================

def test_fl_enc_01_alphabet() -> None:
    assert len(ALPHABET) == 63 == len(set(ALPHABET))
    assert ALPHABET[0] == "0" and ALPHABET[9] == "9" and ALPHABET[10] == "A"
    assert ALPHABET[35] == "Z" and ALPHABET[36] == "a" and ALPHABET[61] == "z"
    assert ALPHABET[62] == "!"
    for preset in PRESETS.values():
        assert set(preset) <= set(ALPHABET)


def test_fl_enc_04_05_field_tables() -> None:
    assert len(OPTION_FIELDS) == 27 and len(TOGGLE_FIELDS) == 91
    assert [option.id for option in OPTION_FIELDS] == [f"C{n:02d}" for n in range(1, 28)]
    assert [toggle.id for toggle in TOGGLE_FIELDS] == [f"B{n:02d}" for n in range(1, 92)]
    for option in OPTION_FIELDS:
        assert option.slots > option.count >= 1
        for random_index, choices in option.random_choices.items():
            assert 0 <= random_index <= option.last_index
            assert all(0 <= choice <= option.last_index and choice != random_index for choice in choices)
    # The field names are the spec's own, except B82 (FP-TOURNEY-01), which
    # ZORA names "Encode level data" (owner decision). (B14 and B16's names are
    # ZORA's in the fixture: tests/flags_spec_tables.py SPEC_WORDING.)
    spec_rows = dict(spec.FIELD_SETTING_ROWS)
    for option in OPTION_FIELDS:
        assert spec_rows[option.id] == option.setting
    for toggle in TOGGLE_FIELDS:
        if toggle == ENCODE_LEVEL_DATA:
            assert toggle.setting == "Encode level data"
        else:
            assert spec_rows[toggle.id] == toggle.setting


def test_fl_enc_04_check_distinct_strings_and_longest_canonical_string() -> None:
    expected = 3 ** 91
    for option in OPTION_FIELDS:
        expected *= option.slots
    assert distinct_string_count() == expected
    largest = decode(_format_base63(expected - 1))
    assert all(largest.option(option) == option.last_index for option in OPTION_FIELDS)
    assert all(largest.toggle(toggle) is ThreeState.POSSIBLE for toggle in TOGGLE_FIELDS)
    assert len(_format_base63(expected - 1)) == 40
    assert len(encode(largest)) <= 40


def test_fl_enc_06_zero_string_and_preset_lengths() -> None:
    assert decode("0") == Settings.zero()
    assert encode(Settings.zero()) == "0"
    assert all(37 <= len(preset) <= 39 for preset in PRESETS.values())


@pytest.mark.parametrize("checkpoint", list(CHECKPOINT_ROWS))
def test_checkpoint_row_round_trips(checkpoint: str) -> None:
    """FL-ENC-02 and FL-ENC-03: every row of the checkpoint table gives the same decoded values and the
    same re-encoded string."""
    _, input_cell, option_cell, toggle_cell, re_encoded_cell = CHECKPOINT_ROWS[checkpoint]
    flag_string = _checkpoint_input(input_cell)
    if option_cell.startswith("error:"):
        with pytest.raises(FlagStringError, match=option_cell.removeprefix("error: ")):
            decode(flag_string)
        return
    settings = decode(flag_string)
    assert [settings.option(option) for option in OPTION_FIELDS] == [int(v) for v in option_cell.split(",")]
    assert "".join(str(int(settings.toggle(toggle))) for toggle in TOGGLE_FIELDS) == toggle_cell.strip("`")
    assert encode(settings) == re_encoded_cell.strip("`")
    assert decode(encode(settings)) == settings


def test_checkpoint_table_has_the_thirteen_codec_rows() -> None:
    assert list(CHECKPOINT_ROWS) == [f"CP-{n}" for n in range(1, 14)]


def test_fl_enc_03_tolerated_forms_beyond_the_table() -> None:
    assert decode("000" + MVP_BASELINE) == decode(MVP_BASELINE)
    assert canonicalize("000" + MVP_BASELINE) == MVP_BASELINE
    # A left-over part above B91 is dropped; a one-digit string is read as a number.
    assert decode("00") == Settings.zero()
    assert decode("1").option("C01") == 1
    for bad in ("", " ", "+", "/", "=", "oIbn PfPb"):
        with pytest.raises(FlagStringError):
            decode(bad)


def test_settings_reject_out_of_range_and_unknown_fields() -> None:
    with pytest.raises(ValueError):
        Settings.zero().updated(options={"C01": 5})
    with pytest.raises(ValueError):
        Settings.zero().updated(options={"C99": 0})
    with pytest.raises(ValueError):
        Settings.zero().updated(toggles={"B01": 3})


# =================================================================================================
# FL-PRE: the four presets
# =================================================================================================

PRESET_ENTRIES = flags_spec_tables.PRESET_ENTRIES


@pytest.mark.parametrize(("preset", "entry"), list(zip(PRESET_NAMES, PRESET_ENTRIES, strict=True)))
def test_preset_string_is_the_spec_string(preset: str, entry: str) -> None:
    assert PRESETS[preset] == spec.PRESET_STRINGS[preset]


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_preset_decodes_to_documented_settings_and_re_encodes(preset: str) -> None:
    """FL-PRE-05: each preset decodes to the table's values; its re-encoding decodes to the same settings
    and, the presets being canonical (FL-ENC-03), is the same string."""
    settings = decode(PRESETS[preset])
    assert settings == preset_settings_from_spec(preset)
    re_encoded = encode(settings)
    assert decode(re_encoded) == settings
    assert re_encoded == PRESETS[preset]


@pytest.mark.parametrize(("preset", "option_diffs", "toggle_diffs", "possible"), [
    ("Published variant A", 5, 1, 0), ("Published variant B", 6, 16, 16), ("Published variant C", 7, 9, 0),
])
def test_preset_differences_from_the_mvp_baseline(preset: str, option_diffs: int, toggle_diffs: int,
                                                  possible: int) -> None:
    """FL-PRE-02 to FL-PRE-04 state how many fields each variant changes."""
    baseline = decode(MVP_BASELINE)
    settings = decode(PRESETS[preset])
    assert sum(settings.option(o) != baseline.option(o) for o in OPTION_FIELDS) == option_diffs
    assert sum(settings.toggle(t) != baseline.toggle(t) for t in TOGGLE_FIELDS) == toggle_diffs
    assert sum(settings.toggle(t) is ThreeState.POSSIBLE for t in TOGGLE_FIELDS) == possible


def test_fl_pre_01_mvp_baseline_prose_values() -> None:
    settings = decode(MVP_BASELINE)
    assert settings.option(DUNGEON_LAYOUT_SOURCE) == DungeonLayoutSource.GENERATED_SHAPES
    assert settings.option("C01") == 0 and settings.option("C03") == 4 and settings.option("C04") == 1
    assert settings.option(CAVE_SHUFFLE) == CaveShuffle.ALL_CAVES and settings.option("C06") == 3
    assert settings.option(LEVEL_9_REQUIREMENT) == Level9Requirement.EIGHT_PIECES
    assert settings.option(ENEMY_HIT_POINTS) == settings.option(BOSS_HIT_POINTS) == HitPointChange.UP_TO_2
    assert settings.option(DUNGEON_ROOM_SHUFFLE) == DungeonRoomShuffle.FULL
    assert settings.option(STARTING_HEARTS) == 2 and settings.option(START_ITEM_LIMIT) == 1
    assert settings.option("C18") == 0
    assert sum(settings.is_on(t) for t in TOGGLE_FIELDS) == 32 and is_resolved(settings)
    assert settings.is_on(ENCODE_LEVEL_DATA)
    # CP-5: the corpus string is the baseline with level encoding off.
    assert decode(MVP_BASELINE_LEVEL_ENCODING_OFF) == settings.updated(toggles={ENCODE_LEVEL_DATA: ThreeState.OFF})


# =================================================================================================
# FL-DEP: dependencies, one test per rule
# =================================================================================================

def test_fl_dep_01_rule_1_ladder_in_the_coast_cave_is_refused() -> None:
    refused = refusals(_settings(options={COAST_PIN.id: PinnedItem.LADDER}))
    assert [r.rule for r in refused] == ["FL-DEP-01 rule 1"]
    assert not refusals(_settings(options={ARMOS_PIN.id: PinnedItem.LADDER}))


def test_fl_dep_01_rule_2_duplicate_pinned_items_are_refused() -> None:
    refused = refusals(_settings(options={ARMOS_PIN.id: PinnedItem.BOW, WHITE_SWORD_CAVE_PIN.id: PinnedItem.BOW}))
    assert [r.rule for r in refused] == ["FL-DEP-01 rule 2"]
    assert "Bow" in refused[0].message.title()
    # Indices 0 and 16 never count as a duplicate, whatever pairs share them.
    for shared in (PinnedItem.NONE_PINNED, PinnedItem.ANY_ITEM_EXCEPT_HEART_CONTAINER):
        assert not refusals(_settings(options={pin.id: shared for pin in PIN_FIELDS}))
    # Any two of the five pin fields trigger it, the level 9 pins included.
    refused = refusals(_settings(options={"C26": PinnedItem.RAFT, "C27": PinnedItem.RAFT}))
    assert [r.rule for r in refused] == ["FL-DEP-01 rule 2"]
    assert not check_dependencies(decode(MVP_BASELINE))


def test_fl_dep_02_rule_1_cave_dependents_need_non_dungeon_cave_shuffle() -> None:
    for dependent in (WOODEN_SWORD_CAVE_MOVES, TAKE_ANY_ROAD_SHUFFLE):
        for cave_shuffle in (CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY):
            only_dependent = Settings.zero().updated(options={CAVE_SHUFFLE: cave_shuffle},
                                                     toggles={dependent: ThreeState.ON})
            assert [r.rule for r in missing_prerequisites(only_dependent)] == ["FL-DEP-02 rule 1"]
        for cave_shuffle in (CaveShuffle.NON_DUNGEON_CAVES_ONLY, CaveShuffle.ALL_CAVES):
            assert not missing_prerequisites(Settings.zero().updated(options={CAVE_SHUFFLE: cave_shuffle},
                                                                     toggles={dependent: ThreeState.ON}))
    assert not missing_prerequisites(Settings.zero())


def test_fl_dep_02_rule_2_room_dependents_need_the_dungeon_room_shuffle() -> None:
    for dependent in (HUNGRY_GORIYA_SHUFFLE, START_ROOM_MAY_MOVE, GANON_MUST_BE_BEATEN):
        vanilla_rooms = Settings.zero().updated(toggles={dependent: ThreeState.ON})
        assert [r.rule for r in missing_prerequisites(vanilla_rooms)] == ["FL-DEP-02 rule 2"]
        for room_shuffle in (DungeonRoomShuffle.WITHIN_EACH_DUNGEON, DungeonRoomShuffle.FULL):
            assert not missing_prerequisites(vanilla_rooms.updated(options={DUNGEON_ROOM_SHUFFLE: room_shuffle}))


def test_fl_dep_02_rule_3_monster_dependents_need_the_dungeon_monster_shuffle() -> None:
    for dependent in (MONSTERS_BETWEEN_LEVELS, GANON_AND_ZELDA_SHUFFLE):
        no_monster_shuffle = Settings.zero().updated(toggles={dependent: ThreeState.ON})
        assert [r.rule for r in missing_prerequisites(no_monster_shuffle)] == ["FL-DEP-02 rule 3"]
        assert not missing_prerequisites(no_monster_shuffle.updated(toggles={DUNGEON_MONSTER_SHUFFLE: ThreeState.ON}))


def test_fl_dep_02_rule_4_layout_source_turns_the_person_shuffles_off() -> None:
    baseline = decode(MVP_BASELINE)
    assert baseline.is_on(HUNGRY_GORIYA_SHUFFLE) and baseline.is_on(BOMB_UPGRADE_PERSON_SHUFFLE)
    for source in (DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED, DungeonLayoutSource.MIXED_WITH_SHAPES):
        applied = apply_dependencies(baseline.updated(options={DUNGEON_LAYOUT_SOURCE: source}))
        assert applied.toggle(HUNGRY_GORIYA_SHUFFLE) is ThreeState.OFF
        assert applied.toggle(BOMB_UPGRADE_PERSON_SHUFFLE) is ThreeState.OFF
        assert applied == baseline.updated(options={DUNGEON_LAYOUT_SOURCE: source},
                                           toggles={"B28": ThreeState.OFF, "B29": ThreeState.OFF})
    for source in (DungeonLayoutSource.FIRST_QUEST, DungeonLayoutSource.GENERATED_SHAPES):
        unchanged = baseline.updated(options={DUNGEON_LAYOUT_SOURCE: source})
        assert apply_dependencies(unchanged) == unchanged
    # Published variant C has C02 = 4: the rule turns its two person shuffles off.
    variant_c = apply_dependencies(decode(PUBLISHED_VARIANT_C))
    assert not variant_c.is_on(HUNGRY_GORIYA_SHUFFLE) and not variant_c.is_on(BOMB_UPGRADE_PERSON_SHUFFLE)


def test_fl_dep_02_rule_5_open_level_9_and_item_instead_of_pieces_never_both_hold() -> None:
    for index in (Level9Requirement.OPEN, Level9Requirement.ITEM_INSTEAD_OF_PIECES):
        settings = _settings(options={LEVEL_9_REQUIREMENT.id: index})
        assert settings.option(LEVEL_9_REQUIREMENT) == index
        assert apply_dependencies(settings) == settings
        assert pieces_needed(settings) is None


def test_fl_dep_02_check_mvp_baseline_meets_every_prerequisite() -> None:
    baseline = decode(MVP_BASELINE)
    assert baseline.option(CAVE_SHUFFLE) == CaveShuffle.ALL_CAVES
    assert baseline.option(DUNGEON_ROOM_SHUFFLE) == DungeonRoomShuffle.FULL
    assert baseline.is_on(DUNGEON_MONSTER_SHUFFLE)
    assert baseline.option(DUNGEON_LAYOUT_SOURCE) == DungeonLayoutSource.GENERATED_SHAPES
    assert not missing_prerequisites(baseline)
    assert apply_dependencies(baseline) == baseline


def test_fl_dep_03_check_mvp_baseline_derived_values() -> None:
    baseline = decode(MVP_BASELINE)
    assert white_sword_hearts(baseline) == (4, 6)
    assert magical_sword_hearts(baseline) == (10, 14)
    assert piece_count_range(baseline) == (0, 8)
    assert pieces_needed(baseline) == 8
    assert starting_hearts(baseline) == 3
    assert starting_pieces(baseline) == 0
    assert start_item_limit(baseline) == 0
    assert chosen_start_items(baseline) == ()
    assert enemy_hit_point_change(baseline) is HitPointChange.UP_TO_2
    assert boss_hit_point_change(baseline).max_shift == 2


def test_fl_dep_03_index_arithmetic_and_swaps() -> None:
    assert white_sword_hearts(_settings(options={WHITE_SWORD_LOWEST.id: 2, WHITE_SWORD_HIGHEST.id: 1})) == (5, 6)
    assert magical_sword_hearts(_settings(options={MAGICAL_SWORD_LOWEST.id: 4, MAGICAL_SWORD_HIGHEST.id: 4})) \
        == (10, 14)
    assert piece_count_range(_settings(options={PIECE_RANGE_LOW.id: 6, PIECE_RANGE_HIGH.id: 5})) == (3, 6)
    for index in range(8):
        assert pieces_needed(_settings(options={LEVEL_9_REQUIREMENT.id: index})) == 8 - index
    assert starting_hearts(_settings(options={STARTING_HEARTS.id: 15})) == 16
    assert start_item_limit(_settings(options={START_ITEM_LIMIT.id: 0})) is None
    assert start_item_limit(_settings(options={START_ITEM_LIMIT.id: 21})) == 20
    with_items = _settings(toggles={"B57": ThreeState.ON, "B85": ThreeState.ON, "B59": ThreeState.POSSIBLE})
    assert [item.id for item in chosen_start_items(with_items)] == ["B57", "B85"]
    assert enemy_hit_point_change(_settings(options={ENEMY_HIT_POINTS.id: 3})) is HitPointChange.ALL_ZERO
    assert HitPointChange.ALL_ZERO.max_shift is None and HitPointChange.NORMAL.max_shift == 0
    with pytest.raises(UnresolvedError):
        starting_hearts(_settings(options={STARTING_HEARTS.id: STARTING_HEARTS_RANDOM}))


def test_fl_dep_04_resolve_picks_among_the_listed_alternatives() -> None:
    every_random = decode(CHECKPOINT_ROWS["CP-12"][1].strip("`"))
    assert not is_resolved(every_random)
    for seed in range(1, 41):
        resolved = resolve(every_random, Rng(seed))
        # B82 never takes "?" (owner ruling, 2026-10-06): generation refuses it before resolving,
        # and the resolver leaves it as it is
        assert resolved.toggle("B82") is ThreeState.POSSIBLE
        assert is_resolved(resolved.updated(toggles={"B82": ThreeState.ON}))
        for option in OPTION_FIELDS:
            if option.is_random(every_random.option(option)):
                assert resolved.option(option) in option.random_choices[every_random.option(option)]
            else:
                assert resolved.option(option) == every_random.option(option)
        assert all(resolved.toggle(t) in (ThreeState.OFF, ThreeState.ON) for t in TOGGLE_FIELDS if t.id != "B82")
    # The alternatives are the FL-DEP-04 list.
    assert DUNGEON_LAYOUT_SOURCE.random_choices == {6: (0, 1, 2, 3, 4), 5: (0, 1, 2)}
    assert LEVEL_9_REQUIREMENT.random_choices == {12: (0, 8, 9, 10, 11)}
    assert STARTING_HEARTS.random_choices == {16: (0, 1, 2, 3, 4)}
    assert START_ITEM_LIMIT.random_choices == {22: tuple(range(1, 22))}
    assert START_SCREEN.random_choices == {}
    # Nothing to resolve in the MVP baseline.
    baseline = decode(MVP_BASELINE)
    assert is_resolved(baseline) and resolve(baseline, Rng(1)) == baseline


def test_fl_dep_04_swordless_forces_a_possible_b25_on() -> None:
    swordless = _settings(options={WOODEN_SWORD_STATE.id: WoodenSwordState.SWORDLESS},
                          toggles={IMPORTANT_ITEMS_IN_LEVEL_9.id: ThreeState.POSSIBLE})
    assert all(resolve(swordless, Rng(seed)).toggle(IMPORTANT_ITEMS_IN_LEVEL_9) is ThreeState.ON
               for seed in range(1, 41))
    random_sword = swordless.updated(options={WOODEN_SWORD_STATE: WoodenSwordState.RANDOM})
    outcomes = {(resolve(random_sword, Rng(seed)).option(WOODEN_SWORD_STATE),
                 resolve(random_sword, Rng(seed)).toggle(IMPORTANT_ITEMS_IN_LEVEL_9)) for seed in range(1, 201)}
    assert (WoodenSwordState.SWORDLESS, ThreeState.OFF) not in outcomes
    assert (WoodenSwordState.SWORDLESS, ThreeState.ON) in outcomes
    assert any(state != WoodenSwordState.SWORDLESS and b25 is ThreeState.OFF for state, b25 in outcomes)
    # A B25 that is plainly off stays off under swordless; the rule is about the possible value.
    plainly_off = swordless.updated(toggles={IMPORTANT_ITEMS_IN_LEVEL_9: ThreeState.OFF})
    assert resolve(plainly_off, Rng(3)).toggle(IMPORTANT_ITEMS_IN_LEVEL_9) is ThreeState.OFF


def test_fl_dep_05_b14_and_b16_select_no_generation_setting() -> None:
    baseline = decode(MVP_BASELINE)
    assert baseline.is_on("B14") and baseline.is_on("B16")
    inert_off = baseline.updated(toggles={"B14": ThreeState.OFF, "B16": ThreeState.OFF})
    assert inert_off != baseline
    assert generation_settings(inert_off) == generation_settings(baseline)
    # They are still decoded and displayed: the support matrix sees the decoded values, and
    # off is each one's turn-off value (FL-OFF-03).
    assert support(inert_off)["B14"] is Support.SUPPORTED and support(baseline)["B14"] is Support.SUPPORTED
    assert encode(inert_off) != encode(baseline)
    assert [t.id for t in INERT_TOGGLES] == ["B14", "B16"]


# =================================================================================================
# FL-SUP: the support matrix
# =================================================================================================

def test_fl_sup_02_03_tables_match_the_mvp_baseline_decode() -> None:
    baseline = mvp_baseline_settings()
    assert baseline == decode(MVP_BASELINE)
    assert len(SUPPORT_OPTION_ROWS) == 27 and len(SUPPORT_TOGGLE_ROWS) == 91
    for row in SUPPORT_OPTION_ROWS:
        assert baseline.option(row[0]) == _leading_int(row[2]), row
    for row in SUPPORT_TOGGLE_ROWS:
        expected = ThreeState.ON if row[2].startswith("on") else ThreeState.OFF
        assert baseline.toggle(row[0]) is expected, row
    assert sum(baseline.option(o) != 0 for o in OPTION_FIELDS) == 10
    assert sum(baseline.is_on(t) for t in TOGGLE_FIELDS) == 32


def test_fl_sup_01_mvp_baseline_preset_is_fully_supported() -> None:
    matrix = support(decode(MVP_BASELINE))
    assert len(matrix) == 118 and set(matrix.values()) == {Support.SUPPORTED}
    assert is_fully_supported(decode(MVP_BASELINE))
    assert is_fully_supported(decode(MVP_BASELINE_LEVEL_ENCODING_OFF))
    # Support is judged on decoded values, not on the spelling (a leading `0`, CP-7).
    assert is_fully_supported(decode(CHECKPOINT_ROWS["CP-7"][1].strip("`")))
    assert Support.SUPPORTED.value == "supported" and Support.NOT_PRODUCED.value == "not produced"


@pytest.mark.parametrize("preset", PRESET_NAMES[1:])
def test_fl_sup_01_other_presets_have_unsupported_fields(preset: str) -> None:
    assert unsupported_fields(decode(PRESETS[preset]))
    assert not is_fully_supported(decode(PRESETS[preset]))


def test_fl_sup_01_level_encoding_is_on_or_off_never_question_mark() -> None:
    """B82 is a plain on/off setting and never takes "?" (owner ruling, 2026-10-06; it replaces
    the 2026-10-04 ruling that supported its "?")."""
    for state in (ThreeState.OFF, ThreeState.ON):
        assert support(_settings(toggles={"B82": state}))["B82"] is Support.SUPPORTED
    assert support(_settings(toggles={"B82": ThreeState.POSSIBLE}))["B82"] is Support.NOT_PRODUCED


def test_not_produced_rows_cover_the_spec_tables() -> None:
    assert len(NOT_PRODUCED_TOGGLE_ROWS) == 91 - 32
    assert NOT_PRODUCED_OPTION_ROWS == ["C07", "C15", "C19"]


@pytest.mark.parametrize("field_id", NOT_PRODUCED_TOGGLE_ROWS)
def test_not_produced_three_state_row(field_id: str) -> None:
    """FL-SUP-03: a three-state field whose supported value is off is not produced when on or possible."""
    assert support(mvp_baseline_settings())[field_id] is Support.SUPPORTED
    for state in (ThreeState.ON, ThreeState.POSSIBLE):
        changed = _settings(toggles={field_id: state})
        assert support(changed)[field_id] is Support.NOT_PRODUCED
        assert unsupported_fields(changed) == [field_id]


@pytest.mark.parametrize("field_id", NOT_PRODUCED_OPTION_ROWS)
def test_not_produced_option_row(field_id: str) -> None:
    """FL-SUP-02: the option rows marked not produced (C07, C15, C19) support only index 0."""
    option = OPTIONS_BY_ID[field_id]
    assert support(mvp_baseline_settings())[field_id] is Support.SUPPORTED
    for index in range(1, option.count):
        assert support(_settings(options={field_id: index}))[field_id] is Support.NOT_PRODUCED


@pytest.mark.parametrize("option", OPTION_FIELDS, ids=[option.id for option in OPTION_FIELDS])
def test_fl_sup_02_supported_option_indices_are_the_baseline_and_the_turn_off_values(option: OptionField) -> None:
    """FL-SUP-02: the baseline index, the "Also supported" column (FL-OFF-07) and the alternative
    values (FL-ALT-02 to FL-ALT-04, owner ruling); every other index is not produced. A random index counts as a "?" and is supported only where all of
    its outcomes are (C17's index 22)."""
    row = next(row for row in SUPPORT_OPTION_ROWS if row[0] == option.id)
    produced = {mvp_baseline_settings().option(option)} | turn_off_values(row) | ALTERNATIVE_VALUES.get(option.id, set())
    for index in range(option.count):
        state = support(_settings(options={option.id: index}))[option.id]
        assert state is (Support.SUPPORTED if index in produced else Support.NOT_PRODUCED), index
    for index, outcomes in option.random_choices.items():
        assert (index in produced) == (set(outcomes) <= produced)


# FL-ALT-01: the alternative values specified, C16 = 3, C20 = 1 and C03 = 2.
ALTERNATIVE_VALUES = {"C16": {3}, "C20": {1}, "C03": {2}}


@pytest.mark.parametrize("field_id, index", [("C16", 3), ("C20", 1), ("C03", 2)])
def test_fl_alt_values_are_produced(field_id: str, index: int) -> None:
    """FL-ALT-02 to FL-ALT-04: owner ruling (2026-10-05), the alternative values are supported after
    the MVP, in place of FL-ALT-01's "not supported in MVP"; each runs its own function."""
    # Level encoding off: plan() needs the level-encoding module for it, which a tree may lack.
    baseline = mvp_baseline_settings().updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.OFF})
    changed = baseline.updated(options={field_id: index})
    assert unsupported_fields(changed) == []
    alternatives = plan(encode(changed), 1).alternatives
    assert alternatives == AlternativeValues(start_with_four_hearts=field_id == "C16",
                                             change_sword_hearts_from_five_hearts=field_id == "C20",
                                             generate_community_hint_text=field_id == "C03")
    assert plan(encode(baseline), 1).alternatives == AlternativeValues()


@pytest.mark.parametrize("field_id", ["C16", "C03"])
def test_fl_alt_random_indices_stay_refused(field_id: str) -> None:
    """A random index is a "?" (FL-DEP-04), supported only where every outcome is: C16's resolves
    to 1 to 5 hearts and C03's to every hint style but Random, so both stay refused. C20 has no
    random index."""
    option = OPTIONS_BY_ID[field_id]
    (random_index,) = option.random_choices
    changed = mvp_baseline_settings().updated(options={field_id: random_index})
    assert unsupported_fields(changed) == [field_id]
    with pytest.raises(FlagsRefused, match=f"{field_id} .*: \\?"):
        plan(encode(changed), 1)
    assert not OPTIONS_BY_ID["C20"].random_choices


@pytest.mark.parametrize("toggle", TOGGLE_FIELDS, ids=[toggle.id for toggle in TOGGLE_FIELDS])
def test_fl_sup_03_supported_three_state_values_are_the_baseline_and_the_turn_off_value(toggle: ToggleField) -> None:
    """FL-SUP-03: the baseline value and the "Also supported" column; "?" wherever off is supported
    (owner ruling, in place of "Possible (2) is not supported for any field"), that is where both
    values are. B23's off needs B22
    off (FL-DEP-06), so it is judged with B22 off."""
    row = next(row for row in SUPPORT_TOGGLE_ROWS if row[0] == toggle.id)
    produced = {mvp_baseline_settings().toggle(toggle)} | turn_off_values(row)
    if {ThreeState.OFF, ThreeState.ON} <= produced:
        produced.add(ThreeState.POSSIBLE)
    if toggle == ENCODE_LEVEL_DATA:
        produced = {ThreeState.OFF, ThreeState.ON}       # never "?" (owner ruling, 2026-10-06)
    if toggle.id in OWNER_TURN_OFF_TOGGLES:
        produced = set(ThreeState)                       # ZORA's own off (owner ruling, 2026-10-07)
    others = {"B22": ThreeState.OFF} if toggle.id == "B23" else {}
    for state in ThreeState:
        judged = support(_settings(toggles={**others, toggle.id: state}))[toggle.id]
        assert judged is (Support.SUPPORTED if state in produced else Support.NOT_PRODUCED), state


def test_fl_off_07_table_matches_the_support_columns_and_counts() -> None:
    """FL-OFF-07 lists 27 fields (22 three-state, 5 option) and 48 values, the same as the last
    columns of FL-SUP-02 and FL-SUP-03 and as zora.flags.support."""
    assert [row[0] for row in TURN_OFF_ROWS] == [
        "B01", "B08", "B09", "B13", "B10", "B11", "B12", "B14", "B16", "B15", "B19", "B22", "B23", "B27", "B28",
        "B31", "B34", "B36", "B40", "B42", "B49", "B54", "C04", "C09", "C10", "C14", "C17"]
    columns = {row[0]: turn_off_values(row) for row in SUPPORT_OPTION_ROWS + SUPPORT_TOGGLE_ROWS
               if turn_off_values(row)}
    assert set(columns) == {row[0] for row in TURN_OFF_ROWS}
    assert sum(len(values) for values in columns.values()) == 48
    assert sorted(TURN_OFF_TOGGLES) == sorted(f for f in columns if f.startswith("B"))
    assert {f: set(v) for f, v in TURN_OFF_OPTIONS.items()} == {f: v for f, v in columns.items() if f.startswith("C")}


def test_fl_sup_01_check_turn_off_strings() -> None:
    """FL-SUP-01's Check: CP-5 with every turn-off value (C17 at 0, B22 and B23 off) has 0
    unsupported fields; CP-5 with B22 off and B23 on is corrected to the pair; B22 on with B23 off
    is not supported."""
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    all_off = cp5.updated(toggles=dict.fromkeys(TURN_OFF_TOGGLES, ThreeState.OFF),
                          options={f: min(v) for f, v in TURN_OFF_OPTIONS.items()})
    assert all_off.option(START_ITEM_LIMIT) == 0
    assert is_fully_supported(all_off)
    merchants_off = cp5.updated(toggles={"B22": ThreeState.OFF})
    assert correct_merchant_toll(merchants_off) == merchants_off.updated(toggles={"B23": ThreeState.OFF})
    assert is_fully_supported(correct_merchant_toll(merchants_off))
    assert unsupported_fields(cp5.updated(toggles={"B23": ThreeState.OFF})) == ["B23"]


def test_fl_dep_06_b22_off_forces_b23_off_and_is_never_refused() -> None:
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    pasted = cp5.updated(toggles={"B22": ThreeState.OFF})
    pair = pasted.updated(toggles={"B23": ThreeState.OFF})
    assert check_dependencies(pasted) == []
    assert correct_merchant_toll(pasted) == pair
    assert correct_merchant_toll(pasted.updated(toggles={"B23": ThreeState.POSSIBLE})) == pair
    assert correct_merchant_toll(cp5) == cp5            # B22 on: nothing changes


# --- "?" values (FL-DEP-04; owner rulings 2026-10-04) ------------------------------------------------

def test_question_mark_on_a_field_without_a_supported_off_is_refused_up_front() -> None:
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    for field_id in ("B02", "B32", "B43"):              # on in the baseline, off not supported
        assert unsupported_fields(cp5.updated(toggles={field_id: ThreeState.POSSIBLE})) == [field_id]
    # B23's off needs B22 off, so a "?" on B23 with B22 on or "?" is refused
    for b22 in (ThreeState.ON, ThreeState.POSSIBLE):
        assert unsupported_fields(cp5.updated(toggles={"B22": b22, "B23": ThreeState.POSSIBLE})) == ["B23"]
    # a random index that may resolve to an unsupported index
    for option_id, random_index in (("C09", 4), ("C10", 4), ("C14", 3)):
        assert unsupported_fields(cp5.updated(options={option_id: random_index})) == [option_id]
    assert is_fully_supported(cp5.updated(options={"C17": 22}))
    assert is_fully_supported(cp5.updated(toggles={"B22": ThreeState.POSSIBLE}))
    assert is_fully_supported(cp5.updated(toggles=dict.fromkeys(TURN_OFF_TOGGLES, ThreeState.POSSIBLE)
                                          | {"B23": ThreeState.ON}))
    assert unsupported_fields(cp5.updated(toggles={"B82": ThreeState.POSSIBLE})) == ["B82"]
