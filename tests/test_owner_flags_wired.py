"""The owner's 2.0 flags wired (docs/design/zora-flags-2.0.md; owner decisions 2026-10-07): each
flag's behaviour on generated seeds. The 1,000-seed beatability runs and the QA sweep are reported
in the commit; here a few seeds each, judged on the finished ROM (tests/owner_flags_replay.py)."""
from functools import cache
from pathlib import Path

import pytest

from tests.owner_flags_replay import replay
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OWNER_2_0_FIELDS, ZoraFlags
from zora.generate.pipeline import generate_rom, generate_world, plan
from zora.generate.steps import overworld_gates as gates
from zora.model.enums import Destination, Item
from zora.model.overworld import POTION_SHOP_MIDDLE
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.layout import MAZE_DIRECTIONS_ADDRESS
from zora.rom.owner_patches import PATCHES_BY_FLAG, owner_patch_writes
from zora.rom.parse.rom_file import load_rom, parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

REPO = Path(__file__).resolve().parent.parent
ON, OFF, MAYBE = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
BASELINE = MVP_BASELINE_LEVEL_ENCODING_OFF
B04_OFF = encode(decode(BASELINE).updated(toggles={"B04": OFF}))
WITHOUT_CANDLES = encode(decode(BASELINE).updated(toggles={"B04": OFF, "B09": OFF}))
PRODUCED = sorted(zora_flags.PRODUCED_OWNER_FIELDS)
MAZE_BYTES = 8


@cache
def base() -> bytes:
    return load_rom(verify_base_rom())


def zora(**values: ThreeState | bool | int) -> str:
    return zora_flags.encode(ZoraFlags(**values))  # type: ignore[arg-type]


def z1r_for(flag: str) -> str:
    if flag == "add_l4_sword":
        return WITHOUT_CANDLES             # with Progressive Items, which refuses Extra Candles
    return B04_OFF if flag == "extra_power_bracelet_blocks" else BASELINE


def zora_for(flag: str, value: ThreeState = ON) -> str:
    """One flag on; Add L4 Sword with Progressive Items, which it needs."""
    return zora(**{flag: value}, **({"progressive_items": True} if flag == "add_l4_sword" else {}))


# --- the patches ------------------------------------------------------------------------------

def test_the_patch_data_is_c2s_build_verbatim() -> None:
    assert (REPO / "zora/rom/flags2_patch_data.py").read_bytes() == (REPO / "asm/flags2/flags2_data.py").read_bytes()


@pytest.mark.parametrize("flag", [f for f in PRODUCED if PATCHES_BY_FLAG[f]])
def test_each_flag_writes_its_patch_exactly_when_on(flag: str) -> None:
    on = generate_rom(z1r_for(flag), 1, base(), zora_flag_string=zora_for(flag)).rom
    plain = generate_rom(z1r_for(flag), 1, base()).rom
    writes = owner_patch_writes([flag])
    assert writes
    for offset, data in writes:
        assert on[offset:offset + len(data)] == data, hex(offset)
    assert any(plain[offset:offset + len(data)] != data for offset, data in writes)


def test_with_the_mazes_off_their_bytes_stay_prg0s() -> None:
    rom = generate_rom(BASELINE, 1, base(), zora_flag_string="1.2").rom
    span = slice(MAZE_DIRECTIONS_ADDRESS, MAZE_DIRECTIONS_ADDRESS + MAZE_BYTES)
    assert rom[span] == base()[span]


# --- each flag on a few seeds, judged on the finished ROM -------------------------------------------

@pytest.mark.parametrize("flag", PRODUCED)
def test_each_flag_ships_beatable_seeds(flag: str) -> None:
    for seed in range(3):
        result = replay(z1r_for(flag), seed, zora_for(flag), base())
        assert result.beatable, (flag, seed, result.problems)


def test_every_question_mark_comes_up_both_ways() -> None:
    """Add L4 Sword's too: a released string's "?" (Off or Level 9; owner ruling, 2026-10-08)."""
    asked = zora(**dict.fromkeys(PRODUCED, MAYBE), progressive_items=True)
    outcomes: dict[str, set[ThreeState]] = {name: set() for name in PRODUCED}
    for seed in range(24):
        resolved = plan(WITHOUT_CANDLES, seed, asked).zora_resolved
        for name in PRODUCED:
            outcomes[name].add(getattr(resolved, name))
    assert all(values == {ON, OFF} for values in outcomes.values()), outcomes


# --- the overworld gates -----------------------------------------------------------------------

def test_the_gates_need_what_the_document_says() -> None:
    from zora.generate.acceptance_check import logic_rules
    rules = logic_rules(False, False, gates.OverworldGates(True, True, True, True))
    assert all(rules.needs(screen) >= {Item.RAFT} for screen in gates.RAFT_BLOCK_SCREENS)
    assert all(rules.needs(screen) >= {Item.POWER_BRACELET} for screen in gates.BRACELET_BLOCK_SCREENS)
    assert all(rules.needs(screen) >= {gates.LOST_HILLS_HINT} for screen in gates.LOST_HILLS_GATED)
    assert all(rules.needs(screen) >= {gates.DEAD_WOODS_HINT} for screen in gates.DEAD_WOODS_GATED)
    assert all(rules.needs(screen) >= {Item.LADDER} for screen in gates.DEAD_WOODS_WEST)
    assert dict(rules.maze_hints) == {gates.LOST_HILLS_HINT: Destination.HINT_SHOP_1,
                                      gates.DEAD_WOODS_HINT: Destination.HINT_SHOP_2}


def test_no_gate_leaves_the_rules_as_they_were() -> None:
    from zora.generate.acceptance_check import DEFAULT_RULES, logic_rules
    assert logic_rules(False, False) == DEFAULT_RULES


# --- Shuffle Blue Potion --------------------------------------------------------------------------

def test_the_blue_potion_adds_one_item_and_one_place() -> None:
    """The place is the potion shop's middle ware; its left blue potion and red potion stay."""
    from zora.generate.steps.potion_shop import potion_shop
    chosen = plan(BASELINE, 2, zora(shuffle_blue_potion=ON))
    world, result = generate_world(chosen, base())
    assert result.extra_pool_items is not None
    assert result.extra_pool_items.shop_items.count(Item.BLUE_POTION) == 1
    assert [(ware.shop.destination, ware.position) for ware in result.extra_pool_items.shop_wares] == \
        [(Destination.POTION_SHOP, POTION_SHOP_MIDDLE)]
    shop, prg0 = potion_shop(world.overworld), potion_shop(parse_rom(base()).overworld)
    assert [ware.item for ware in shop.items] == [ware.item for ware in prg0.items] == \
        [Item.BLUE_POTION, Item.RED_POTION]
    assert shop.middle is not None and prg0.middle is None


def test_the_letter_never_lands_in_the_potion_shop_and_is_tracked_when_needed() -> None:
    from zora.generate.steps.potion_shop import potion_shop
    tracked_letter = 0
    for seed in range(12):
        chosen = plan(BASELINE, seed, zora(shuffle_blue_potion=ON, randomize_letter=True))
        world, result = generate_world(chosen, base())
        shop = potion_shop(world.overworld)
        assert shop.middle is not None and Item.LETTER not in {shop.middle.item, *(ware.item for ware in shop.items)}
        state = result.item_shuffle_result
        assert state is not None
        middle = f"shop {Destination.POTION_SHOP.name} {POTION_SHOP_MIDDLE}"
        holds_tracked = any(place.slot == middle for place in state.tracked)
        letter = any(place.item == Item.LETTER for place in state.tracked)
        assert letter == holds_tracked, seed
        tracked_letter += letter
    assert tracked_letter


# --- Add L4 Sword (docs/design/l4-sword.md, tests T7-T12) ---------------------------------------

L4_FLAGS = {"add_l4_sword": ON, "progressive_items": True}


def test_with_add_l4_sword_on_its_patches_are_written() -> None:
    """The beam test, and ASNB's take-l4 and sword-cap, which retire l4-sword-take (asnb.md 3a)."""
    from zora.rom.owner_patches import ASNB_PATCHES_BY_FLAG, RETIRED_PATCHES
    rom = generate_rom(WITHOUT_CANDLES, 1, base(), zora_flag_string=zora(**L4_FLAGS)).rom
    writes = owner_patch_writes(["add_l4_sword"])
    assert set(PATCHES_BY_FLAG["add_l4_sword"]) == {"l4-sword-beam"} and RETIRED_PATCHES == {"l4-sword-take"}
    assert set(ASNB_PATCHES_BY_FLAG["add_l4_sword"]) == {"take-l4", "sword-cap"}
    for offset, data in writes:
        assert rom[offset:offset + len(data)] == data, hex(offset)


def test_t7_without_progressive_items_its_question_mark_resolves_off() -> None:
    """A released "?" without Progressive Items resolves off (beta 1's rule); on is refused."""
    from zora.generate.pipeline import FlagsRefused
    for seed in range(8):
        assert plan(B04_OFF, seed, zora(add_l4_sword=MAYBE)).zora_resolved.add_l4_sword is OFF
    with pytest.raises(FlagsRefused):
        plan(B04_OFF, 1, zora(add_l4_sword=ON))


def level9_swords(world: object) -> list[int]:
    from zora.generate.steps.add_l4_sword import L4_SWORD_ITEM
    level9 = next(level for level in world.levels if level.level_num == 9)  # type: ignore[attr-defined]
    return [room.room_num for room in level9.rooms if room.item == L4_SWORD_ITEM]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t8_t9_one_sword_in_a_qualifying_level_9_room_outside_pool_and_logic(seed: int) -> None:
    from zora.generate.steps.add_l4_sword import L4_SWORD_ITEM, collectible_rooms, qualifies
    from zora_measure.owner_flags import owner_flag_problems
    chosen = plan(WITHOUT_CANDLES, seed, zora(**L4_FLAGS))
    world, result = generate_world(chosen, base())
    level9 = next(level for level in world.levels if level.level_num == 9)
    swords = level9_swords(world)
    assert len(swords) == 1
    room = level9.block.room(swords[0])
    assert qualifies(level9, room, collectible_rooms(level9), L4_SWORD_ITEM)
    assert owner_flag_problems(world, gates.NO_GATES, l4_sword=True) == []      # R6a's top half too
    state = result.item_shuffle_result
    assert state is not None
    assert not any(place.item & 0x3F == L4_SWORD_ITEM and place.level == 9 for place in state.tracked)
    assert L4_SWORD_ITEM not in (result.extra_pool_items.shop_items if result.extra_pool_items else [])


def test_t10_the_same_flags_and_seed_give_the_same_rom() -> None:
    flags = zora(**L4_FLAGS)
    assert generate_rom(WITHOUT_CANDLES, 5, base(), zora_flag_string=flags).rom == \
        generate_rom(WITHOUT_CANDLES, 5, base(), zora_flag_string=flags).rom


def test_t11_seeds_with_the_sword_are_beatable() -> None:
    for seed in range(4):
        result = replay(WITHOUT_CANDLES, seed, zora(**L4_FLAGS), base())
        assert result.beatable, (seed, result.problems)


def test_t12_the_spoiler_log_lists_the_sword() -> None:
    from zora_export.seed_document import seed_document_for
    from zora_export.spoiler_log import L4_SWORD_LABEL, spoiler_log
    flags = zora(**L4_FLAGS)
    rom = generate_rom(WITHOUT_CANDLES, 6, base(), zora_flag_string=flags).rom
    document = seed_document_for(rom, WITHOUT_CANDLES, 6, flags)
    room = document["zoraExtras"]["l4Sword"]["room"]
    assert [room] == level9_swords(parse_rom(rom))
    assert f"room {room:02X}" in spoiler_log(document) and L4_SWORD_LABEL in spoiler_log(document)


def test_every_flag_is_mapped_to_its_patches() -> None:
    assert set(PATCHES_BY_FLAG) == set(OWNER_2_0_FIELDS)


# --- the seed document and the spoiler log ----------------------------------------------------------

def test_the_document_and_log_carry_the_mazes_gates_and_potion_shop() -> None:
    import json

    from zora_export.seed_document import seed_document_for
    from zora_export.spoiler_log import WIDTH, spoiler_log
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "docs/seed-format/seed-format.schema.json").read_text())
    flags = zora(**dict.fromkeys(PRODUCED, ON), progressive_items=True)
    rom = generate_rom(WITHOUT_CANDLES, 4, base(), zora_flag_string=flags).rom
    document = seed_document_for(rom, WITHOUT_CANDLES, 4, flags)
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(document))
    world = parse_rom(rom)
    mazes = {maze["name"]: maze for maze in document["zoraExtras"]["mazes"]}
    assert mazes["Lost Hills"]["sequence"] == [
        {0x08: "up", 0x04: "down", 0x01: "right"}[step] for step in world.overworld.lost_hills_directions]
    assert mazes["Dead Woods"]["sequence"][-1] == "south" and mazes["Dead Woods"]["hintShop"] == "Hint Shop 2"
    needs = {gate["needs"] for gate in document["zoraExtras"]["gates"]}
    assert {"the raft", "the power bracelet", "the ladder"} <= needs
    log = spoiler_log(document)
    assert "Mazes and overworld gates" in log and all(len(line) <= WIDTH for line in log.splitlines())
    potion = next(cave for cave in document["caves"] if cave["kind"] == "potion-shop")
    assert [ware["item"] for ware in potion["wares"]][-1] == "Red Potion"


def test_t8_the_triforce_checker_room_takes_the_sword_in_its_top_half() -> None:
    """R6a: drawn there, the sword stands at level 9's first top-half item position."""
    from zora.generate.late_gate.walk import level9_entry_room
    from zora.generate.rng import Rng
    from zora.generate.steps import add_l4_sword as l4
    world = parse_rom(generate_rom(BASELINE, 1, base()).rom)
    level9 = next(level for level in world.levels if level.level_num == 9)
    checker = level9_entry_room(level9)
    assert checker is not None
    others = [room for room in level9.rooms if room.room_num != checker]
    for room in others:            # leave the checker room the only one that qualifies
        room.item = Item.KEY
    checker_room = level9.block.room(checker)
    checker_room.item = Item.NOTHING
    if checker_room.room_action in l4.HIDING_TRIGGERS:
        pytest.skip("this seed's checker room hides its item")
    assert l4.add_l4_sword(world.levels, Rng(1)) == checker
    y = level9.item_position_table[checker_room.item_position] & l4.POSITION_Y_MASK
    assert y < l4.TOP_HALF_Y_BELOW


@pytest.mark.parametrize("seed", range(12))
def test_the_swords_room_was_empty_is_no_excluded_kind_and_is_collectible(
        monkeypatch: pytest.MonkeyPatch, seed: int) -> None:
    """Owner decision (2026-10-07): a level-9 room with no item beforehand; never a cellar, a
    transport staircase, Zelda's or Ganon's room, or a room on the "last boss" trigger (or the
    drop-on-clear trigger, R5.3); and the sword collectible: the plain walk from level 9's entrance
    reaches its room before Ganon's shutters open."""
    from zora.generate import generation_pass
    from zora.generate.dungeon_walk import walk_level
    from zora.generate.rng import IntRng
    from zora.generate.steps.add_l4_sword import add_l4_sword
    from zora.model.enums import Enemy, RoomAction, RoomType
    from zora.model.levels import Level
    before: dict[str, object] = {}

    def recording(levels: list[Level], rng: IntRng) -> int:
        level9 = next(level for level in levels if level.level_num == 9)
        items = {room.room_num: room.item for room in level9.rooms}
        number = add_l4_sword(levels, rng)
        before.update(item=items[number], room=number)
        return number

    monkeypatch.setattr(generation_pass, "add_l4_sword", recording)
    world, _ = generate_world(plan(WITHOUT_CANDLES, seed, zora(**L4_FLAGS)), base())
    level9 = next(level for level in world.levels if level.level_num == 9)
    number = before["room"]
    assert isinstance(number, int) and before["item"] == Item.NOTHING
    room = level9.block.room(number)
    assert room.item == Item.WOOD_SWORD and level9_swords(world) == [number]
    assert number not in {staircase.room_num for staircase in level9.block.staircases}
    assert room.room_type not in (RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE)
    assert room.enemy not in (Enemy.THE_KIDNAPPED, Enemy.THE_BEAST)
    assert room.room_action not in (RoomAction.LAST_BOSS, RoomAction.ALL_DEAD_ITEM)
    assert number != level9.entrance_room
    walk = walk_level(level9, frozenset({Item.LADDER}), is_last_boss_open=False, uses_families=False,
                      target=number, uses_entry_sides=False)
    assert walk.accepts(level9, number)
