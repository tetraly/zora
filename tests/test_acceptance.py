"""The acceptance check (acceptance.md): the arrival rule, and accepted
output's level-9 consequence (VA-REJ-08)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.measure.checkpoints.acceptance import long_items_outside_level9
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.generate.dungeon_walk import (
    FAMILY_ITEMS, PRG0_POLS_VOICE_GROUP_VALUES, arrival_accepts, is_family_blocked, pols_voice_group_values,
    are_stairs_usable,
)
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.model.rooms import MONSTER_BIT_CODE, LayoutInfo, Room
from zora.model.levels import ZELDA_LIST
from zora.model.enums import Enemy, Item, RoomAction, RoomType, Side



def test_arrival_rule() -> None:
    """VA-REJ-17's arrival rule by layout."""
    assert arrival_accepts(0x18, True, {Side.WEST}) and not arrival_accepts(0x18, True, {Side.NORTH})
    assert arrival_accepts(0x0E, True, {Side.SOUTH}) and not arrival_accepts(0x0E, True, {Side.EAST})
    assert arrival_accepts(0x19, True, {Side.EAST}) and not arrival_accepts(0x0F, True, {Side.SOUTH})
    assert arrival_accepts(0x12, True, {Side.SOUTH, Side.WEST}) and not arrival_accepts(0x12, True, {Side.SOUTH})
    assert arrival_accepts(0x13, True, {Side.WEST}) and not arrival_accepts(0x13, True, {Side.EAST})
    assert arrival_accepts(0x0B, True, {Side.NORTH, Side.WEST}) and not arrival_accepts(0x0B, True, {Side.NORTH, Side.EAST})
    assert arrival_accepts(0x20, True, set()) and not arrival_accepts(0x20, False, set())


def _stairs_room(layout: int, movable: bool = False, trigger: int = 0) -> Room:
    room = Room.blank(0)
    room.layout_info = LayoutInfo(RoomType(layout), movable)
    room.room_action = RoomAction(trigger)
    return room


def test_stairs_usable_while_blocked() -> None:
    """VA-WALK-04 (W1, A58): $1B and $1C, push bit included ($5B, $5C),
    keep their stairs in a blocked room; $5A and trigger 5 only work in a
    room that can be cleared."""
    for layout in (0x1B, 0x1C):
        for movable in (False, True):
            assert are_stairs_usable(_stairs_room(layout, movable), is_blocked=True)
    diamond = _stairs_room(0x1A, movable=True)                    # $5A
    assert are_stairs_usable(diamond, is_blocked=False) and not are_stairs_usable(diamond, is_blocked=True)
    assert not are_stairs_usable(_stairs_room(0x1A), is_blocked=False)   # $1A is not $5A
    reveal = _stairs_room(0x20, trigger=5)
    assert are_stairs_usable(reveal, is_blocked=False) and not are_stairs_usable(reveal, is_blocked=True)


def _room(enemy: int, flagged: bool = False) -> Room:
    room = Room.blank(0)
    room.enemy = Enemy(enemy | (MONSTER_BIT_CODE if flagged else 0))
    return room


def test_family_lists() -> None:
    """VA-REJ-17's lists by monster value (low six bits, plus $80 when the
    layout byte's bit 7 is set) and their unblocking items."""
    sword = frozenset({Item.WOOD_SWORD})
    assert is_family_blocked(_room(0x33), sword) and not is_family_blocked(_room(0x33), sword | {Item.BOW})
    assert is_family_blocked(_room(0x38), sword) and not is_family_blocked(_room(0x39), sword | {Item.RECORDER})
    # Ganon and Zelda need both the bow and the silver arrow
    assert is_family_blocked(_room(0x3E), sword | {Item.BOW})
    assert is_family_blocked(_room(0x37), sword | {Item.SILVER_ARROWS})
    assert not is_family_blocked(_room(0x3E), sword | {Item.BOW, Item.SILVER_ARROWS})
    # The sword list: Gleeok ($42 flagged = $82) and Pols Voice groups, inert
    # while the wooden sword is held
    assert is_family_blocked(_room(0x02, flagged=True), frozenset())
    assert not is_family_blocked(_room(0x02, flagged=True), sword)
    assert not is_family_blocked(_room(0x02), frozenset())        # $02 unflagged is not Gleeok
    assert is_family_blocked(_room(0x30, flagged=True), frozenset())   # group $70
    assert not is_family_blocked(_room(0x33, flagged=True), sword)     # $B3 is not Gohma


def test_pols_voice_groups_from_prg0() -> None:
    """The sword list's group values, derived from PRG0's group lists."""
    env = os.environ.get("ZORA_VANILLA_ROM")
    path = Path(env) if env else BASE_ROM_PATH
    if not path.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(path)
    enemies = parse_rom(load_rom(path)).enemies
    offsets = sorted(enemies.mixed_group_offsets.values())
    groups = {}
    for group, start in enemies.mixed_group_offsets.items():
        end = next((o for o in offsets if o > start), len(enemies.mixed_enemy_data))
        groups[group] = enemies.mixed_enemy_data[start:end]
    assert pols_voice_group_values(groups) == PRG0_POLS_VOICE_GROUP_VALUES


def test_accepted_output_keeps_long_items_out_of_level9() -> None:
    env = os.environ.get("ZORA_VANILLA_ROM")
    path = Path(env) if env else BASE_ROM_PATH
    if not path.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(path)
    rom = load_rom(path)
    for seed in range(3):
        gw = parse_rom(rom)
        result = generate_shapes(gw, Rng(seed), ShapeOptions())
        assert long_items_outside_level9(parse_rom(serialize_to_rom(gw, rom)))
        assert set(result.acceptance_rejections) <= {"E1", "E3", "E4", "E5"}


# The finished corpus ROMs: the folder ZORA_CORPUS names (scripts/verify.sh sets it); the tests
# that need them skip without it.
CORPUS = Path(os.environ.get("ZORA_CORPUS", "temp/no-corpus"))
TRIFORCE_LEVELS = range(1, 9)


@pytest.mark.slow
def test_walk_accepts_every_corpus_target() -> None:
    """Every corpus final passed E1 and E3, so the walk,
    holding the ladder and every item that unblocks a family list (as the
    closure does by its end), must accept each level 1-8 Triforce room
    (eight completions are needed) and Zelda's room (200 finals)."""
    from zora.generate.dungeon_walk import item_room, walk_level
    roms = sorted(CORPUS.glob("*.nes"))[:200]
    if not roms:
        pytest.skip("corpus missing")
    held = FAMILY_ITEMS | {Item.LADDER}
    for path in roms:
        for level in parse_rom(load_rom(path)).levels:
            if level.level_num in TRIFORCE_LEVELS:
                triforce = item_room(level, Item.TRIFORCE)
                assert triforce is not None, (path.name, level.level_num)
                walk = walk_level(level, held, is_last_boss_open=False, uses_families=True, target=triforce)
                assert walk.accepts(level, triforce), (path.name, level.level_num)
            else:
                zelda = next(room.room_num for room in level.block.rooms
                             if room.monster_byte == ZELDA_LIST)
                walk = walk_level(level, held, is_last_boss_open=True, uses_families=False, target=zelda)
                assert walk.accepts(level, zelda), (path.name, "Zelda")


# --- Progressive Items and Shop Items in the Item Pool (plan section 5) --------------------------

from dataclasses import replace  # noqa: E402
from functools import cache  # noqa: E402

from zora.generate import acceptance_check as acceptance  # noqa: E402
from zora.generate.acceptance_check import (  # noqa: E402
    DEFAULT_RULES, ONE_ARROW, ONE_CANDLE, TWO_ARROWS, AcceptanceCheck, logic_rules,
)
from zora.generate.steps.cave_entries import BURNABLE_SCREENS  # noqa: E402

PROGRESSIVE = logic_rules(progressive_items=True, shop_items_in_pool=False)
SHOP_POOL = logic_rules(progressive_items=False, shop_items_in_pool=True)
SWORD = frozenset({Item.WOOD_SWORD})
GANON = 0x3E
GOHMA = 0x33


@cache
def _generated() -> tuple:
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_world, plan
    world, result = generate_world(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1), verify_base_rom().read_bytes())
    return world, result


def _check(rules: acceptance.LogicRules) -> AcceptanceCheck:
    world, result = _generated()
    return AcceptanceCheck(world.levels, result.item_shuffle_result, world.overworld, result.overworld, rules)


def test_both_flags_off_keep_todays_rules() -> None:
    assert logic_rules(False, False) == DEFAULT_RULES
    assert not DEFAULT_RULES.counts_lines and DEFAULT_RULES.checks_front_doors


def test_pi_logic_02_ganon_needs_two_arrow_upgrades() -> None:
    """With Progressive Items on: the bow and an arrow count of at least 2; the silver arrow's
    ID alone is one upgrade. Off: the bow and the silver arrows, as today."""
    lists = PROGRESSIVE.family_lists
    assert is_family_blocked(_room(GANON), SWORD | {Item.BOW, Item.SILVER_ARROWS}, lists)
    assert is_family_blocked(_room(GANON), SWORD | {Item.BOW, ONE_ARROW}, lists)
    assert not is_family_blocked(_room(GANON), SWORD | {Item.BOW, TWO_ARROWS}, lists)
    assert not is_family_blocked(_room(GANON), SWORD | {Item.BOW, Item.SILVER_ARROWS})
    assert is_family_blocked(_room(GANON), SWORD | {Item.BOW, TWO_ARROWS})


def test_pi_logic_01_a_line_counts_its_held_items_and_the_reached_shop_ware() -> None:
    """The silver arrow plus the arrow shop's wooden arrow (its door reached) is two upgrades;
    with no door reached, or under Shop Items in the Item Pool (the ware joined), one."""
    every_screen_need = SWORD | {Item.RAFT, Item.RECORDER, Item.LADDER, Item.POWER_BRACELET, Item.SILVER_ARROWS}
    assert _check(PROGRESSIVE).line_counts(every_screen_need) == {ONE_ARROW, TWO_ARROWS, ONE_CANDLE}
    unreachable = replace(PROGRESSIVE, screen_needs=((frozenset(range(0x80)), Item.MAGICAL_KEY),))
    assert _check(unreachable).line_counts(every_screen_need) == {ONE_ARROW}
    assert _check(SHOP_POOL).line_counts(every_screen_need) == {ONE_ARROW}
    assert _check(SHOP_POOL).line_counts(every_screen_need | {Item.WOOD_ARROWS, Item.RED_CANDLE}) == {
        ONE_ARROW, TWO_ARROWS, ONE_CANDLE}


def test_pi_logic_03_gohma_needs_an_arrow_with_the_shop_items_in_the_pool() -> None:
    lists = SHOP_POOL.family_lists
    assert is_family_blocked(_room(GOHMA), SWORD | {Item.BOW}, lists)
    assert not is_family_blocked(_room(GOHMA), SWORD | {Item.BOW, ONE_ARROW}, lists)
    assert not is_family_blocked(_room(GOHMA), SWORD | {Item.BOW})          # off: the bow, as today
    assert not is_family_blocked(_room(GOHMA), SWORD | {Item.BOW}, PROGRESSIVE.family_lists)


def test_pi_logic_04_a_burnable_screen_needs_a_candle() -> None:
    bush = min(BURNABLE_SCREENS)
    assert SHOP_POOL.needs(bush) >= {ONE_CANDLE}
    assert ONE_CANDLE not in DEFAULT_RULES.needs(bush) and ONE_CANDLE not in PROGRESSIVE.needs(bush)


def test_pi_logic_05_front_doors_are_skipped_with_the_shop_items_in_the_pool(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """E4/E5 (OW-SHOP-06) judge the candle and arrow shops' doors unless Shop Items in the Item
    Pool is on; Progressive Items alone keeps them (they guarantee PI-LOGIC-02's shop arrow)."""
    world, result = _generated()
    args = (world.levels, result.item_shuffle_result, world.overworld, result.overworld)
    assert acceptance.acceptance_check(*args) is None                     # the accepted pass
    monkeypatch.setattr(acceptance, "front_door_failure", lambda *_: "(a) candle")
    assert acceptance.acceptance_check(*args) == "E4"
    assert acceptance.acceptance_check(*args, replace(DEFAULT_RULES, checks_front_doors=False)) is None
    assert not SHOP_POOL.checks_front_doors and PROGRESSIVE.checks_front_doors
