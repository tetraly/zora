"""No hint is about a level's Triforce piece, map or compass (owner ruling, 2026-11-23; a tester on 2.0.2's test build
got a hint for a Triforce piece). With Add Triforces or Add Maps/Compasses to the Item Pool on they are items
(docs/design/archipelago-items.md piece 6), and every hint source leaves them out, in Archipelago and single player:

- the requirement texts' tracked records (door, inside-dungeon and boss forms; Deception's too): hinted_level_records
  and deceiving_requirement_candidates skip them (UNHINTED_ITEMS), and the draw takes other candidates;
- the White Sword Cave's and the coast's requirement candidates: none when the place holds one;
- the White Sword Cave's holder text: "THE ITEM" for the cave's item, and Deception's pick never draws one;
- the level-9 trio: with Add Maps/Compasses on, level 9's compass is an item and its guardian's text is left out;
- another player's item named in a hint (hinted_foreign_places): never another ZORA player's "Level 3 Triforce".

Seeds with neither switch are unchanged (the quick check's output comparison). Level 9's gate text ("YOU NEED EIGHT
TRIFORCE PIECES.") says what the gate asks for, not where an item is, and stays."""
import copy
import re
from dataclasses import replace
from functools import cache
from types import SimpleNamespace

import pytest

from tests.needs import needs_base_rom
from tests.test_solo_level_items import z1r
from zora import archipelago
from zora.flags.codec import decode as decode_z1r
from zora.flags.codec import encode as encode_z1r
from zora.flags.fields import HINT_STYLE, HintStyle, ItemShuffleScope, ThreeState
from zora.flags.zora_flags import LevelItemShuffle, ZoraFlags, encode
from zora.generate import pipeline
from zora.generate.finish import FOREIGN as FOREIGN_VALUE
from zora.generate.finish import hinted_foreign_places
from zora.generate.steps.hint_text import (
    HOLDER_SLOT,
    LEVEL_ITEM_CODES,
    SLOT_COUNT,
    Deception,
    Form,
    deceiving_requirement_candidates,
    hinted_level_records,
    requirement_candidates,
    write_person_name_texts,
)
from zora.generate.rng import Rng
from zora.generate.steps.item_shuffle_result import ItemShuffleResult, TrackedPlace
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, OverworldItem
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

SEEDS = (1, 2)
SWITCHES = {"triforces": (True, False), "maps/compasses": (False, True), "both": (True, True)}
HINT_STYLES = {"helpful": HintStyle.HELPFUL, "deception": HintStyle.DECEPTIVE}
# A hint naming one: "THE TRIFORCE PIECE WAITS IN LEVEL-3.", "THE ELDER HAS THE MAP ...", "THE COMPASS IS GUARDED ..."
NAMES_ONE = re.compile(r"TRIFORCE PIECE(?!S)|\bMAP\b|COMPASS")
LEVEL_ITEMS_SAMPLE = (Item.TRIFORCE_3, Item.MAP_5, Item.COMPASS_2, Item.TRIFORCE, Item.MAP, Item.COMPASS)


def zora_string(switches: str) -> str:
    triforces, maps = SWITCHES[switches]
    return encode(ZoraFlags(triforce_shuffle=LevelItemShuffle.ANYWHERE if triforces else LevelItemShuffle.OFF,
                            map_compass_shuffle=LevelItemShuffle.ANYWHERE if maps else LevelItemShuffle.OFF))


def with_hint_style(flags: str, style: str) -> str:
    return encode_z1r(decode_z1r(flags).updated(options={HINT_STYLE.id: int(HINT_STYLES[style])}))


@cache
def hint_quotes(game: str, switches: str, style: str, seed: int) -> tuple[str, ...]:
    """The quotes of a finished ROM: an Archipelago game with BUILD's own placement as the multiworld's, or a
    single-player seed under Item Shuffle: Full, whose swaps move the level items."""
    base = remember_repo_base_rom()
    zora = zora_string(switches)
    if game == "archipelago":
        flags = with_hint_style(archipelago.DEFAULT_FLAGS, style)
        result = archipelago.build_from_strings(flags, zora, seed, base)
        fill = {place.name: item for place, item in zip(result.places, result.pool, strict=True)}
        world = parse_rom(archipelago.finish(result, fill))
    else:
        flags = with_hint_style(z1r(ItemShuffleScope.FULL), style)
        rom = pipeline.generate_rom(flags, seed, base, zora_flag_string=zora).rom
        world = parse_rom(rom, pipeline.plan(flags, seed, zora).config)
    return tuple(quote.text for quote in world.quotes)


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("style", HINT_STYLES)
@pytest.mark.parametrize("switches", SWITCHES)
@pytest.mark.parametrize("game", ["archipelago", "single player"])
def test_no_hint_names_a_piece_map_or_compass(game: str, switches: str, style: str, seed: int) -> None:
    """Before the ruling these seeds named them: "THE TRIFORCE PIECE WAITS IN LEVEL-2.", "THE ELDER HAS THE MAP NEAR
    START FOR 4 HEARTS", "THE TRIFORCE PIECE NEEDS THE LADDER", "THE COMPASS HAS NO GUARDIAN"."""
    named = [text for text in hint_quotes(game, switches, style, seed) if NAMES_ONE.search(text)]
    if not SWITCHES[switches][1]:
        # level 9's compass is no item: the trio's text about its guardian stays, as in every seed
        named = [text for text in named if "COMPASS IS GUARDED" not in text and "COMPASS HAS" not in text]
    assert named == [], (game, switches, style, seed)


# --- each source on its own ------------------------------------------------------------------------------------


# A seed whose White Sword Cave stands where a means is needed, so the cave forms a requirement candidate
CANDIDATE_SEED = 3


@cache
def _world() -> GameWorld:
    built = pipeline.build(pipeline.plan(z1r(ItemShuffleScope.FULL), CANDIDATE_SEED, zora_string("both")),
                           remember_repo_base_rom())
    return built.world


def world_holding(white_sword: Item, coast: Item) -> GameWorld:
    world = copy.deepcopy(_world())
    cave = world.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    coast_place = world.overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    assert cave is not None and coast_place is not None
    cave.item, coast_place.item = white_sword, coast
    return world


def records(items: tuple[Item, ...]) -> list[TrackedPlace]:
    """Each item tracked in a level, with the Bow and the Raft beside them."""
    return [TrackedPlace(item, level=level) for level, item in enumerate((*items, Item.BOW, Item.RAFT), start=1)
            if level <= 8]


def state_tracking(tracked: list[TrackedPlace]) -> ItemShuffleResult:
    return replace(ItemShuffleResult(), tracked=tracked)


@pytest.mark.parametrize("item", LEVEL_ITEMS_SAMPLE, ids=lambda item: item.name)
def test_the_requirement_texts_skip_tracked_level_items(item: Item) -> None:
    kept = hinted_level_records(state_tracking(records((item,))))
    assert [record.item for record in kept] == [Item.BOW, Item.RAFT]


@needs_base_rom
@pytest.mark.parametrize("item", LEVEL_ITEMS_SAMPLE, ids=lambda item: item.name)
def test_no_requirement_candidate_names_a_level_item(item: Item) -> None:
    """The White Sword Cave and the coast holding one, and one tracked in a level: no candidate names it; the
    Bow tracked beside it still forms candidates."""
    world = world_holding(item, item)
    level_records = [record for record in records((item,)) if record.item not in LEVEL_ITEM_CODES]
    candidates = requirement_candidates(world, [(record.item, record.level) for record in level_records
                                                if record.level is not None], records=level_records)
    assert all(candidate.item not in LEVEL_ITEM_CODES for candidate in candidates)
    assert not any(candidate.white_sword_cave for candidate in candidates)
    assert not any(candidate.form == Form.LADDER and candidate.item is not None for candidate in candidates)
    assert any(candidate.item == Item.BOW for candidate in candidates)
    deceiving = deceiving_requirement_candidates(world, state_tracking(records((item,))), Deception(Rng(1), False))
    assert all(candidate.item not in LEVEL_ITEM_CODES for candidate in deceiving)
    assert any(candidate.item == Item.BOW for candidate in deceiving)


@needs_base_rom
def test_the_coast_and_white_sword_cave_still_name_other_items() -> None:
    candidates = requirement_candidates(world_holding(Item.LADDER, Item.RAFT), [])
    assert any(candidate.white_sword_cave and candidate.item == Item.LADDER for candidate in candidates)
    assert any(candidate.form == Form.LADDER and candidate.item == Item.RAFT for candidate in candidates)


@needs_base_rom
@pytest.mark.parametrize("item", LEVEL_ITEMS_SAMPLE, ids=lambda item: item.name)
def test_the_holder_text_leaves_a_level_item_unnamed(item: Item) -> None:
    texts: list[list[str] | None] = [None] * SLOT_COUNT
    write_person_name_texts(world_holding(item, Item.RAFT), texts)
    text = " ".join(texts[HOLDER_SLOT] or [])
    assert "THE ITEM" in text and not NAMES_ONE.search(text), text
    write_person_name_texts(world_holding(Item.BOW, Item.RAFT), texts)
    assert "THE BOW" in " ".join(texts[HOLDER_SLOT] or [])


# --- another player's item ---------------------------------------------------------------------------------------

PLACES = [SimpleNamespace(name="L2 a", level=2), SimpleNamespace(name="L3 a", level=3),
          SimpleNamespace(name="Coast", level=None), SimpleNamespace(name="White Sword Cave", level=None)]
ALL_FOREIGN = {place.name: FOREIGN_VALUE for place in PLACES}


@pytest.mark.parametrize("name", ["Level 3 Triforce", "Level 9 Map", "Level 1 Compass"])
def test_another_zora_players_level_item_is_never_named(name: str) -> None:
    """Another ZORA player's piece, map or compass in a hinted place: the hint keeps the generic wording."""
    owners = {"L2 a": ("GOB", name), "L3 a": ("GOB", "Hammer"), "Coast": ("GOB", name),
              "White Sword Cave": ("GOB", name)}
    assert hinted_foreign_places(PLACES, ALL_FOREIGN, owners) == {"L3 a": 3}
