"""Change Hidden OW Tiles (B89; features-behavior.md FP-VIS-01) on finished ROMs from the spec's own
Check strings (CP-5 with B89 on under each overworld quest, off, and at possible):

  - steps 1 and 2's bytes (the looks, the tiles, the two hooks and the routine) in every ROM with
    B89 on, PRG0's with it off;
  - step 3: under C01 = 0 and 1 the layouts are PRG0's with the plain twins swapped in for the
    screens whose quest field is 2 or 3, and only there; under C01 = 2 and 3 the layouts keep
    their secret columns;
  - "?" comes out both ways; every ROM generates (and so is accepted);
  - a finished ROM written again (parse_rom, serialize_to_rom) is unchanged under every overworld
    quest, B89 on and off: the steps find their own bytes at their sites (the batch run's crash at
    b275933, the round trip of test_flag_invariants' Mixed Quest - 2nd cases)."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.generate.pipeline import build, finish, plan
from zora.rom import hidden_tiles
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.vanilla_overworld.tables import ROOM_LAYOUTS_OW

pytestmark = needs_base_rom
B89_BY_QUEST = {quest: "Riygf8gJSi!tFYWl0cAQ9ReR8OmsExUFuLQUJ3" + suffix for quest, suffix in enumerate("ABCD")}
B89_OFF_BY_QUEST = {quest: "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3" + suffix for quest, suffix in enumerate("ABCD")}
B89_POSSIBLE = "tQwMJHLcvIIwQvP3!uo2Ak6ZDo5TfQZVkniUJ3A"
LAYOUTS = slice(ROOM_LAYOUTS_OW.file_offset, ROOM_LAYOUTS_OW.file_offset + ROOM_LAYOUTS_OW.size)


@cache
def rom(flag_string: str, seed: int) -> bytes:
    base = remember_repo_base_rom()
    return finish(build(plan(flag_string, seed), base), base)


def fixed_writes(finished: bytes) -> list[tuple[int, bytes]]:
    return [(hidden_tiles.SECRET_LOOKS, hidden_tiles.MARKED_LOOKS),
            (hidden_tiles.MARKED_TILES, hidden_tiles.marked_tile_bytes()),
            (hidden_tiles.SHOVE_TEST, hidden_tiles.SHOVE_HOOK), (hidden_tiles.STEP_TEST, hidden_tiles.STEP_HOOK),
            (hidden_tiles.SOLID_ROUTINE, hidden_tiles.SOLID_ROUTINE_CODE)]


def written(finished: bytes, writes: list[tuple[int, bytes]]) -> list[bool]:
    return [finished[offset:offset + len(data)] == data for offset, data in writes]


@pytest.mark.parametrize("quest", range(4))
@pytest.mark.parametrize("seed", (1, 2))
def test_the_looks_and_the_solid_tiles(quest: int, seed: int) -> None:
    on, off = rom(B89_BY_QUEST[quest], seed), rom(B89_OFF_BY_QUEST[quest], seed)
    assert all(written(on, fixed_writes(on)))
    assert not any(written(off, fixed_writes(off)))


def swapped_entries(finished: bytes, flag_string_off: str, seed: int) -> list[int]:
    """The layout entries that differ from the same seed without B89."""
    without = rom(flag_string_off, seed)
    return [offset for offset in range(LAYOUTS.start, LAYOUTS.stop) if finished[offset] != without[offset]]


@pytest.mark.parametrize("quest", (0, 1))
@pytest.mark.parametrize("seed", (1, 2))
def test_second_quest_only_secrets_are_plain_under_the_first_and_second_quest(quest: int, seed: int) -> None:
    finished = rom(B89_BY_QUEST[quest], seed)
    changed = swapped_entries(finished, B89_OFF_BY_QUEST[quest], seed)
    assert len(changed) == 11
    without = rom(B89_OFF_BY_QUEST[quest], seed)
    assert all(finished[offset] == hidden_tiles.PLAIN_TWINS[without[offset]] for offset in changed)
    assert dict(hidden_tiles.plain_dead_secret_writes(without)) == {offset: bytes([finished[offset]])
                                                                   for offset in changed}


@pytest.mark.parametrize("quest", (2, 3))
def test_the_mixed_quests_keep_their_secret_columns(quest: int) -> None:
    assert swapped_entries(rom(B89_BY_QUEST[quest], 1), B89_OFF_BY_QUEST[quest], 1) == []


@pytest.mark.parametrize("b89", (True, False), ids=("B89 on", "B89 off"))
@pytest.mark.parametrize("quest", range(4))
def test_a_finished_rom_written_again_is_unchanged(quest: int, b89: bool) -> None:
    base = remember_repo_base_rom()
    built = build(plan((B89_BY_QUEST if b89 else B89_OFF_BY_QUEST)[quest], 1), base)
    config = built.plan.config
    assert config.change_hidden_tiles == b89
    finished = serialize_to_rom(built.world, base, config=config)
    assert serialize_to_rom(parse_rom(finished, config), finished, config=config) == finished


def test_the_drawings_are_the_spec_s() -> None:
    """The spec's 256 bytes (FP-VIS-01's informative list), by their SHA-256: a test ships no run of
    the original game's bytes either."""
    import hashlib
    assert hashlib.sha256(hidden_tiles.marked_tile_bytes()).hexdigest() == SPEC_TILES_SHA256


SPEC_TILES_SHA256 = "49d62c66c27ad1061167597328d9bf7484eb27efbc2a1318636dd4c48de0f95d"


def test_b89_random_comes_up_both_ways() -> None:
    assert {plan(B89_POSSIBLE, seed).settings.is_on("B89") for seed in range(16)} == {True, False}
