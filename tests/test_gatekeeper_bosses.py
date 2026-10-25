"""Gatekeeper Bosses (ZORA flag gatekeeper_bosses, version 12; owner, 2026-10-24; docs/zora-extras.md
section 19; docs/reports/research-gatekeeper-bosses.md): in each level 1-8 one boss room is the only way
into the part holding the triforce. Its shutters open on the kill (trigger 7), its item (what the item
shuffle left in the level's heart-container room) appears then, and the compass lies in front of it.
Level 9 is unchanged."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags import zora_flags, zora_form
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import GatekeeperBosses, ZoraFlags
from zora.generate.late_gate.gatekeeper import (
    GATEKEEPER_BOSSES,
    GATEKEEPER_LEVELS,
    drops_nothing,
    gated_part,
    gatekeeper_problems,
    item_place,
    level_neighbors,
    reached_before,
)
from zora.generate.late_gate.walk import connectivity_walk
from zora.generate.pipeline import Built, build, plan
from zora.generate.shapes.world import D_SHUTTER, D_WALL, side_of
from zora.model.enums import Item, RoomAction
from zora.model.levels import LEVEL_9, Level
from zora.rom.base_rom import remember_repo_base_rom
from zora_measure.checks import check_triforce_of_power

SEEDS = (1, 2, 3)


def gatekeeper_string(setting: GatekeeperBosses = GatekeeperBosses.ANYWHERE, **extras: object) -> str:
    return zora_flags.encode(ZoraFlags(gatekeeper_bosses=setting, **extras))  # type: ignore[arg-type]


@cache
def built(seed: int, zora: str = "", flags: str = MVP_BASELINE_LEVEL_ENCODING_OFF) -> Built:
    return build(plan(flags, seed, zora or gatekeeper_string()), remember_repo_base_rom())


# --- The flag ------------------------------------------------------------------------------------

def test_version_12_holds_gatekeeper_bosses_off_by_default() -> None:
    """Version 12's one field, four values, Off by default: a version-11 string decodes with it off and
    keeps its spelling; each value spells as version 12 and decodes back."""
    field = next(field for field in zora_flags.FIELDS if field.name == "gatekeeper_bosses")
    assert (field.slots, field.version) == (len(GatekeeperBosses), 12)
    version_11 = zora_flags.encode(ZoraFlags(disable_custom_music=True))
    assert version_11.startswith("11.") and zora_flags.decode(version_11).gatekeeper_bosses is GatekeeperBosses.OFF
    for setting in GatekeeperBosses:
        flags = ZoraFlags(gatekeeper_bosses=setting)
        text = zora_flags.encode(flags)
        assert zora_flags.decode(text) == flags
        assert text.startswith("12.") or setting is GatekeeperBosses.OFF


def test_the_form_offers_its_four_values() -> None:
    [field] = [field for field in zora_form.FIELDS if field["name"] == "gatekeeper_bosses"]
    assert field["label"] == "Gatekeeper Bosses" and field["help"]
    assert [value["label"] for value in field["values"]] == ["Off", "Anywhere", "Late", "Early"]
    assert [value["value"] for value in field["values"]] == [int(setting) for setting in GatekeeperBosses]


def test_archipelago_holds_it_back() -> None:
    """Held until the logic is scanned (owner, 2026-10-24): only Off is offered."""
    assert archipelago.HELD_BACK["gatekeeper_bosses"] == frozenset(set(GatekeeperBosses) - {GatekeeperBosses.OFF})


# --- The gatekeepers -------------------------------------------------------------------------------

def assert_gatekeepers_hold(world_levels: list[Level]) -> None:
    for level in world_levels:
        if level.level_num == LEVEL_9:
            assert level.gatekeeper_room is None
            continue
        gatekeeper = level.gatekeeper_room
        assert gatekeeper is not None, level.level_num
        assert gatekeeper_problems(level) == []
        room = level.block.room(gatekeeper)
        assert room.enemy in GATEKEEPER_BOSSES and room.room_action == RoomAction.ALL_DEAD_ITEM
        assert room.item != Item.NOTHING and level.boss_room == gatekeeper
        behind = gated_part(level, gatekeeper)
        assert item_place(level, Item.TRIFORCE) in behind
        assert item_place(level, Item.COMPASS) in reached_before(level, gatekeeper) - {gatekeeper}
        # every passable side into the gated part is a shutter, and the level is whole once it falls
        assert all(side_of(room, side) in (D_SHUTTER, D_WALL)
                   for side, other in level_neighbors(level, gatekeeper) if other in behind)
        assert connectivity_walk(level).passed


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_every_level_1_to_8_has_a_gatekeeper_that_holds(seed: int) -> None:
    assert_gatekeepers_hold(built(seed).world.levels)


@needs_base_rom
@pytest.mark.parametrize("setting", [GatekeeperBosses.LATE, GatekeeperBosses.EARLY])
def test_each_setting_holds(setting: GatekeeperBosses) -> None:
    assert_gatekeepers_hold(built(1, gatekeeper_string(setting)).world.levels)


@needs_base_rom
@pytest.mark.parametrize("setting", [GatekeeperBosses.ANYWHERE, GatekeeperBosses.LATE, GatekeeperBosses.EARLY])
def test_no_room_drops_an_item_it_does_not_hold(setting: GatekeeperBosses) -> None:
    """TFOP-ROOM: filling the gatekeeper moves the heart container's place's item into it, and may move
    the compass forward; the rooms they leave keep no trigger 7, or the kill would show a magical sword
    (or, under the no-item remap, a second triforce of power). Batch run b77c33d, 66 cases."""
    for seed in SEEDS:
        world = built(seed, gatekeeper_string(setting)).world
        assert check_triforce_of_power(world).passed, (seed, check_triforce_of_power(world).message)
        assert not [room.room_num for block in world.level_blocks for room in block.rooms if drops_nothing(room)]


@needs_base_rom
def test_the_settings_order_the_share_behind() -> None:
    """Late leaves the least of the level behind the boss, Early the most (over seeds 1-3)."""
    def share(setting: GatekeeperBosses) -> float:
        shares = [len(gated_part(level, level.gatekeeper_room)) / (len(level.room_nums) - 1)
                  for seed in SEEDS for level in built(seed, gatekeeper_string(setting)).world.levels
                  if level.gatekeeper_room is not None]
        return sum(shares) / len(shares)
    near, anywhere, early = (share(setting) for setting in
                             (GatekeeperBosses.LATE, GatekeeperBosses.ANYWHERE, GatekeeperBosses.EARLY))
    assert near < anywhere < early
    assert early > 2 / 3 * 0.9


@needs_base_rom
@pytest.mark.parametrize(("setting", "lowest", "highest"), [(GatekeeperBosses.LATE, 0.0, 1 / 4),
                                                            (GatekeeperBosses.EARLY, 1 / 2, 1.0)])
def test_late_and_early_keep_their_bounds(setting: GatekeeperBosses, lowest: float, highest: float) -> None:
    """SHARE_ACCEPTED: Late puts at most a quarter of the level's other rooms behind the boss, Early at
    least half."""
    for seed in SEEDS:
        for level in built(seed, gatekeeper_string(setting)).world.levels:
            if level.gatekeeper_room is not None:
                share = len(gated_part(level, level.gatekeeper_room)) / (len(level.room_nums) - 1)
                assert lowest <= share <= highest, (seed, level.level_num, share)


@needs_base_rom
def test_without_the_gate_vanilla_levels_get_gatekeepers() -> None:
    """Dungeon Quest: 1st Quest with Dungeon Room Shuffle: Vanilla (C02 = 0, C14 = 0): the late gate
    does not run (VA-REJ-02), and the levels as they stand take their gatekeepers."""
    first_quest = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C02": 0, "C14": 0}))
    assert_gatekeepers_hold(built(1, gatekeeper_string(), first_quest).world.levels)


@needs_base_rom
def test_with_do_not_segment_dungeons_doors_alone_still_join_each_level() -> None:
    zora = gatekeeper_string(do_not_segment_dungeons=ThreeState.ON)
    levels = built(1, zora).world.levels
    assert_gatekeepers_hold(levels)
    assert all(connectivity_walk(level, transports=False).passed for level in levels)


@needs_base_rom
def test_oops_all_bosses_keeps_the_gatekeepers() -> None:
    zora = gatekeeper_string(oops_all_bosses=zora_flags.OopsAllBosses.DODONGOS)
    assert_gatekeepers_hold(built(1, zora).world.levels)


@needs_base_rom
def test_with_item_shuffle_none_the_heart_container_moves_into_the_gatekeeper() -> None:
    """Owner decision 5: the gatekeeper holds what the item shuffle left in the heart container's
    room; with Item Shuffle: None (C06 = 0) that is the heart container itself."""
    unshuffled = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C06": 0}))
    for level in built(1, gatekeeper_string(), unshuffled).world.levels:
        if level.level_num in GATEKEEPER_LEVELS:
            assert level.gatekeeper_room is not None
            assert level.block.room(level.gatekeeper_room).item == Item.HEART_CONTAINER


@needs_base_rom
def test_off_has_no_gatekeepers() -> None:
    off = built(1, zora_flags.encode(ZoraFlags(randomize_letter=True))).world
    assert all(level.gatekeeper_room is None for level in off.levels)
