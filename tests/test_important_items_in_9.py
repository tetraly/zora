"""Allow Important Items in 9 (B25, acceptance.md VA-REJ-08): level 9's items need level-9 entry
instead of the five long items. The corpus figures over 1,000 seeds: `python3
scripts/compare_corpus.py --set b25`."""
from functools import cache

import pytest

from zora.generate.acceptance_check import DEFAULT_RULES, LEVEL9_ENTRY, LONG_ITEMS
from zora.generate.pipeline import extra_options, generate_rom, plan
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.acceptance import IMPORTANT_ITEMS_IN_9_FLAGS, long_items_in_level9_cellars

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")
# Seeds 0-39 put a long item in a level-9 item cellar in some (VA-REJ-08's Check: 266 of 1,000)
SEEDS = range(40)


def test_level_9_needs_its_entry_without_the_long_items() -> None:
    rules = extra_options(plan(IMPORTANT_ITEMS_IN_9_FLAGS, 1)).logic_rules
    assert rules.level_9_entry_needs == {LEVEL9_ENTRY}
    assert DEFAULT_RULES.level_9_entry_needs == LONG_ITEMS | {LEVEL9_ENTRY}


@cache
def _cellar_counts() -> list[int]:
    base = remember_repo_base_rom()
    config = plan(IMPORTANT_ITEMS_IN_9_FLAGS, 1).config
    parse_config = GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode)
    return [long_items_in_level9_cellars(parse_rom(generate_rom(IMPORTANT_ITEMS_IN_9_FLAGS, seed, base).rom,
                                                   parse_config))
            for seed in SEEDS]


def test_a_long_item_may_sit_in_a_level_9_item_cellar() -> None:
    """With B25 on, the check accepts seeds with a long item in level 9 (never with B25 off)."""
    assert any(_cellar_counts())
