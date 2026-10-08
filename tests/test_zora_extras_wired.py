"""The ZORA extras wired into generation (docs/zora-extras.md; owner requirements
2026-10-04): the ZORA flag string beside the Z1R one, Randomize Magical Sword
with its $0E "no item" code and heart check, and Randomize Letter.

tests/test_zora_extras.py and tests/test_zora_flags.py test the parts without
a full generation; these generate."""
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL, GAME_MODE, GAME_SUBMODE, ITEMS, OBJ_STATE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, ROOM_ITEM_SLOT, Emulator,
    Mode,
)
from zora.flags import form as flag_form
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.context import GenerationResult
from zora.generate.generation_pass import has_magical_sword_hearts
from zora.generate.pipeline import FlagsRefused, GenerationPlan, extra_options, generate_rom, generate_world, plan
from zora.generate.steps.change_sword_hearts import MAGICAL_SWORD_HEARTS
from zora.generate.steps.hint_text import ITEM_ARTICLE, MAGICAL_SWORD_TEXT_SLOT, item_name, magical_sword_cave_words
from zora.generate.steps.item_shuffle_result import EXTRA_SLOT_CAVES
from zora.generate.steps.cave_entries import OverworldResult
from zora.generate.steps.randomize_magical_sword import (
    TAKE_ANY_CAVES_SPENT_ELSEWHERE, has_enough_heart_containers, reachable_take_any_hearts,
    take_any_heart_allowance,
)
from zora.model.enums import Destination, Item, RoomAction
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave
from zora.rom import level_encoding
from zora.rom.base_rom import verify_base_rom
from zora.rom.game_config import DungeonNothingCode
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

FLAGS = MVP_BASELINE_LEVEL_ENCODING_OFF
SWORD = "1.D"            # Randomize Magical Sword, the hearts capped at 12
SWORD_UNCAPPED = "1.1"   # Randomize Magical Sword alone: refused while B10 may ask for 14
LETTER = "1.2"           # Randomize Letter
BOTH = "1.F"             # both, the hearts capped at 12
CAPPED_HEARTS = range(10, 13)
SEEDS = range(1, 6)
# Emulator (aldonunez labels): the cave's three wares, and the stairs mode's target.
CAVE_ITEM_IDS = 0x422
TARGET_MODE = 0x5B
IS_UPDATING_MODE = 0x11
STAIRS_MODE, CAVE_MODE = 0x10, 0x0B
CAVE_WARE = 1                        # the middle ware: a sword cave's and the letter cave's item
CAVE_DESTINATIONS = 0x18490          # LevelBlockAttrsB of the overworld: code in bits 7-2 (OW-CAVE-01)
CAVE_CODE_SHIFT = 2
FIRST_CAVE_CODE, CAVE_PERSON_BASE = 0x10, 0x6A   # the cave person's object type: $6A + code - $10
LEVEL_START_ROOM = 0x1943B           # LevelInfo_StartRoomId of level 1; one level information apart
LEVEL_INFO_SIZE = 252
LEVEL_LOAD_FRAMES, SETTLE_FRAMES, CAVE_FRAMES = 900, 20, 120
TEXT_PAD = "~"                       # a parsed line's centring


@cache
def base() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def generated(zora: str, seed: int) -> tuple[GenerationPlan, GameWorld, GenerationResult]:
    chosen = plan(FLAGS, seed, zora)
    world, result = generate_world(chosen, base())
    return chosen, world, result


def cave(world: GameWorld, destination: Destination) -> ItemCave:
    found = world.overworld.get_cave(destination, ItemCave)
    assert found is not None
    return found


def sword_rooms(world: GameWorld) -> list[tuple[int, int]]:
    """(level, room) of each dungeon room holding the magical sword."""
    return [(level.level_num, room.room_num) for level in world.levels for room in level.rooms
            if room.item == Item.MAGICAL_SWORD]


# --- the ZORA flag string ---------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2])
def test_the_empty_zora_string_is_todays_generation(seed: int) -> None:
    """Empty (and any spelling of every default) leaves the plan, the seed and the ROM as they were."""
    for flags in (FLAGS, *((MVP_BASELINE,) if level_encoding.is_available() else ())):
        today = generate_rom(flags, seed, base())
        for zora in ("", "1.0", " "):
            chosen = plan(flags, seed, zora)
            assert chosen == plan(flags, seed) and chosen.zora_flag_string == ""
            assert generate_rom(flags, seed, base(), zora_flag_string=zora) == today


@pytest.mark.parametrize("zora", [SWORD, LETTER, BOTH])
def test_a_zora_flag_changes_the_rom_and_its_code(zora: str) -> None:
    today = generate_rom(FLAGS, 1, base())
    extra = generate_rom(FLAGS, 1, base(), zora_flag_string=zora)
    assert extra.rom != today.rom and extra.code != today.code
    assert extra.zora_flag_string == zora and extra.flag_string == today.flag_string
    assert plan(FLAGS, 1, zora).generation_seed != plan(FLAGS, 1).generation_seed


def test_the_level_encoding_key_covers_both_strings() -> None:
    if not level_encoding.is_available():
        pytest.skip("level encoding not installed")
    for zora, text in (("", MVP_BASELINE), (LETTER, f"{MVP_BASELINE} {LETTER}")):
        key = plan(MVP_BASELINE, 3, zora).config.level_encoding
        assert key is not None and key.flag_string == text


def test_a_bad_zora_string_is_refused_with_the_decoders_reason() -> None:
    for bad, reason in (("1", "expected <version>.<flags>"), ("4.1", "newer"), ("1.O", "beyond")):
        with pytest.raises(FlagsRefused, match=reason):
            plan(FLAGS, 0, bad)
    with pytest.raises(FlagsRefused, match="ZORA flag string"):
        plan(FLAGS, 0, FLAGS)                  # a Z1R string in the ZORA box


# --- the sword-hearts conflict (owner requirement: refused, never changed) ---------------------

def _with_b10(value: ThreeState) -> str:
    return encode(decode(FLAGS).updated(toggles={"B10": value}))


def test_more_than_12_hearts_with_the_sword_is_refused() -> None:
    with pytest.raises(FlagsRefused) as refused:
        plan(FLAGS, 0, SWORD_UNCAPPED)
    assert "Change Sword Hearts" in str(refused.value) and "14 hearts" in str(refused.value)
    with pytest.raises(FlagsRefused, match="Change Sword Hearts"):
        plan(_with_b10(ThreeState.POSSIBLE), 0, SWORD_UNCAPPED)     # a "?" may come up on
    # resolved by hand: B10 off (PRG0's 12) or the cap at 12
    assert plan(_with_b10(ThreeState.OFF), 0, SWORD_UNCAPPED).zora.randomize_magical_sword
    assert plan(FLAGS, 0, SWORD).zora.magical_sword_hearts_highest == 12


def test_the_page_shows_the_conflict_at_each_setting() -> None:
    state = flag_form.form_state(FLAGS, SWORD_UNCAPPED)
    assert state["zora"]["ok"] and state["zora"]["flags"] == SWORD_UNCAPPED
    [conflict] = state["zora"]["conflicts"]
    assert set(conflict["fields"]) == {"randomize_magical_sword", "magical_sword_hearts_highest", "B10"}
    assert conflict["message"] in state["generateRefusals"]
    resolved = flag_form.form_state(FLAGS, SWORD)
    assert resolved["zora"]["conflicts"] == [] and resolved["generateRefusals"] == []
    assert flag_form.form_state(_with_b10(ThreeState.OFF), SWORD_UNCAPPED)["generateRefusals"] == []
    bad = flag_form.form_state(FLAGS, "1.")
    assert not bad["zora"]["ok"] and bad["generateRefusals"]


def test_the_page_shows_the_extra_candles_conflict_at_both_settings() -> None:
    """PI-FLAG-03: Progressive Items with B09 on (the MVP baseline) is refused and shown in red
    at both settings; B09 off clears it."""
    progressive = "2.O"
    state = flag_form.form_state(FLAGS, progressive)
    [conflict] = state["zora"]["conflicts"]
    assert conflict["fields"] == ["progressive_items", "B09"]
    assert conflict["message"].startswith("Progressive Items cannot be used with Extra Candles")
    assert conflict["message"] in state["generateRefusals"]
    with pytest.raises(FlagsRefused, match="Extra Candles"):
        plan(FLAGS, 0, progressive)
    without = encode(decode(FLAGS).updated(toggles={"B09": ThreeState.OFF}))
    assert flag_form.form_state(without, progressive)["zora"]["conflicts"] == []
    possible = encode(decode(FLAGS).updated(toggles={"B09": ThreeState.POSSIBLE}))
    assert all(not plan(possible, seed, progressive).steps.extra_candles for seed in range(8))
    assert any(plan(possible, seed).steps.extra_candles for seed in range(8))


def test_the_tab_controls_spell_the_zora_string() -> None:
    from zora.flags.zora_flags import OWNER_2_0_FIELDS
    values = {"randomize_magical_sword": "1", "randomize_letter": "0", "magical_sword_hearts_highest": "3",
              "progressive_items": "0", "shop_items_in_pool": "0", **dict.fromkeys(OWNER_2_0_FIELDS, "0")}
    assert flag_form.zora_form_change(FLAGS, values)["zora"]["flags"] == SWORD
    off = dict.fromkeys(values, "0")
    assert flag_form.zora_form_change(FLAGS, off)["zora"]["flags"] == ""
    assert flag_form.form_state(FLAGS, BOTH)["zora"]["values"] == {
        "randomize_magical_sword": 1, "randomize_letter": 1, "magical_sword_hearts_highest": 3,
        "progressive_items": 0, "shop_items_in_pool": 0, **dict.fromkeys(OWNER_2_0_FIELDS, 0)}
    assert [field["name"] for field in flag_form.metadata()["zora"]["fields"]] == list(values)


# --- Randomize Magical Sword ----------------------------------------------------------------

def test_the_sword_moves_and_its_cave_offers_the_item_it_displaced() -> None:
    moved = 0
    for seed in SEEDS:
        chosen, world, result = generated(SWORD, seed)
        assert chosen.config.dungeon_nothing_code is DungeonNothingCode.ZORA_REMAP
        assert result.extra_pool_items is not None
        offered = cave(world, Destination.MAGICAL_SWORD_CAVE).item
        assert offered == result.extra_pool_items.caves["magical_sword"]
        moved += offered != Item.MAGICAL_SWORD
    assert moved >= 3


def test_a_sword_in_a_dungeon_room_survives_the_round_trip() -> None:
    """Written with the $0E "no item" code, read back as the magical sword; every other room's
    item reads back as written."""
    seed = next(seed for seed in range(20) if sword_rooms(generated(SWORD, seed)[1]))
    chosen, world, _ = generated(SWORD, seed)
    reread = parse_rom(serialize_to_rom(world, base(), config=chosen.config), config=chosen.config)
    assert sword_rooms(reread) == sword_rooms(world)
    assert [[room.item for room in level.rooms] for level in reread.levels] == \
        [[room.item for room in level.rooms] for level in world.levels]


@pytest.mark.parametrize("zora", [SWORD, LETTER, BOTH])
def test_tracked_items_in_the_extras_caves_are_collected(zora: str) -> None:
    """E1 collects a tracked item an extra displaced into its cave (acceptance_check.closure)."""
    found = 0
    for seed in range(12):
        _, world, result = generated(zora, seed)
        assert result.item_shuffle_result is not None and result.overworld is not None
        in_caves = {place.item for place in result.item_shuffle_result.tracked if place.slot in EXTRA_SLOT_CAVES}
        check = AcceptanceCheck(world.levels, result.item_shuffle_result, world.overworld, result.overworld)
        assert in_caves <= check.closure()[0] and check.collects_everything()
        found += bool(in_caves)
    assert found


def test_the_requirement_is_drawn_before_the_check_and_checked_exactly() -> None:
    for seed in SEEDS:
        chosen, world, result = generated(SWORD, seed)
        assert cave(world, Destination.MAGICAL_SWORD_CAVE).heart_requirement in CAPPED_HEARTS
        assert result.item_shuffle_result and result.overworld and result.extra_pool_items is not None
        assert has_magical_sword_hearts(world.levels, result.item_shuffle_result, result.extra_pool_items,
                                        OverworldResult(world.overworld, result.overworld), extra_options(chosen))
    # B10 off: PRG0's 12, not drawn
    chosen = plan(_with_b10(ThreeState.OFF), 1, SWORD_UNCAPPED)
    world, _ = generate_world(chosen, base())
    assert cave(world, Destination.MAGICAL_SWORD_CAVE).heart_requirement == 12


def test_the_heart_check_counts_all_but_two_reachable_take_any_caves() -> None:
    """(reachable heart containers) + max(0, k - 2) >= N - M. A take-any cave (code 17) offers a
    red potion, the blue candle (OW-SHOP-05, with B09) and a heart container (PRG0's wares)."""
    _, world, _ = generated(SWORD, 1)
    take_any = world.overworld.caves[[c.destination for c in world.overworld.caves].index(Destination.TAKE_ANY)]
    assert set(getattr(take_any, "items")) == {Item.RED_POTION, Item.BLUE_CANDLE, Item.HEART_CONTAINER}
    every_need = frozenset({Item.RAFT, Item.RECORDER, Item.LADDER, Item.POWER_BRACELET})
    assert reachable_take_any_hearts(world.overworld, every_need) == 7       # seven code-17 screens
    assert reachable_take_any_hearts(world.overworld, frozenset()) <= 7
    assert [take_any_heart_allowance(k) for k in range(5)] == [0, 0, 0, 1, 2]
    assert TAKE_ANY_CAVES_SPENT_ELSEWHERE == 2
    # N = 12, M = 3: four reachable heart containers and five take-any caves are enough, three are not
    assert has_enough_heart_containers(12, 3, 4 + take_any_heart_allowance(7))
    assert not has_enough_heart_containers(12, 3, 4 + take_any_heart_allowance(6))


def test_the_caves_own_text_names_the_item_it_offers() -> None:
    for seed in (1, 2):
        chosen, world, _ = generated(SWORD, seed)
        offered = cave(world, Destination.MAGICAL_SWORD_CAVE).item
        rom = generate_rom(FLAGS, seed, base(), zora_flag_string=SWORD).rom
        shown = parse_rom(rom, config=chosen.config).quotes[MAGICAL_SWORD_TEXT_SLOT].text
        first, second = magical_sword_cave_words()
        assert [line.strip(TEXT_PAD) for line in shown.split("|")] == [first, f"{second} {ITEM_ARTICLE}",
                                                                       item_name(offered)]
    # without the flag the slot keeps its drawn text
    _, world, _ = generated("", 1)
    assert not world.quotes[MAGICAL_SWORD_TEXT_SLOT].text.startswith(magical_sword_cave_words()[0])


def test_the_magical_sword_heart_draw_follows_the_cap() -> None:
    assert extra_options(plan(FLAGS, 0)).magical_sword_hearts == MAGICAL_SWORD_HEARTS
    assert extra_options(plan(FLAGS, 0, SWORD)).magical_sword_hearts == CAPPED_HEARTS


# --- Randomize Letter -------------------------------------------------------------------------

def test_the_letter_moves_and_its_cave_offers_the_item_it_displaced() -> None:
    moved = 0
    for seed in SEEDS:
        chosen, world, result = generated(LETTER, seed)
        assert chosen.config.dungeon_nothing_code is DungeonNothingCode.VANILLA
        assert result.extra_pool_items is not None
        offered = cave(world, Destination.LETTER_CAVE).item
        assert offered == result.extra_pool_items.caves["letter"]
        moved += offered != Item.LETTER
        assert Item.MAGICAL_SWORD == cave(world, Destination.MAGICAL_SWORD_CAVE).item
    assert moved >= 3


# --- in the emulator --------------------------------------------------------------------------

def _start_in_room(rom: bytes, level_num: int, room_num: int) -> Emulator:
    """The level loaded with this room as its start room (LevelInfo_StartRoomId rewritten)."""
    patched = bytearray(rom)
    patched[LEVEL_START_ROOM + LEVEL_INFO_SIZE * (level_num - 1)] = room_num
    emu = Emulator(bytes(patched))
    emu.new_game()
    emu[CUR_LEVEL] = level_num
    emu[GAME_MODE] = Mode.LOAD_LEVEL
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == level_num, limit=LEVEL_LOAD_FRAMES)
    emu.run(SETTLE_FRAMES)
    return emu


def _takes_the_room_item(emu: Emulator) -> bool:
    """Link stands on the room item; whether the magical sword lands in InvSword."""
    x, y = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    for _ in range(30):
        emu[OBJ_X], emu[OBJ_Y] = x, y
        emu.run(1)
    return emu[ITEMS] == Item.MAGICAL_SWORD


@pytest.mark.slow
def test_a_magical_sword_in_a_dungeon_room_is_taken() -> None:
    """The $0E change (docs/zora-extras.md section 6): a room whose item is the magical sword
    starts with it active, and Link takes it. Control: the same world written with PRG0's $03
    "no item" code starts it deactivated, and Link cannot."""
    for seed in range(40):
        chosen, world, _ = generated(SWORD, seed)
        visible = [(level.level_num, room.room_num) for level in world.levels for room in level.rooms
                   if room.item == Item.MAGICAL_SWORD and room.room_action != RoomAction.ALL_DEAD_ITEM]
        if visible:
            break
    level_num, room_num = visible[0]
    remapped = serialize_to_rom(world, base(), config=chosen.config)
    emu = _start_in_room(remapped, level_num, room_num)
    assert emu[ROOM_ID] == room_num and emu[OBJ_STATE + ROOM_ITEM_SLOT] == 0
    assert _takes_the_room_item(emu)
    prg0_code = serialize_to_rom(world, base(), config=replace(chosen.config,
                                                                dungeon_nothing_code=DungeonNothingCode.VANILLA))
    control = _start_in_room(prg0_code, level_num, room_num)
    assert control[OBJ_STATE + ROOM_ITEM_SLOT] != 0 and not _takes_the_room_item(control)


def _cave_wares(rom: bytes, screen: int) -> list[int] | None:
    """Enter the cave on this overworld screen (the stairs mode, as a cave entrance sets it) and
    read the wares it shows (CaveItemIds); None when the cave's person did not load.

    Entered this way, a cave on a screen that spawns its own monsters can come up without its
    person (the screen's monster stays in the person's slot), so the caller uses the screens
    whose person loads."""
    emu = Emulator(rom)
    emu.new_game()
    emu[ROOM_ID] = screen
    emu[TARGET_MODE] = CAVE_MODE
    emu[IS_UPDATING_MODE] = 0
    emu[GAME_MODE] = STAIRS_MODE
    emu[GAME_SUBMODE] = 0
    emu.run(CAVE_FRAMES)
    destination = rom[CAVE_DESTINATIONS + screen] >> CAVE_CODE_SHIFT
    if emu.mode != CAVE_MODE or emu[OBJ_TYPE + 1] != CAVE_PERSON_BASE + destination - FIRST_CAVE_CODE:
        return None
    return [emu[CAVE_ITEM_IDS + ware] for ware in range(3)]


@pytest.mark.slow
@pytest.mark.parametrize(("zora", "destination"), [(SWORD, Destination.MAGICAL_SWORD_CAVE),
                                                     (LETTER, Destination.LETTER_CAVE)])
def test_the_cave_offers_its_new_item(zora: str, destination: Destination) -> None:
    """In the emulator the cave shows the item that landed there: the first seed whose cave
    offers another item and whose cave person loads from some screen of it."""
    for seed in range(30):
        _, world, _ = generated(zora, seed)
        offered = cave(world, destination).item
        if offered in (Item.MAGICAL_SWORD, Item.LETTER):
            continue
        rom = generate_rom(FLAGS, seed, base(), zora_flag_string=zora).rom
        shown = [wares for screen in world.overworld.screens if screen.destination == destination
                 if (wares := _cave_wares(rom, screen.screen_num)) is not None]
        if shown:
            assert all(wares[CAVE_WARE] == offered for wares in shown)
            return
    pytest.fail("no seed in 0-29 to look at")
