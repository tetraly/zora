"""Force Overworld Block (B81; overworld-behavior.md OW-CAVE-08): a cave result with no dungeon
door and no white-sword cave behind an item gate restarts the whole seed. The Check over 1,000
seeds: `python3 scripts/compare_corpus.py --set b81`."""
import copy
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import FORCE_OVERWORLD_BLOCK, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support
from zora.generate.pipeline import build, plan
from zora.generate.steps.cave_entries import CaveShuffle, Entry
from zora.generate.steps.force_overworld_block import force_overworld_block, has_gated_door
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.overworld_quests import FORCE_BLOCK_FLAGS, gated_doors

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

POSSIBLE_FLAGS = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
    toggles={FORCE_OVERWORLD_BLOCK.id: ThreeState.POSSIBLE}))


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


def test_the_corpus_string_is_cp5_with_b81_on() -> None:
    settings = decode(FORCE_BLOCK_FLAGS)
    assert settings.toggle(FORCE_OVERWORLD_BLOCK) is ThreeState.ON
    off = settings.updated(toggles={FORCE_OVERWORLD_BLOCK.id: ThreeState.OFF})
    assert encode(off) == MVP_BASELINE_LEVEL_ENCODING_OFF
    for state in ThreeState:
        judged = support(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={FORCE_OVERWORLD_BLOCK.id: state}))
        assert judged[FORCE_OVERWORLD_BLOCK.id] is Support.SUPPORTED, state


@pytest.mark.parametrize("screen, code, passes", [
    (47, Destination.LEVEL_3, True),               # the raft set
    (66, Destination.WHITE_SWORD_CAVE, True),      # the recorder set
    (29, Destination.LEVEL_8, True),               # the bracelet set
    (32, Destination.LEVEL_8, False),              # 32 and 33 are left out of the bracelet set
    (40, Destination.LEVEL_8, False),              # the burnable set does not count
    (47, Destination.TAKE_ANY, False),             # only doors and the white-sword cave
])
def test_the_test(screen: int, code: Destination, passes: bool) -> None:
    """OW-CAVE-08's test reads the cave-list entries at their final screens."""
    caves = CaveShuffle([Entry(4, Destination.LEVEL_1, 0), Entry(screen, code, 0)], armos_screen=36)
    overworld = copy.deepcopy(_prg0().overworld)
    assert has_gated_door(overworld, caves) is passes
    assert (force_overworld_block(overworld, caves) is None) is passes


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_seed_has_a_gated_door(seed: int) -> None:
    """B81 on: every finished seed has a dungeon door or the white-sword cave behind an item gate;
    a seed that had none restarted (the restart reasons say so)."""
    built = build(plan(FORCE_BLOCK_FLAGS, seed), _base())
    assert gated_doors(built.world) > 0


def test_possible_is_a_coin_per_seed() -> None:
    """B81 at "?" resolves on or off per seed (FL-DEP-04)."""
    resolved = {plan(POSSIBLE_FLAGS, seed).alternatives.force_overworld_block for seed in range(12)}
    assert resolved == {True, False}
