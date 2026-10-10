"""The recompute of item-dependent outputs (R3; zora/generate/finish.py, docs/archipelago.md):
Archipelago Phase 2 tests 3 (with the recompute on), 7 and 8.
  3. a permuted assignment lands where it should and changes no byte outside the item bytes,
     the prices, the hint text regions, the seed code, the one-time wares and the remap;
  7. FINISH is deterministic: the same build and assignment give the same bytes twice, and in a
     fresh process;
  8. the recompute list is complete: changing one assigned item changes only that item's byte
     and outputs on the R3 list.
Also: with BUILD's own draws, the hint text FINISH composes for the identity assignment is
exactly BUILD's (so nothing a later BUILD step writes leaks into the recomposed text)."""
import copy
import subprocess
import sys
from pathlib import Path

import pytest

import zora.generate.generation_pass as generation_pass
from tests.archipelago_cases import FLAG_CASES
from tests.test_assignment import (
    ALLOWED_WITHOUT_RECOMPUTE,
    _built,
    finish_unchecked,
    finish_world_unchecked,
    identity,
    permuted,
    reading,
)
from zora.generate.finish import FOREIGN, Foreign, rebuild_tracking, recompose_hint_text, with_tracking, written_item
from zora.generate.pipeline import Built, build, finish, finish_world, plan
from zora.generate.places import read_item
from zora.generate.rng import Rng
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.layout import (
    CAVE_PRICE_DATA_ADDRESS,
    EXT_HINT_DATA_ROM_END,
    EXT_HINT_DATA_ROM_START,
    HINT_SHOP_QUOTES_ADDRESS,
    OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS,
    QUOTE_DATA_ADDRESS,
    REFUSAL_TEXT_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE,
)
from zora.rom.parse.rom_file import parse_rom

REPO = Path(__file__).resolve().parent.parent
SEEDS = (1, 2, 3)
CAVE_TABLE_SIZE = 20 * 3
HINT_SHOP_OFFERS = 6
WHITE_SWORD_SELECTOR_OFFSET = 2

# The R3 list's ROM regions besides the item bytes (docs/archipelago.md): the cave prices, and
# the hint text's pointers, bodies and selector tables.
R3_REGIONS = (set(range(CAVE_PRICE_DATA_ADDRESS, CAVE_PRICE_DATA_ADDRESS + CAVE_TABLE_SIZE))
              | set(range(QUOTE_DATA_ADDRESS, REFUSAL_TEXT_ADDRESS))
              | set(range(EXT_HINT_DATA_ROM_START, EXT_HINT_DATA_ROM_END))
              | {OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + WHITE_SWORD_SELECTOR_OFFSET}
              | set(range(HINT_SHOP_QUOTES_ADDRESS, HINT_SHOP_QUOTES_ADDRESS + HINT_SHOP_OFFERS))
              | set(range(UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
                          UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS + UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE))
              | set(range(UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
                          UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS + UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE)))
ALLOWED = ALLOWED_WITHOUT_RECOMPUTE | R3_REGIONS


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def _changed(before: bytes, after: bytes) -> set[int]:
    return {offset for offset, (old, new) in enumerate(zip(before, after, strict=True)) if old != new}


# --- test 3, with the recompute on --------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_a_permuted_assignment_with_the_recompute(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    assignment = permuted(built, seed)
    _, finished = finish_world_unchecked(built, assignment)
    rom = finish_unchecked(built, base, assignment)
    parsed = parse_rom(rom, reading(finished.config))
    assert [read_item(parsed, place) for place in built.places] == [written_item(assignment[place.name])
                                                                       for place in built.places]
    changed = _changed(finish(built, base), rom)
    assert changed <= ALLOWED, sorted(hex(offset) for offset in changed - ALLOWED)


# --- test 7: FINISH is deterministic ------------------------------------------------------------

FRESH = """
import hashlib, sys
sys.path.insert(0, {repo!r})
from tests.archipelago_cases import FLAG_CASES
from tests.test_assignment import permuted
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import remember_repo_base_rom
base = remember_repo_base_rom()
flags, zora = FLAG_CASES[{case!r}]
built = build(plan(flags, {seed}, zora), base)
print(hashlib.sha1(finish(built, base, permuted(built, {seed}), check=False)).hexdigest())
"""


@pytest.mark.parametrize("case", ["baseline", "every ZORA flag on"])
def test_finish_is_deterministic(base: bytes, case: str) -> None:
    import hashlib
    built = _built(case, 2)
    assignment = permuted(built, 2)
    rom = finish_unchecked(built, base, assignment)
    assert finish_unchecked(built, base, assignment) == rom
    rebuilt = build(plan(*FLAG_CASES[case][:1], 2, FLAG_CASES[case][1]), base)
    assert finish_unchecked(rebuilt, base, assignment) == rom
    fresh = subprocess.run([sys.executable, "-c", FRESH.format(repo=str(REPO), case=case, seed=2)],
                           capture_output=True, text=True, cwd=REPO, check=False)
    assert fresh.returncode == 0, fresh.stderr
    assert fresh.stdout.strip() == hashlib.sha1(rom).hexdigest()


# --- test 8: the recompute list is complete -----------------------------------------------------

def _alternatives(built: Built, name: str, assignment: dict[str, Item | Foreign]) -> list[Item | Foreign]:
    """Other values the place may take: another pool item it does not forbid, and FOREIGN."""
    place = next(place for place in built.places if place.name == name)
    current = assignment[name]
    others = [item for item in dict.fromkeys(read_item(built.world, place) for place in built.places)
              if item != current and item not in place.forbids]
    return [*others[:1], FOREIGN]


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_changing_one_item_changes_only_r3_outputs(base: bytes, case: str, seed: int) -> None:
    built = _built(case, seed)
    assignment = permuted(built, seed)
    rom = finish_unchecked(built, base, assignment)
    for place in built.places:
        for value in _alternatives(built, place.name, assignment):
            changed = _changed(rom, finish_unchecked(built, base, {**assignment, place.name: value}))
            assert changed <= ALLOWED, (place.name, value, sorted(hex(offset) for offset in changed - ALLOWED))


# --- the recomposed hint text, with BUILD's own draws ---------------------------------------------

HINT_FIELDS = ("quotes", "hint_pointers", "hint_text_bytes", "white_sword_text_selector", "hint_shop_offer_selectors",
               "underworld_text_selectors_a", "underworld_text_selectors_b", "hint_overlay_flags")


def _hint_shop_prices(world: GameWorld) -> list[int]:
    from zora.generate.steps.hint_text import hint_shop_prices
    return hint_shop_prices(world)


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_recomposed_hint_text_with_builds_draws_is_builds(base: bytes, case: str,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    streams: list[Rng] = []
    original = generation_pass.compose_hint_text

    def recording(*args, **kwargs):
        streams.append(copy.deepcopy(args[3]))       # the stream as the hint step finds it
        return original(*args, **kwargs)

    monkeypatch.setattr(generation_pass, "compose_hint_text", recording)
    flag_string, zora_flag_string = FLAG_CASES[case]
    built = build(plan(flag_string, 5, zora_flag_string), base)
    monkeypatch.undo()
    world = copy.deepcopy(built.world)
    assert built.result.item_shuffle_result is not None
    state = with_tracking(built.result.item_shuffle_result, rebuild_tracking(world, built), world, built.places)
    recompose_hint_text(world, built, state, streams[-1])
    for field in HINT_FIELDS:
        assert getattr(world, field) == getattr(built.world, field), field
    assert _hint_shop_prices(world) == _hint_shop_prices(built.world)
    assert finish_unchecked(built, base, identity(built), recompute=False) == finish(built, base)


# --- the recompute follows the new items ----------------------------------------------------------

def _swap_into(built: Built, name: str, item: Item) -> dict[str, Item | Foreign]:
    """The identity assignment with `item` moved into the named place, and that place's item moved
    to where `item` was."""
    assignment = identity(built)
    source = next(place.name for place in built.places if assignment[place.name] == item)
    assignment[source], assignment[name] = assignment[name], item
    return assignment


def test_the_hint_text_names_the_white_sword_caves_new_item(base: bytes) -> None:
    from zora.generate.steps.hint_text import ITEM_NAMES, REGION_PHRASES
    named = 0
    for seed in range(1, 9):
        built = _built("baseline", seed)
        cave = next(place for place in built.places if place.name == "White Sword Cave")
        item = next(item for item in (Item.RAFT, Item.RECORDER) if read_item(built.world, cave) != item)
        world, _ = finish_world_unchecked(built, _swap_into(built, "White Sword Cave", item))
        named += any(f"THE {ITEM_NAMES[item]} {phrase}" in quote.text.replace("|", " ")
                     for quote in world.quotes for phrase in REGION_PHRASES.values())
    assert named > 0


def test_the_prices_follow_the_items(base: bytes) -> None:
    from zora.generate.places import PlaceKind
    from zora.model.overworld import Shop
    built = _built("every ZORA flag on", 1)
    extras = built.result.extra_pool_items
    assert extras is not None
    wares = [place for place in built.places if place.kind == PlaceKind.SHOP_WARE]
    potion = next(place for place in built.places if place.kind == PlaceKind.POTION_SHOP)
    assert wares[0].destination is not None and potion.destination is not None
    expected = {Item.LADDER: range(60, 81), Item.BOOK: range(200, 241), Item.HEART_CONTAINER: range(20, 41),
                Item.LETTER: range(20, 41), Item.BLUE_POTION: range(25, 56)}
    for item, prices in expected.items():
        assignment = _swap_into(built, wares[0].name, item)
        world, _ = finish_world_unchecked(built, assignment)
        shop = world.overworld.get_cave(wares[0].destination, Shop)
        assert shop is not None and wares[0].position is not None
        assert shop.ware(wares[0].position).price in prices, item
    # another player's item keeps the ware's price from before SI-PRICE-01
    world, _ = finish_world_unchecked(built, {**identity(built), potion.name: FOREIGN})
    shop = world.overworld.get_cave(potion.destination, Shop)
    assert shop is not None and potion.position is not None
    own = [ware.shop.destination for ware in extras.shop_wares].index(potion.destination)
    assert shop.ware(potion.position).price == extras.slot_prices[own]


def test_an_all_foreign_world_tracks_nothing(base: bytes) -> None:
    built = _built("every ZORA flag on", 2)
    _, finished = finish_world_unchecked(built, {place.name: FOREIGN for place in built.places})
    assert finished.tracking.tracked == []
    assert built.result.item_shuffle_result is not None
    assert len(finished.tracking.elsewhere) >= len(built.result.item_shuffle_result.tracked)
