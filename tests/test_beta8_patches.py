"""The beta 8 export's fixed patches and drop and boss-health passes, on finished ROMs from the
spec's own Check strings (CP-5 with the field set), each against its entry's Check:

  - Recorder to Unbeaten Dungeons (B07; OW-WARP-02): the nine bytes.
  - Hide Dungeon Numbers (B24; FP-LEVEL-02): levels 1 to 8's number byte $2E, 0 and 9 kept.
  - Hidden Health (B55; FP-HIDE-01): the ten heart colours $36 and the beep operand $00, over the
    player's heart colour and beep.
  - Red Bubble Curse (C19 = 1, 2, 3; FP-BUBL-01): the sword test NOPs, each value's own sites, the
    other value's sites PRG0's; 3 resolves to 0, 1 and 2.
  - Make Important Items Drops (B39; PS-EDROP-01): fifteen slots that held a rupee or a heart now
    hold the fifteen codes once each (fourteen under Swordless, no magical sword).
  - Randomize Item Drop Rate (B44; PS-EDROP-02): the four rates in 80 to 175.
  - Maximum Boss Health (B46; PS-HP-07): the twelve boss bytes $FF, the five operands $F0; under
    Swordless the wooden-sword cave sells the red candle.
  - "?" values resolve both ways; ROMs without the fields keep PRG0's bytes at every site."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import build, finish, plan
from zora.model.enums import Destination, Item
from zora.model.overworld import ItemCave
from zora.rom import uphill_battle as patches
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS, LowHealthBeep, PlayerSettings

pytestmark = needs_base_rom
ON, POSSIBLE = ThreeState.ON, ThreeState.POSSIBLE
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF
# The Checks' strings
B07_ON, B07_POSSIBLE = "8hq4BeR1JXo8ASWSdRRMXg3ZGiUJ3A", "8hq4BeR1JXo8BjjsGPcubx74eHUJ3A"
B24_ON, B24_POSSIBLE = "8hq4BeR1TzN7egCKFmIT9etrx!UJ3A", "8hq4BeR1ePx79A5bW4L6qumg0rUJ3A"
B39_ON, B39_SWORDLESS = "8hq4L9OecE3638yzKtw6FRPQPHUJ3A", "8hq4L9OecE3638yzKtw6FRPQPHYbxq"
B44_ON = "8hqerwGbONO2sB14dLLOcfsjsrUJ3A"
B46_ON, B46_SWORDLESS, B46_POSSIBLE = ("8hvJEBxB034Na8kHhL2znopBiZUJ3A", "8hvJEBxB034Na8kHhL2znopBiZYbxq",
                                       "8h!YGkSKhZLd06AWOCr97DdKW!UJ3A")
B55_ON = "YgZ8BgCfnmbFzxlcANtK2jaWeiUJ3A"
C19 = {1: "8hq4BeR1JXo89BJ2!TFwsxa4X1haQV", 2: "8hq4BeR1JXo89BJ2!TG3HV969vurnq", 3: "8hq4BeR1JXo89BJ2!TGAh2j7np78AA"}
BOSS_VALUES, BOSS_VALUE_BYTES = 0x1FB77, 12
BOSS_OPERANDS = (0x120C6, 0x12F27, 0x114D5, 0x12A45, 0x12735)


@cache
def rom(flag_string: str, seed: int, player: PlayerSettings | None = None) -> bytes:
    base = remember_repo_base_rom()
    return finish(build(plan(flag_string, seed), base), base, player_settings=player or DEFAULT_PLAYER_SETTINGS)


def base() -> bytes:
    return remember_repo_base_rom()


def at(data: bytes, writes: list[tuple[int, bytes]]) -> list[bytes]:
    return [data[offset:offset + len(written)] for offset, written in writes]


def written(data: bytes, writes: list[tuple[int, bytes]]) -> bool:
    return at(data, writes) == [written for _offset, written in writes]


def kept(data: bytes, writes: list[tuple[int, bytes]]) -> bool:
    return at(data, writes) == at(base(), writes)


@pytest.mark.parametrize("seed", (1, 2))
def test_recorder_to_unbeaten_dungeons(seed: int) -> None:
    assert written(rom(B07_ON, seed), patches.recorder_to_unbeaten_writes())
    assert kept(rom(CP5, seed), patches.recorder_to_unbeaten_writes())


@pytest.mark.parametrize("seed", (1, 2))
def test_hide_dungeon_numbers(seed: int) -> None:
    levels = parse_rom(rom(B24_ON, seed)).levels
    assert {level.level_num: level.rom_level_num for level in levels if level.level_num <= 8} == dict.fromkeys(
        range(1, 9), patches.QUESTION_MARK_TILE)
    assert next(level for level in levels if level.level_num == 9).rom_level_num == 9


@pytest.mark.parametrize("seed", (1, 2))
def test_hidden_health_overrides_the_player_settings(seed: int) -> None:
    player = PlayerSettings(heart_color=0x16, low_health_beep=LowHealthBeep.KEPT)
    assert written(rom(B55_ON, seed, player), patches.hidden_health_writes())
    assert not written(rom(CP5, seed, player), patches.hidden_health_writes())


@pytest.mark.parametrize("curse", (1, 2))
@pytest.mark.parametrize("seed", (1, 2))
def test_red_bubble_curse(curse: int, seed: int) -> None:
    other = 3 - curse
    finished = rom(C19[curse], seed)
    assert written(finished, patches.red_bubble_writes(curse, base()))
    assert kept(finished, patches.red_bubble_writes(other, base())[1:])
    assert kept(rom(CP5, seed), patches.red_bubble_writes(curse, base()))


def test_slow_speed_with_pegasus_boots_runs_after_the_boots_speed() -> None:
    """Pegasus Boots' `JSR BootsSpeed / NOP` holds InitLinkSpeed's bytes: under C19 = 2 the call
    goes to the slow-speed routine, which calls BootsSpeed first and then halves the speed while
    the curse lasts (owner's fix, beta 8)."""
    boots = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON))
    base_rom = remember_repo_base_rom()
    with_boots = finish(build(plan(CP5, 1, boots), base_rom), base_rom)
    both = finish(build(plan(C19[2], 1, boots), base_rom), base_rom)
    boots_call = with_boots[patches.LINK_SPEED_INIT:patches.LINK_SPEED_INIT + 4]
    assert boots_call[0] == patches.JSR and boots_call[3] == patches.NOP
    routine = both[patches.SLOW_SPEED_ROUTINE:patches.SLOW_SPEED_ROUTINE + 13]
    assert both[patches.LINK_SPEED_INIT:patches.LINK_SPEED_INIT + 4] == patches.SLOW_SPEED_CALL
    assert routine == boots_call[:3] + patches.SLOW_AFTER_BOOTS_CODE


@pytest.mark.parametrize("boots", (False, True), ids=("without the boots", "with the boots"))
def test_slow_speed_written_again_keeps_its_routine(boots: bool) -> None:
    """A finished ROM written again (the round trip) holds the slow-speed call in InitLinkSpeed, not
    the boots' call: the routine stays the one written, with or without BootsSpeed's call first
    (the beta 8 batch run's round-trip failure)."""
    zora = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON)) if boots else ""
    base_rom = remember_repo_base_rom()
    finished = finish(build(plan(C19[2], 1, zora), base_rom), base_rom)
    routine = patches.slow_speed_code(finished)
    assert finished[patches.SLOW_SPEED_ROUTINE:patches.SLOW_SPEED_ROUTINE + len(routine)] == routine
    assert (routine[0] == patches.JSR) == boots


def test_red_bubble_random_resolves_to_each_value() -> None:
    assert {plan(C19[3], seed).config.red_bubble_curse for seed in range(30)} == {0, 1, 2}


def drop_table(data: bytes) -> bytes:
    return data[patches.DROP_ITEM_TABLE:patches.DROP_ITEM_TABLE + patches.DROP_ITEM_COUNT]


@pytest.mark.parametrize("flag_string, codes", [(B39_ON, patches.IMPORTANT_DROPS),
                                                (B39_SWORDLESS, patches.IMPORTANT_DROPS[:-1])])
@pytest.mark.parametrize("seed", (1, 2))
def test_important_items_drops(flag_string: str, codes: tuple[int, ...], seed: int) -> None:
    before, after = drop_table(base()), drop_table(rom(flag_string, seed))
    changed = [slot for slot in range(patches.DROP_ITEM_COUNT) if before[slot] != after[slot]]
    assert all(before[slot] in (patches.RUPEE, patches.HEART) for slot in changed)
    assert sorted(after[slot] for slot in changed) == sorted(codes)


@pytest.mark.parametrize("seed", (1, 2))
def test_random_drop_rates(seed: int) -> None:
    rates = rom(B44_ON, seed)[patches.DROP_RATES:patches.DROP_RATES + patches.DROP_RATE_COUNT]
    assert all(patches.DROP_RATE_LOWEST <= rate <= patches.DROP_RATE_HIGHEST for rate in rates)
    assert drop_table(rom(B44_ON, seed)) == drop_table(base())


@pytest.mark.parametrize("seed", (1, 2))
def test_maximum_boss_health(seed: int) -> None:
    finished = rom(B46_ON, seed)
    assert finished[BOSS_VALUES:BOSS_VALUES + BOSS_VALUE_BYTES] == b"\xff" * BOSS_VALUE_BYTES
    assert [finished[operand] for operand in BOSS_OPERANDS] == [0xF0] * len(BOSS_OPERANDS)


def test_maximum_boss_health_under_swordless_sells_the_red_candle() -> None:
    cave = parse_rom(rom(B46_SWORDLESS, 1)).overworld.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
    assert cave is not None and cave.item == Item.RED_CANDLE


@pytest.mark.parametrize("flag_string, field_id", [(B07_POSSIBLE, "B07"), (B24_POSSIBLE, "B24"),
                                                   (B46_POSSIBLE, "B46")])
def test_each_random_comes_up_both_ways(flag_string: str, field_id: str) -> None:
    assert {plan(flag_string, seed).settings.is_on(field_id) for seed in range(16)} == {True, False}


@pytest.mark.parametrize("field_id", ["B39", "B44", "B55"])
def test_the_other_randoms_come_up_both_ways(field_id: str) -> None:
    flag_string = encode(decode(CP5).updated(toggles={field_id: POSSIBLE}))
    assert {plan(flag_string, seed).settings.is_on(field_id) for seed in range(16)} == {True, False}
