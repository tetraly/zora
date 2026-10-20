"""Dungeon Quest's last three values: Mixed Quest (C02 = 2, SH-SRC-09), Random No Shapes (C02 = 5)
and Random (C02 = 6, SH-SRC-10), with FL-DEP-02 rule 4 and FL-DEP-04. These tests need no ROM: the
flag tables, the plan and the set-source draws. The finished-ROM checks are in
tests/test_dungeon_quest.py (they need the base ROM); the corpus figures come from
`python3 scripts/compare_corpus.py --set c02-mixed` (and c02-random-noshapes, c02-random)."""
from collections import Counter

import pytest

from zora import archipelago
from zora.archipelago import OptionsConflict, flag_strings
from zora.flags import form as flag_form
from zora.flags.codec import decode, encode
from zora.flags.dependencies import apply_dependencies
from zora.flags.fields import (
    BOMB_UPGRADE_PERSON_SHUFFLE,
    DUNGEON_LAYOUT_SOURCE,
    HUNGRY_GORIYA_SHUFFLE,
    DungeonLayoutSource,
    ThreeState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support, unsupported_fields
from zora.generate.alternative_values import AlternativeValues
from zora.generate.pipeline import plan, resolve_question_marks
from zora.generate.rng import Rng
from zora.generate.steps.dungeon_quest import (
    MIXED_HEADS,
    MIXED_TAILS,
    draw_attempt_set_sources,
    draw_seed_set_sources,
    monsters_take_second_quest_path,
)
from zora_measure.checkpoints.dungeon_quest import (
    MIXED_DUNGEONS_FLAGS,
    RANDOM_DUNGEONS_FLAGS,
    RANDOM_NO_SHAPES_FLAGS,
)

NEW_VALUES = {MIXED_DUNGEONS_FLAGS: DungeonLayoutSource.MIXED,
              RANDOM_NO_SHAPES_FLAGS: DungeonLayoutSource.RANDOM_WITHOUT_SHAPES,
              RANDOM_DUNGEONS_FLAGS: DungeonLayoutSource.RANDOM}
# FL-DEP-04 / SH-SRC-10: what each random index draws from
DRAWN = {DungeonLayoutSource.RANDOM_WITHOUT_SHAPES: {0, 1, 2}, DungeonLayoutSource.RANDOM: {0, 1, 2, 3, 4}}
# FL-DEP-02 rule 4: the drawn values that turn the two person shuffles off
WITHOUT_PERSON_MOVES = {DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED,
                        DungeonLayoutSource.MIXED_WITH_SHAPES}
SEEDS = range(1, 301)


# --- the flag string and the support matrix (FL-SUP-01, FL-SUP-02) ---------------------------------

@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_the_corpus_strings_are_cp5_with_only_c02_changed(flags: str) -> None:
    """SH-SRC-07's Check strings decode to CP-5 with C02 changed, and round-trip."""
    settings = decode(flags)
    assert settings.option(DUNGEON_LAYOUT_SOURCE) == NEW_VALUES[flags]
    assert encode(settings) == flags
    baseline = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    assert settings == baseline.updated(options={DUNGEON_LAYOUT_SOURCE: NEW_VALUES[flags]})


@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_each_value_is_supported_alone(flags: str) -> None:
    """FL-SUP-01: every value of C02 is supported; a random index is because every value it draws
    is (C02 = 5: 0 to 2; C02 = 6: 0 to 4)."""
    settings = decode(flags)
    assert support(settings)[DUNGEON_LAYOUT_SOURCE.id] is Support.SUPPORTED
    assert unsupported_fields(apply_dependencies(settings)) == []


def test_every_c02_value_is_supported() -> None:
    baseline = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    assert all(support(baseline.updated(options={DUNGEON_LAYOUT_SOURCE: value}))[DUNGEON_LAYOUT_SOURCE.id]
               is Support.SUPPORTED for value in DungeonLayoutSource)
    assert set(flag_form.supported_values(DUNGEON_LAYOUT_SOURCE)) == set(DungeonLayoutSource)


# --- the plan: FL-DEP-02 rule 4 and FL-DEP-04 ------------------------------------------------------

def test_mixed_quest_plans_with_the_person_moves_off() -> None:
    """SH-SRC-09 and FL-DEP-02 rule 4: B28 and B29 are off; the generator sees Mixed Quest."""
    chosen = plan(MIXED_DUNGEONS_FLAGS, 1)
    assert chosen.alternatives.dungeon_quest is DungeonLayoutSource.MIXED
    assert not chosen.steps.shuffle_hungry_goriya and not chosen.steps.shuffle_bomb_upgraders
    assert chosen.alternatives == AlternativeValues(dungeon_quest=DungeonLayoutSource.MIXED)


@pytest.mark.parametrize("index", [DungeonLayoutSource.RANDOM_WITHOUT_SHAPES, DungeonLayoutSource.RANDOM])
def test_a_random_index_draws_once_per_seed_and_acts_as_the_drawn_value(index: DungeonLayoutSource) -> None:
    """SH-SRC-10: the value is drawn per seed, uniformly (FL-DEP-04), the same each time for one
    seed; FL-DEP-02 rule 4 then acts on the drawn value: a drawn 1, 2 or 4 turns B28 and B29 off,
    a drawn 0 or 3 keeps them on (CP-5 has both on)."""
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={DUNGEON_LAYOUT_SOURCE: index}))
    drawn: Counter[int] = Counter()
    for seed in SEEDS:
        chosen = plan(flags, seed)
        value = chosen.alternatives.dungeon_quest
        drawn[value] += 1
        assert chosen.settings.option(DUNGEON_LAYOUT_SOURCE) == value
        person_moves = value not in WITHOUT_PERSON_MOVES
        assert chosen.steps.shuffle_hungry_goriya is person_moves
        assert chosen.steps.shuffle_bomb_upgraders is person_moves
        assert plan(flags, seed).alternatives.dungeon_quest is value          # once per seed
    assert set(drawn) == DRAWN[index]
    expected = len(SEEDS) / len(DRAWN[index])
    assert all(abs(count - expected) < 4 * expected ** 0.5 for count in drawn.values()), drawn


def test_rule_4_after_resolving_changes_only_a_drawn_c02() -> None:
    """resolve_question_marks applies FL-DEP-02 rule 4 to the drawn values. Strings without a
    random C02 resolve exactly as before: an explicit 1, 2 or 4 has had the rule applied already,
    and 0 and 3 never trigger it."""
    baseline = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    for value in (DungeonLayoutSource.FIRST_QUEST, DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED,
                  DungeonLayoutSource.GENERATED_SHAPES, DungeonLayoutSource.MIXED_WITH_SHAPES):
        # a "?" elsewhere so that the resolution runs (B81 = 2)
        settings = apply_dependencies(baseline.updated(options={DUNGEON_LAYOUT_SOURCE: value},
                                                       toggles={"B81": ThreeState.POSSIBLE}))
        for seed in range(1, 21):
            resolved = resolve_question_marks(settings, seed, encode(settings))
            assert resolved.toggle(HUNGRY_GORIYA_SHUFFLE) is settings.toggle(HUNGRY_GORIYA_SHUFFLE)
            assert resolved.toggle(BOMB_UPGRADE_PERSON_SHUFFLE) is settings.toggle(BOMB_UPGRADE_PERSON_SHUFFLE)


def test_default_plans_are_unchanged() -> None:
    """The MVP baseline still plans shapes dungeons with the person moves on."""
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    assert chosen.alternatives == AlternativeValues()
    assert chosen.steps.shuffle_hungry_goriya and chosen.steps.shuffle_bomb_upgraders


# --- the set sources (SH-SRC-09, SH-SRC-05) --------------------------------------------------------

def test_mixed_quest_draws_a_coin_on_every_attempt_from_the_generation_stream() -> None:
    """SH-SRC-09: no source pair per seed; heads makes levels 1-6 second quest and 7-9 first,
    tails the other way round; the coin is redrawn on each attempt, so both outcomes occur."""
    rng = Rng(5)
    assert draw_seed_set_sources(DungeonLayoutSource.MIXED, rng) is None
    outcomes = Counter(draw_attempt_set_sources(None, rng) for _ in range(400))
    assert set(outcomes) == {MIXED_HEADS, MIXED_TAILS}
    assert 150 < outcomes[MIXED_HEADS] < 250, outcomes
    assert MIXED_HEADS[0].name == "SECOND_QUEST" and MIXED_TAILS[1].name == "SECOND_QUEST"


def test_mixed_quest_keeps_the_first_quest_monster_branches() -> None:
    """SH-SRC-09's quirk: the branch bytes stay $F0 under Mixed Quest though one set is second
    quest; Mixed + Shapes with the same pair takes the second-quest path."""
    for sources in (MIXED_HEADS, MIXED_TAILS):
        assert not monsters_take_second_quest_path(DungeonLayoutSource.MIXED, sources)
        assert monsters_take_second_quest_path(DungeonLayoutSource.MIXED_WITH_SHAPES, sources)


@pytest.mark.parametrize("index", [DungeonLayoutSource.RANDOM_WITHOUT_SHAPES, DungeonLayoutSource.RANDOM])
def test_the_generator_never_sees_a_random_index(index: DungeonLayoutSource) -> None:
    """SH-SRC-10: C02 = 5 and 6 reach the generator already drawn."""
    with pytest.raises(ValueError, match="SH-SRC-10"):
        draw_seed_set_sources(index, Rng(1))


# --- the page and Archipelago ----------------------------------------------------------------------

@pytest.mark.parametrize("flags", list(NEW_VALUES))
def test_the_page_offers_each_value(flags: str) -> None:
    """The form shows each value as produced; Mixed Quest notes FL-DEP-02 rule 4's adjustment."""
    state = flag_form.form_state(flags)
    field = state["fields"][DUNGEON_LAYOUT_SOURCE.id]
    assert not field["problem"]
    assert state["generateRefusals"] == []
    notes = [f"FL-DEP-02 rule 4 turns {toggle} off" for toggle in ("B28", "B29")]
    assert (state["adjustments"] == notes) == (NEW_VALUES[flags] is DungeonLayoutSource.MIXED)


@pytest.mark.parametrize("value", [DungeonLayoutSource.MIXED, DungeonLayoutSource.RANDOM_WITHOUT_SHAPES,
                                   DungeonLayoutSource.RANDOM])
def test_archipelago_offers_the_new_values(value: DungeonLayoutSource) -> None:
    """Each new value passed its logic scan (2026-10-16) and is offered: not held back, and its
    flag string carries it."""
    assert value not in archipelago.HELD_BACK.get(DUNGEON_LAYOUT_SOURCE.id, frozenset())
    flags, _zora = flag_strings({DUNGEON_LAYOUT_SOURCE.id: int(value)})
    assert decode(flags).option(DUNGEON_LAYOUT_SOURCE.id) == value
