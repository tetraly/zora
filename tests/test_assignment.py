"""Assignments (zora/generate/finish.py; Archipelago Phase 2 tests 2, 3 and 9, docs/archipelago.md),
with the recompute of item-dependent outputs off:
  2. the identity assignment gives the ZORA-mode ROM byte for byte, but for the one-time wares:
     External mode sells every ware place once, a re-buyable blue potion there too (Phase 4a;
     GameConfig.one_time_places), so that buying it is a location check;
  3. a permuted assignment lands where it should, and changes no byte outside the item bytes,
     the seed code, the one-time wares and (when it turns on) the $0E remap;
  9. the exclusions and restrictions (R2) hold.
"""
import random
from functools import cache, partial

import pytest

import zora.generate.places as places_module
from tests.archipelago_cases import FLAG_CASES
from zora.generate.finish import FOREIGN, FOREIGN_ITEM, AssignmentRefused, Foreign, one_time_places, written_item
from zora.generate.pipeline import Built, build, finish, finish_world, plan
from zora.generate.places import Place, PlaceKind, is_never_a_place, read_item
from zora.generate.steps import move_last_boss_room_items
from zora.model.enums import Destination, Item, RoomAction
from zora.model.overworld import ItemCave
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import ONE_TIME_WARES, SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.game_config import DungeonNothingCode, GameConfig
from zora.rom.layout import (
    ARMOS_ITEM_ADDRESS,
    ASM_NOTHING_CODE_PATCH_OFFSET,
    CAVE_ITEM_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_TABLE_SIZE,
)
from zora.rom.parse.rom_file import parse_rom

SEEDS = (1, 2, 3, 4)
# These tests write arbitrary permutations, which need not be beatable: the sanity check (R4) is
# tests/test_sanity_check.py's.
finish_unchecked = partial(finish, check=False)
finish_world_unchecked = partial(finish_world, check=False)
CAVE_TABLE_SIZE = 20 * 3            # 20 caves x 3 wares
ITEM_TABLE = 4                      # LevelBlockAttrsE, the room item byte
ONE_TIME_WARES_SIZE = 3


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def _built(case: str, seed: int) -> Built:
    flag_string, zora_flag_string = FLAG_CASES[case]
    return build(plan(flag_string, seed, zora_flag_string), remember_repo_base_rom())


def identity(built: Built) -> dict[str, Item | Foreign]:
    return {place.name: read_item(built.world, place) for place in built.places}


def permuted(built: Built, seed: int) -> dict[str, Item | Foreign]:
    """The built world's items shuffled among its places, respecting each place's forbids."""
    rng = random.Random(seed)
    items: list[Item | Foreign] = [read_item(built.world, place) for place in built.places]
    for _ in range(10_000):
        rng.shuffle(items)
        if all(not isinstance(item, Item) or item not in place.forbids for place, item in zip(built.places, items,
                                                                                              strict=True)):
            return dict(zip((place.name for place in built.places), items, strict=True))
    raise AssertionError("no permutation respects the forbids")


def reading(config: GameConfig) -> GameConfig:
    return GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode)


def item_byte_offsets() -> set[int]:
    """Where the ROM holds item codes: both quest-1 blocks' room item tables, the cave item table
    and the Armos and coast items."""
    offsets = {block + ITEM_TABLE * LEVEL_TABLE_SIZE + room for block in (LEVEL_1_6_DATA_ADDRESS,
                                                                          LEVEL_7_9_DATA_ADDRESS)
               for room in range(LEVEL_TABLE_SIZE)}
    offsets |= set(range(CAVE_ITEM_DATA_ADDRESS, CAVE_ITEM_DATA_ADDRESS + CAVE_TABLE_SIZE))
    return offsets | {ARMOS_ITEM_ADDRESS, COAST_ITEM_ADDRESS}


ALLOWED_WITHOUT_RECOMPUTE = (item_byte_offsets() | set(range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH))
                             | set(range(ONE_TIME_WARES, ONE_TIME_WARES + ONE_TIME_WARES_SIZE))
                             | {ASM_NOTHING_CODE_PATCH_OFFSET})


# --- test 2: the identity assignment is lossless ----------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_identity_assignment_gives_the_zora_mode_rom(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    zora_mode = finish(built, base)
    expected = bytearray(zora_mode)
    for shop_number, position in one_time_places(built.places):
        expected[ONE_TIME_WARES + position] |= 1 << shop_number
    external = bytearray(finish_unchecked(built, base, identity(built), recompute=False))
    if expected != bytearray(zora_mode):            # the seed code hashes the ROM, so it follows
        seed_code = slice(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)
        external[seed_code] = expected[seed_code]
    assert external == expected


# --- test 3: a permuted assignment lands where it should --------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_a_permuted_assignment_lands_where_it_should(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    assignment = permuted(built, seed)
    world, finished = finish_world_unchecked(built, assignment, recompute=False)
    rom = finish_unchecked(built, base, assignment, recompute=False)
    parsed = parse_rom(rom, reading(finished.config))
    assert [read_item(parsed, place) for place in built.places] == [written_item(assignment[place.name])
                                                                       for place in built.places]
    original = finish(built, base)
    changed = {offset for offset, (old, new) in enumerate(zip(original, rom, strict=True)) if old != new}
    assert changed <= ALLOWED_WITHOUT_RECOMPUTE, sorted(hex(offset) for offset in changed - ALLOWED_WITHOUT_RECOMPUTE)
    # the built world is untouched
    assert finish(built, base) == original


def test_foreign_items_show_as_rupees(base: bytes) -> None:
    built = _built("baseline", 1)
    assignment = {place.name: FOREIGN for place in built.places}
    _, finished = finish_world_unchecked(built, assignment, recompute=False)
    parsed = parse_rom(finish_unchecked(built, base, assignment, recompute=False), reading(finished.config))
    assert {read_item(parsed, place) for place in built.places} == {FOREIGN_ITEM}


# --- test 9: exclusions and restrictions (R2) --------------------------------------------------

def test_the_exclusion_is_vareg20s_own_rule() -> None:
    assert getattr(places_module, "is_last_boss_room") is move_last_boss_room_items.is_last_boss_room


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_no_last_boss_ganon_or_zelda_room_is_a_place(case: str, seed: int) -> None:
    built = _built(case, seed)
    never = {(level.level_num, room.room_num) for level in built.world.levels for room in level.rooms
             if is_never_a_place(room)}
    assert any(room.room_action == RoomAction.LAST_BOSS for room in built.world.levels[8].rooms)
    assert not {(place.level, place.room_num) for place in built.places if place.kind == PlaceKind.ROOM} & never


def _place(built: Built, kind: PlaceKind, destination: Destination | None = None) -> Place:
    return next(place for place in built.places
                if place.kind == kind and (destination is None or place.destination == destination))


def _refused(built: Built, base: bytes, assignment: dict[str, Item | Foreign]) -> list[str]:
    with pytest.raises(AssignmentRefused) as refusal:
        finish_unchecked(built, base, assignment)
    return refusal.value.reasons


def test_assignments_breaking_a_rule_are_refused(base: bytes) -> None:
    built = _built("every ZORA flag on", 1)
    ware = _place(built, PlaceKind.SHOP_WARE)
    potion = _place(built, PlaceKind.POTION_SHOP)
    room = _place(built, PlaceKind.ROOM)
    cellar = _place(built, PlaceKind.CELLAR)
    assert _refused(built, base, {potion.name: Item.LETTER}) == [f"{potion.name}: LETTER is forbidden there"]
    assert _refused(built, base, {room.name: Item.TRIFORCE_OF_POWER})
    assert _refused(built, base, {cellar.name: Item.TRIFORCE_OF_POWER})
    assert _refused(built, base, {room.name: Item.MAGICAL_SHIELD}) == [
        f"{room.name}: MAGICAL_SHIELD is not in this seed's major pool"]
    assert _refused(built, base, {"Level 1 Room 7F Cellar": Item.BOW, "Nowhere": Item.BOW})
    # the letter and heart containers anywhere else, and FOREIGN anywhere, are fine
    finish_unchecked(built, base, {ware.name: Item.LETTER, room.name: Item.HEART_CONTAINER, potion.name: FOREIGN})
    finish_unchecked(built, base, {ware.name: Item.HEART_CONTAINER, potion.name: Item.HEART_CONTAINER})


@pytest.mark.parametrize("case", ["baseline", "magical sword and letter"])
def test_a_magical_sword_in_a_dungeon_turns_the_remap_on(base: bytes, case: str) -> None:
    built = _built(case, 2)
    room, cellar = _place(built, PlaceKind.ROOM), _place(built, PlaceKind.CELLAR)
    assignment: dict[str, Item | Foreign] = {room.name: Item.MAGICAL_SWORD, cellar.name: Item.MAGICAL_SWORD}
    if case == "baseline":
        assert built.plan.config.dungeon_nothing_code == DungeonNothingCode.VANILLA
        assignment = {room.name: Item.BOW, cellar.name: Item.BOW}      # no magical sword in this pool
        _, finished = finish_world_unchecked(built, assignment)
        assert finished.config.dungeon_nothing_code == DungeonNothingCode.VANILLA
        return
    _, finished = finish_world_unchecked(built, assignment)
    assert finished.config.dungeon_nothing_code == DungeonNothingCode.ZORA_REMAP
    rom = finish_unchecked(built, base, assignment, recompute=False)
    assert rom[ASM_NOTHING_CODE_PATCH_OFFSET] != base[ASM_NOTHING_CODE_PATCH_OFFSET]
    parsed = parse_rom(rom, reading(finished.config))
    assert read_item(parsed, room) == read_item(parsed, cellar) == Item.MAGICAL_SWORD


def test_the_white_sword_cave_asks_for_its_hearts_whatever_it_holds(base: bytes) -> None:
    built = _built("baseline", 3)
    cave = _place(built, PlaceKind.CAVE, Destination.WHITE_SWORD_CAVE)
    built_cave = built.world.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert built_cave is not None and built_cave.heart_requirement > 0
    assert cave.requires == (places_module.HeartsRequired(built_cave.heart_requirement),)
    for item in (Item.BOW, Item.HEART_CONTAINER, FOREIGN):
        parsed = parse_rom(finish_unchecked(built, base, {cave.name: item}, recompute=False))
        parsed_cave = parsed.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
        assert parsed_cave is not None
        assert parsed_cave.item == written_item(item)
        assert parsed_cave.heart_requirement == built_cave.heart_requirement
