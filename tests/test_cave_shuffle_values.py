"""Cave Shuffle's values and the wooden-sword and take-any-road caves left out (overworld-behavior.md
OW-CAVE-09 to OW-CAVE-12; flags-behavior.md FL-DEP-02 rule 1; acceptance.md VA-REJ-21)."""
from collections import Counter
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import CaveShuffle, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.cave_entries import ENROLLED_SCREENS, FIXED_SCREENS, WOOD_SWORD_SCREENS
from zora.generate.steps.mixed_overworld_quest import (
    FIRST_QUEST_SECRET_POSITIONS,
    SECOND_QUEST_DEALT_POSITIONS,
    WOOD_SWORD_LIST_INDEX,
    mixed_quest_entries,
    second_quest_entries,
)
from zora.generate.steps.shuffle_caves import (
    ALL_CAVES_WALK,
    CaveWalkParts,
    cave_walk_parts,
    enrolled_entries,
    leave_wood_sword_cave_in_place,
    walk_destination_codes,
)
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import Overworld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.cave_shuffle import (
    ANY_ROAD_CAVES_OFF_FLAGS,
    BOTH_PARTS,
    DOORS_ONLY,
    DUNGEON_DOORS_ONLY_FLAGS,
    NO_WALK,
    NON_DUNGEON_CAVES_ONLY_FLAGS,
    NON_DUNGEON_ONLY,
    RANDOM_CAVES_FLAGS,
    VANILLA_CAVES_FLAGS,
    WOOD_SWORD_CAVE_OFF_FLAGS,
    any_road_caves_at_home,
    fixed_screens_kept,
    walk_parts,
    wood_sword_placement,
)
from zora_measure.checkpoints.overworld import destinations_changed, start_room_ban
from zora_measure.checkpoints.start_rooms import start_room_on_own_door

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEEDS = (1, 2, 3, 4)
WOOD_SWORD_HOME = 119
# OW-CAVE-09: the PRG0 screens of the nine enrolled doors ($05, $0B, $22, $37, $3C, $42, $45, $6D, $74)
ENROLLED_DOOR_SCREENS = (5, 11, 34, 55, 60, 66, 69, 109, 116)
# OW-CAVE-12: PRG0's list order, 123 last (OW-CAVE-02 step 2 not made)
PRG0_ORDER = (*ENROLLED_SCREENS[:WOOD_SWORD_LIST_INDEX], WOOD_SWORD_HOME,
              *ENROLLED_SCREENS[WOOD_SWORD_LIST_INDEX + 1:-1], 123)


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _finished(flags: str, seed: int) -> GameWorld:
    return parse_rom(generate_rom(flags, seed, _base()).rom)


def _prg0_overworld() -> Overworld:
    return parse_rom(_base()).overworld


# --- Shuffle Wood Sword Cave off (B02 = 0, OW-CAVE-12) ----------------------------------------------

def test_b02_off_and_its_random_are_supported() -> None:
    """FL-SUP-03: B02 off is supported, and since the beta 8 export its "?" too (OW-CAVE-12: resolved
    before FL-DEP-02 rule 1, whose coin then applies)."""
    off = decode(WOOD_SWORD_CAVE_OFF_FLAGS)
    assert support(off)["B02"] is Support.SUPPORTED
    possible = off.updated(toggles={"B02": ThreeState.POSSIBLE})
    assert support(possible)["B02"] is Support.SUPPORTED
    assert plan(encode(possible), 1).flag_string == encode(possible)


def test_b02_off_list_keeps_prg0_order() -> None:
    """OW-CAVE-12: without code 16, OW-CAVE-02 step 2 makes no exchange: the list is PRG0's order."""
    entries = leave_wood_sword_cave_in_place(enrolled_entries(_prg0_overworld()))
    assert tuple(entry.screen for entry in entries) == PRG0_ORDER


@pytest.mark.parametrize("positions", [FIRST_QUEST_SECRET_POSITIONS, SECOND_QUEST_DEALT_POSITIONS],
                         ids=["mixed", "mixed, second-quest variant"])
def test_b02_off_undoes_the_exchange_in_the_mixed_lists(positions: tuple[int, ...]) -> None:
    """The mixed lists put the last dealt pair in the wooden-sword entry's place; it goes back last."""
    exchanged = mixed_quest_entries(_prg0_overworld(), Rng(5), positions)
    entries = leave_wood_sword_cave_in_place(exchanged)
    assert entries[WOOD_SWORD_LIST_INDEX].screen == WOOD_SWORD_HOME
    assert entries[-1] is exchanged[WOOD_SWORD_LIST_INDEX]
    assert [entry.screen for entry in entries if entry.screen != WOOD_SWORD_HOME] == \
        [entry.screen for entry in exchanged[:WOOD_SWORD_LIST_INDEX] + exchanged[WOOD_SWORD_LIST_INDEX + 1:-1]
         + [exchanged[WOOD_SWORD_LIST_INDEX]]]


def test_b02_off_undoes_the_exchange_in_the_second_quest_list() -> None:
    """OW-QST-03: step 2 exchanged the wooden-sword entry with the last (114); 114 goes back last."""
    entries = leave_wood_sword_cave_in_place(second_quest_entries(_prg0_overworld()))
    assert entries[-1].screen == 114
    screens = [entry.screen for entry in entries]
    assert screens.index(WOOD_SWORD_HOME) == WOOD_SWORD_LIST_INDEX - 2     # 11 and 66 are not entries


@pytest.mark.parametrize("seed", SEEDS)
def test_b02_off_finished_roms(seed: int) -> None:
    """OW-CAVE-12's Check: code 16 on $77; the fixed screens keep their bytes; no door on S(d)."""
    gw = _finished(WOOD_SWORD_CAVE_OFF_FLAGS, seed)
    assert wood_sword_placement(gw) == {"on A3": True, "on $77": True}
    assert fixed_screens_kept(gw)
    assert start_room_ban(gw) == (9, 9)
    assert 59 <= destinations_changed(gw) <= 72


def test_wood_sword_set_holds_its_home() -> None:
    assert WOOD_SWORD_HOME in WOOD_SWORD_SCREENS and WOOD_SWORD_HOME not in FIXED_SCREENS
    assert _prg0_overworld().screens[WOOD_SWORD_HOME].destination == Destination.WOOD_SWORD_CAVE


# --- Cave Shuffle's walk parts (OW-CAVE-09) and FL-DEP-02 rule 1's coin (OW-CAVE-10) ---------------

NO_BAN = dict.fromkeys(range(1, 10), 0x7F)       # start rooms on no entry's screen


def _walked(parts: CaveWalkParts, seed: int) -> tuple[list[int], list[int]]:
    """The entries' codes before and after a walk with these parts (PRG0's list, no Armos move)."""
    entries = enrolled_entries(_prg0_overworld())
    before = [int(entry.code) for entry in entries]
    walk_destination_codes(entries, NO_BAN, Rng(seed), parts=parts)
    return before, [int(entry.code) for entry in entries]


def _is_door(code: int) -> bool:
    return 1 <= code <= 9


@pytest.mark.parametrize("seed", range(8))
def test_dungeon_part_only_permutes_the_doors(seed: int) -> None:
    """OW-CAVE-09, C05 = 1: the nine doors are permuted among their PRG0 screens; every other code,
    16 and 20 included, keeps its screen."""
    before, after = _walked(CaveWalkParts(dungeon_doors=True, non_dungeon_caves=False), seed)
    assert all(a == b for a, b in zip(before, after, strict=True) if not _is_door(b))
    assert sorted(code for code in after if _is_door(code)) == list(range(1, 10))
    assert all(_is_door(a) for a, b in zip(before, after, strict=True) if _is_door(b))


@pytest.mark.parametrize("seed", range(8))
def test_non_dungeon_part_only_moves_no_door_but_by_the_wood_sword_exchange(seed: int) -> None:
    """OW-CAVE-09, C05 = 2: only codes above 9 move, except that the wooden-sword visit may exchange
    with a door on an A3 screen, which then stands on $77."""
    entries = enrolled_entries(_prg0_overworld())
    before = {entry.screen: int(entry.code) for entry in entries}
    walk_destination_codes(entries, NO_BAN, Rng(seed), parts=CaveWalkParts(dungeon_doors=False))
    moved_doors = {entry.screen: int(entry.code) for entry in entries
                   if _is_door(before[entry.screen]) != _is_door(int(entry.code))}
    assert not moved_doors or (len(moved_doors) == 2 and _is_door(moved_doors[WOOD_SWORD_HOME])
                               and int(Destination.WOOD_SWORD_CAVE) in moved_doors.values())
    assert all(int(entry.code) == before[entry.screen] for entry in entries
               if _is_door(before[entry.screen]) and entry.screen not in moved_doors)


def test_the_wood_sword_exchange_reaches_a_door_under_non_dungeon_only() -> None:
    """OW-CAVE-09's quirk: some seeds put a door on $77 (184 of 1,000 in the corpus)."""
    doors_on_home = 0
    for seed in range(200):
        entries = enrolled_entries(_prg0_overworld())
        walk_destination_codes(entries, NO_BAN, Rng(seed), parts=CaveWalkParts(dungeon_doors=False))
        doors_on_home += any(entry.screen == WOOD_SWORD_HOME and _is_door(int(entry.code)) for entry in entries)
    assert 15 < doors_on_home < 70


def test_neither_part_skips_the_walk() -> None:
    """OW-CAVE-09, C05 = 0: step 3 is skipped; no draw."""
    before, after = _walked(CaveWalkParts(dungeon_doors=False, non_dungeon_caves=False), 1)
    assert before == after


def test_the_parts_of_each_value() -> None:
    """OW-CAVE-09: C05's parts; a mixed overworld quest turns the non-dungeon part on."""
    parts = {value: cave_walk_parts(value, mixed_overworld_quest=False) for value in
             (CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.NON_DUNGEON_CAVES_ONLY,
              CaveShuffle.ALL_CAVES)}
    assert [(p.dungeon_doors, p.non_dungeon_caves) for p in parts.values()] == \
        [(False, False), (True, False), (False, True), (True, True)]
    assert cave_walk_parts(CaveShuffle.VANILLA, mixed_overworld_quest=True) == CaveWalkParts(False, True)
    assert cave_walk_parts(CaveShuffle.ALL_CAVES, mixed_overworld_quest=False) == ALL_CAVES_WALK


def _coin_side(flags: str, seed: int) -> CaveShuffle:
    """The C05 the generator saw after FL-DEP-02 rule 1's coin."""
    return plan(flags, seed).alternatives.cave_shuffle


@pytest.mark.parametrize("seed", SEEDS)
def test_vanilla_caves_finished_roms(seed: int) -> None:
    """OW-CAVE-09 and OW-CAVE-10, C05 = 0 with B02 and B04 on: the coin either turns the non-dungeon
    part on (the ROM shows that walk) or B02 and B04 off (no walk: the cave table is PRG0's apart
    from the Armos re-pointing)."""
    gw = _finished(VANILLA_CAVES_FLAGS, seed)
    side = _coin_side(VANILLA_CAVES_FLAGS, seed)
    assert side in (CaveShuffle.VANILLA, CaveShuffle.NON_DUNGEON_CAVES_ONLY)
    chosen = plan(VANILLA_CAVES_FLAGS, seed).settings
    if side == CaveShuffle.VANILLA:
        assert not chosen.is_on("B02") and not chosen.is_on("B04")
        assert walk_parts(gw) == NO_WALK
    else:
        assert chosen.is_on("B02") and chosen.is_on("B04")
        assert walk_parts(gw) == NON_DUNGEON_ONLY
    assert fixed_screens_kept(gw) and start_room_ban(gw) == (9, 9) and not start_room_on_own_door(gw)


def test_the_coin_is_equal_chance_and_leaves_the_baseline_alone() -> None:
    """OW-CAVE-10: about half of the seeds take each side; the MVP baseline (C05 = 3) flips none."""
    sides = Counter(_coin_side(VANILLA_CAVES_FLAGS, seed) for seed in range(200))
    assert 70 < sides[CaveShuffle.NON_DUNGEON_CAVES_ONLY] < 130, sides
    assert {plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed).alternatives.cave_shuffle for seed in range(20)} == \
        {CaveShuffle.ALL_CAVES}


def test_vanilla_caves_with_b02_and_b04_off_flips_no_coin() -> None:
    """FL-DEP-02 rule 1 applies only with B02 or B04 on."""
    settings = decode(VANILLA_CAVES_FLAGS).updated(toggles={"B02": ThreeState.OFF, "B04": ThreeState.OFF})
    assert {plan(encode(settings), seed).alternatives.cave_shuffle for seed in range(20)} == {CaveShuffle.VANILLA}


@pytest.mark.parametrize("seed", SEEDS)
def test_dungeon_doors_only_finished_roms(seed: int) -> None:
    """OW-CAVE-09 and OW-CAVE-10, C05 = 1 with B02 and B04 on: the coin either adds the non-dungeon
    part (C05 = 3's walk) or turns B02 and B04 off (only the doors move, among the nine enrolled
    door screens, which then hold the nine dungeon codes)."""
    gw = _finished(DUNGEON_DOORS_ONLY_FLAGS, seed)
    side = _coin_side(DUNGEON_DOORS_ONLY_FLAGS, seed)
    assert side in (CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.ALL_CAVES)
    if side == CaveShuffle.DUNGEON_DOORS_ONLY:
        assert walk_parts(gw) in (DOORS_ONLY, NO_WALK)
        codes = [int(screen.destination) for screen in gw.overworld.screens]
        assert sorted(codes[screen] for screen in ENROLLED_DOOR_SCREENS) == list(range(1, 10))
        assert wood_sword_placement(gw)["on $77"]
    else:
        assert walk_parts(gw) == BOTH_PARTS
    assert fixed_screens_kept(gw) and start_room_ban(gw) == (9, 9) and not start_room_on_own_door(gw)


@pytest.mark.parametrize("seed", SEEDS)
def test_non_dungeon_caves_only_finished_roms(seed: int) -> None:
    """OW-CAVE-09, C05 = 2: no coin; only codes above 9 move, but for the wooden-sword cave's
    exchange with a door on an A3 screen; code 16 on an A3 screen."""
    gw = _finished(NON_DUNGEON_CAVES_ONLY_FLAGS, seed)
    assert _coin_side(NON_DUNGEON_CAVES_ONLY_FLAGS, seed) == CaveShuffle.NON_DUNGEON_CAVES_ONLY
    assert walk_parts(gw) == NON_DUNGEON_ONLY
    assert wood_sword_placement(gw)["on A3"]
    assert fixed_screens_kept(gw) and start_room_ban(gw) == (9, 9) and not start_room_on_own_door(gw)


E9_SEED = 47       # the first seed of C05 = 2 whose passes E9 rejects (once; seed 33, twice, until 114f280)


def test_e9_rejects_level_3_starting_on_its_door() -> None:
    """VA-REJ-21 under C05 = 0 and 2: the enrolled doors keep their PRG0 screens, so a level 3 whose
    start room is $74 meets its own door and the pass is rejected (E9); no shipped ROM has it."""
    from zora.generate.pipeline import build
    built = build(plan(NON_DUNGEON_CAVES_ONLY_FLAGS, E9_SEED), _base())
    assert built.result.acceptance_rejections["E9"] == 1
    assert not start_room_on_own_door(built.world)


def test_random_cave_shuffle_draws_each_value() -> None:
    """OW-CAVE-11: C05 = 4 resolves to 0, 1, 2 or 3 with equal chance, then the coin of OW-CAVE-10
    when it is 0 or 1 (B02 and B04 on: 0 may run as 2, 1 as 3)."""
    assert support(decode(RANDOM_CAVES_FLAGS))["C05"] is Support.SUPPORTED
    drawn = Counter(decode_resolved_cave_shuffle(seed) for seed in range(400))
    assert set(drawn) == {CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.NON_DUNGEON_CAVES_ONLY,
                          CaveShuffle.ALL_CAVES}
    assert all(60 < count < 140 for count in drawn.values()), drawn
    seen = Counter(_coin_side(RANDOM_CAVES_FLAGS, seed) for seed in range(400))
    assert seen[CaveShuffle.NON_DUNGEON_CAVES_ONLY] + seen[CaveShuffle.ALL_CAVES] > 250, seen   # 5/8 expected


def decode_resolved_cave_shuffle(seed: int) -> CaveShuffle:
    """C05 after FL-DEP-04's draw, before the coin."""
    from zora.generate.pipeline import resolve_question_marks
    settings = decode(RANDOM_CAVES_FLAGS)
    return CaveShuffle(resolve_question_marks(settings, seed, encode(settings)).option("C05"))


@pytest.mark.parametrize("seed", SEEDS)
def test_random_cave_shuffle_finished_roms(seed: int) -> None:
    gw = _finished(RANDOM_CAVES_FLAGS, seed)
    expected = {CaveShuffle.VANILLA: {NO_WALK}, CaveShuffle.DUNGEON_DOORS_ONLY: {DOORS_ONLY, NO_WALK},
                CaveShuffle.NON_DUNGEON_CAVES_ONLY: {NON_DUNGEON_ONLY}, CaveShuffle.ALL_CAVES: {BOTH_PARTS}}
    assert walk_parts(gw) in expected[_coin_side(RANDOM_CAVES_FLAGS, seed)]
    assert fixed_screens_kept(gw) and start_room_ban(gw) == (9, 9) and not start_room_on_own_door(gw)


# --- With the overworld quests (OW-CAVE-09, OW-MIX-05 step 1, OW-MIX-07, OW-QST-03) -----------------

def _with(flags: str, **options: int) -> str:
    """A corpus string with option fields changed and B02 and B04 off (no coin)."""
    settings = decode(flags).updated(options=options, toggles={"B02": ThreeState.OFF, "B04": ThreeState.OFF})
    return encode(settings)


@pytest.mark.parametrize("quest", [2, 3], ids=["mixed", "mixed, second-quest variant"])
def test_a_mixed_overworld_walks_the_non_dungeon_caves_under_vanilla(quest: int) -> None:
    """OW-MIX-05 step 1: a mixed overworld quest turns the non-dungeon part on whatever C05 says."""
    flags = _with(VANILLA_CAVES_FLAGS, C01=quest)
    for seed in (1, 2):
        assert plan(flags, seed).alternatives.cave_shuffle == CaveShuffle.VANILLA
        assert destinations_changed(_finished(flags, seed)) > 40


def test_the_second_quest_overworld_keeps_vanilla_caves() -> None:
    """OW-QST-03: C01 = 1 does not force the non-dungeon part; under C05 = 0 only the seven
    second-quest codes and the Armos re-pointing change cave bytes."""
    flags = _with(VANILLA_CAVES_FLAGS, C01=1)
    for seed in (1, 2):
        assert destinations_changed(_finished(flags, seed)) <= 12


def test_the_coin_still_flips_under_a_mixed_overworld() -> None:
    """OW-MIX-07: the coin reads C05 alone; with C01 = 2 its B02-and-B04-off side leaves the
    wooden-sword cave on $77 although the non-dungeon walk runs."""
    settings = decode(VANILLA_CAVES_FLAGS).updated(options={"C01": 2})
    flags = encode(settings)
    sides = {seed: plan(flags, seed).settings.is_on("B02") for seed in range(12)}
    assert set(sides.values()) == {True, False}
    off_seed = next(seed for seed, on in sides.items() if not on)
    assert wood_sword_placement(_finished(flags, off_seed))["on $77"]


@pytest.mark.parametrize("cave_shuffle", [CaveShuffle.NON_DUNGEON_CAVES_ONLY, CaveShuffle.ALL_CAVES])
def test_any_road_caves_off_with_each_walking_value(cave_shuffle: CaveShuffle) -> None:
    """OW-CAVE-12 (B04 off, ZORA's own value since 2026-10-07) under C05 = 2 and 3: the take-any-road
    caves, their record and F bytes stay PRG0's while the other non-dungeon caves move."""
    flags = encode(decode(ANY_ROAD_CAVES_OFF_FLAGS).updated(options={"C05": cave_shuffle}))
    for seed in (1, 2):
        gw = _finished(flags, seed)
        assert any_road_caves_at_home(gw) and fixed_screens_kept(gw)
        assert walk_parts(gw) == (NON_DUNGEON_ONLY if cave_shuffle == CaveShuffle.NON_DUNGEON_CAVES_ONLY
                                  else BOTH_PARTS)
