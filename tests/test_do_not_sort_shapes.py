"""Do Not Sort Shapes (B86; shapes-behavior.md SH-NUM-02, SH-NUM-04): on and Random are produced;
with it on, each set's level numbers are a uniform shuffle, so the room counts no longer rise
with the level number; level 9 stays in the three-level set; where the shape generator does not
run (vanilla dungeons) it changes nothing."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec
from zora.flags.fields import DungeonLayoutSource, ThreeState
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.generate.pipeline import Built, build, plan, shape_options
from zora.model.canonical import canonical_bytes
from zora.rom.base_rom import remember_repo_base_rom

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5: generated shapes (C02 = 3)
SEEDS = range(1, 13)
FIRST_SET, SECOND_SET = range(1, 7), range(7, 10)


@pytest.mark.parametrize("state", list(ThreeState))
def test_every_value_is_supported(state: ThreeState) -> None:
    assert support(DEFAULT_SETTINGS.updated(toggles={"B86": state}))["B86"] is Support.SUPPORTED


def test_on_turns_sorting_off() -> None:
    assert shape_options(DEFAULT_SETTINGS).sort_shapes
    assert not shape_options(DEFAULT_SETTINGS.updated(toggles={"B86": ThreeState.ON})).sort_shapes


@cache
def _built(b86: ThreeState, seed: int, quest: DungeonLayoutSource = DungeonLayoutSource.GENERATED_SHAPES) -> Built:
    settings = DEFAULT_SETTINGS.updated(options={"C02": quest}, toggles={"B86": b86})
    return build(plan(codec.encode(settings), seed), remember_repo_base_rom())


def _sizes_rise(built: Built, numbers: range) -> bool:
    sizes = [len(built.world.levels[number - 1].room_nums) for number in numbers]
    return sizes == sorted(sizes)


@needs_base_rom
def test_sorted_without_it_shuffled_with_it() -> None:
    """SH-NUM-01 with B86 off: room counts never fall from level 1 to 6 or from 7 to 9. With it on
    (SH-NUM-04's Check: about 1 seed in 200 keeps 1 to 6 rising), some seed breaks the order."""
    assert all(_sizes_rise(_built(ThreeState.OFF, seed), numbers) for seed in SEEDS for numbers in (FIRST_SET, SECOND_SET))
    assert not all(_sizes_rise(_built(ThreeState.ON, seed), FIRST_SET) for seed in SEEDS)


@needs_base_rom
def test_level_9_stays_in_the_three_level_set() -> None:
    for seed in SEEDS:
        levels = _built(ThreeState.ON, seed).world.levels
        assert levels[8].block is levels[6].block is levels[7].block
        assert levels[8].block is not levels[0].block


@needs_base_rom
def test_no_effect_without_the_shape_generator() -> None:
    """Under 1st Quest dungeons (C02 = 0) B86 on is the same world as off: no shape pass, no draw."""
    for seed in SEEDS[:3]:
        plain = _built(ThreeState.OFF, seed, DungeonLayoutSource.FIRST_QUEST).world
        on = _built(ThreeState.ON, seed, DungeonLayoutSource.FIRST_QUEST).world
        assert canonical_bytes(plain) == canonical_bytes(on)
