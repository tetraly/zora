"""Item and Sprite Appearance (C15; features-behavior.md FP-SPRITE-01) on finished ROMs from the
spec's own Check strings (CP-5 with C15 = 1, 2 and 3):

  - fun percentage: all 34 item pictures one of the twelve sources' PRG0 bytes, the four zeroed;
  - sprite shuffle: every picture one of the 19 sources' PRG0 bytes, the four zeroed, the five groups
    equal;
  - under both: the title story's list holds eighteen $34, the file-select set-up keeps PRG0's
    code (no icons) and the heading shows four characters from $01 to $23, which the page and the
    spoiler log show as the seed code;
  - C15 = 3 resolves to 0, 1 and 2; CP-5 keeps PRG0's pictures and list, with the icons."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.generate.rng import Rng
from zora.rom import item_sprites as sprites
from zora.rom.archipelago_logo import LOGO_TILES, LOGO_TILES_AT, logo_writes
from zora.rom.base_rom import remember_repo_base_rom
from zora_export.seed_document import seed_document
from zora_web import api

pytestmark = needs_base_rom
C15 = {1: "8hq4BeR1JXo89BJ2!TFpTPdBDXGJCV", 2: "8hq4BeR1JXo89BJ2!TFpTQFJXw2JLq", 3: "8hq4BeR1JXo89BJ2!TFpTQsRsJpJVA"}
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF


@cache
def rom(flag_string: str, seed: int) -> bytes:
    base = remember_repo_base_rom()
    return finish(build(plan(flag_string, seed), base), base)


def pattern(data: bytes, offset: int) -> bytes:
    return data[offset:offset + sprites.PATTERN_BYTES]


def demo_list(data: bytes) -> bytes:
    return data[sprites.DEMO_LEFT_ITEMS:sprites.DEMO_LEFT_ITEMS + sprites.DEMO_LEFT_ITEMS_CHANGED]


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_fun_percentage(seed: int) -> None:
    base, finished = remember_repo_base_rom(), rom(C15[1], seed)
    written = {pattern(finished, offset) for offset in sprites.ITEM_PATTERNS if offset not in sprites.ZEROED}
    assert len(written) == 1 and written <= {pattern(base, offset) for offset in sprites.FUN_PERCENTAGE_SOURCES}
    assert all(pattern(finished, offset) == bytes(sprites.PATTERN_BYTES) for offset in sprites.ZEROED)


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_sprite_shuffle(seed: int) -> None:
    base, finished = remember_repo_base_rom(), rom(C15[2], seed)
    sources = {pattern(base, offset) for offset in sprites.SHUFFLE_SOURCES}
    assert all(pattern(finished, offset) in sources for offset in sprites.ITEM_PATTERNS if offset not in sprites.ZEROED)
    assert all(pattern(finished, offset) == bytes(sprites.PATTERN_BYTES) for offset in sprites.ZEROED)
    for first, *others in sprites.EQUAL_GROUPS:
        assert all(pattern(finished, other) == pattern(finished, first) for other in others)


@pytest.mark.parametrize("appearance", (1, 2))
@pytest.mark.parametrize("seed", (1, 2))
def test_the_title_story_and_the_code_as_text(appearance: int, seed: int) -> None:
    finished = rom(C15[appearance], seed)
    assert demo_list(finished) == bytes([sprites.DEMO_ITEM]) * sprites.DEMO_LEFT_ITEMS_CHANGED
    text = api.code_text(finished)
    assert text is not None and len(text) == 4 and all(character in sprites.CODE_TEXT for character in text)
    assert api.code_icons(finished) == []
    assert seed_document(finished, plan(C15[appearance], seed))["seed"]["code"] == [text]


def test_c15_random_resolves_to_each_value() -> None:
    assert {plan(C15[3], seed).config.item_appearance for seed in range(30)} == {0, 1, 2}


def test_normal_keeps_the_pictures_and_the_icons() -> None:
    base, finished = remember_repo_base_rom(), rom(CP5, 1)
    assert all(pattern(finished, offset) == pattern(base, offset) for offset in sprites.ITEM_PATTERNS)
    assert demo_list(finished) == demo_list(base)
    assert api.code_text(finished) is None and len(api.code_icons(finished)) == 4


@pytest.mark.parametrize("appearance", (1, 2))
def test_the_logos_tiles_are_never_written(appearance: int) -> None:
    """The Archipelago logo has background tiles of its own (archipelago_logo.py), which no draw of
    Item Sprites writes; since the look setting's retirement (docs/design/archipelago-items.md piece 5)
    the magical shield's picture is a source and a target in every ROM."""
    image = bytearray(remember_repo_base_rom())
    for address, data in logo_writes():
        image[address:address + len(data)] = data
    logo_bytes = range(LOGO_TILES_AT, LOGO_TILES_AT + len(LOGO_TILES))
    for key in range(40):
        written = dict(sprites.item_sprite_writes(image, appearance, Rng(key)))
        assert not any(offset in logo_bytes or offset + len(data) - 1 in logo_bytes
                       for offset, data in written.items())
        assert set(written) == set(sprites.ITEM_PATTERNS) | {sprites.DEMO_LEFT_ITEMS}
