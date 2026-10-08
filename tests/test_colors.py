"""B5 color sets (post-shapes-b5.md PS-COLOR-02)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.generate.rng import Rng
from zora.generate.steps.shuffle_dungeon_palettes import TEMPLATES, color_candidates, shuffle_dungeon_palettes


def _vanilla() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def test_prg0_candidates_are_pairwise_distinct() -> None:
    candidates = color_candidates(parse_rom(_vanilla()))
    assert len(candidates) == 23 and len(set(candidates)) == 23


def test_template_13_value_rule_wins() -> None:
    """The value rule runs last: template 13 changes set 1 byte 14 and set
    2 bytes 6 and 70 away from the span write."""
    gw = parse_rom(_vanilla())
    first = gw.levels[0].color_sets
    set_1, set_2 = color_candidates(gw)[9 + 13]
    template = TEMPLATES[13]
    changed = [(which, pos) for which, (orig, new) in enumerate(((first[0], set_1), (first[1], set_2)))
               for pos, value in enumerate(orig) if value in (12, 28, 44)]
    for which, pos in changed:
        expected = template[{12: 1, 28: 2, 44: 3}[(first[which])[pos]]]
        assert (set_1, set_2)[which][pos] == expected
    assert (0, 14) in changed and (1, 6) in changed and (1, 70) in changed


def test_nine_distinct_picks() -> None:
    gw = parse_rom(_vanilla())
    state = shuffle_dungeon_palettes(gw, Rng(3))
    assert len(state.picks) == 9 and len(set(state.picks)) == 9
