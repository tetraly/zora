"""Universal Drops v2.0 (ZORA flag universal_drops_v2, version 19; owner rulings 2026-11-05; docs/zora-extras.md
section 26): never with Allow Universal Drops In Shapes (B91); on built seeds every room item stands on its
screen type's drop squares, each level keeps the center at its index, only Triforce rooms take the center,
never a door square, and Highlight No-Drop Rooms
marks no room that holds an item. The step's own rules: the coverage rule, and only the item moves when the
drops are dealt."""
import re
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import UNIVERSAL_DROPS_V2_CONFLICT, ZoraFlags
from zora.generate.drop_square_table import DROP_SQUARES
from zora.generate.drop_squares import misplaced_drops
from zora.generate.pipeline import Built, FlagsRefused, build, plan
from zora.generate.rng import Rng
from zora.generate.steps.highlight_no_drop_rooms import MARKED_PALETTE
from zora.generate.steps.universal_drops_v2 import (
    CANDIDATE_SQUARES,
    CENTER,
    deal_drops,
    place_on_drop_square,
)
from zora.model.enums import Item
from zora.model.rooms import LayoutInfo
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom
ON = zora_flags.encode(ZoraFlags(universal_drops_v2=ThreeState.ON, highlight_no_drop_rooms=ThreeState.ON))
# The MVP baseline (level encoding off), and with Remove Most Open Stairs (B30) and Shuffle Minor Dungeon
# Drops (B17) on: the passes that change a room's layout or move its item after the shape stage
FLAGS = {"baseline": MVP_BASELINE_LEVEL_ENCODING_OFF,
         "B30 and B17": encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
             toggles={"B30": ThreeState.ON, "B17": ThreeState.ON}))}
SEEDS = (1, 2, 3)
# The door squares, where Link stands as he comes in: the top and bottom rows' two middle squares, the middle
# row's end squares
DOOR_SQUARES = {0x76, 0x86, 0x29, 0xD9, 0x7C, 0x8C}


@cache
def built(flags: str, seed: int) -> Built:
    return build(plan(flags, seed, ON), remember_repo_base_rom())


@pytest.mark.parametrize("b91", [ThreeState.ON, ThreeState.POSSIBLE], ids=["B91 on", "B91 ?"])
@pytest.mark.parametrize("v2", [ThreeState.ON, ThreeState.POSSIBLE], ids=["on", "?"])
def test_never_with_allow_universal_drops_in_shapes(b91: ThreeState, v2: ThreeState) -> None:
    with_b91 = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B91": b91}))
    with pytest.raises(FlagsRefused, match=re.escape(UNIVERSAL_DROPS_V2_CONFLICT[:30])):
        plan(with_b91, 1, zora_flags.encode(ZoraFlags(universal_drops_v2=v2)))
    assert UNIVERSAL_DROPS_V2_CONFLICT.startswith("Universal Drops v2.0")


def test_held_back_from_archipelago() -> None:
    assert "universal_drops_v2" in archipelago.NOT_OFFERED


def test_the_candidates_are_t5s_squares_and_never_a_door_square() -> None:
    """No drop stands where Link comes in through a door (CustomShield's report on 2.0.1)."""
    assert len(CANDIDATE_SQUARES) == 11 and CENTER not in CANDIDATE_SQUARES
    assert not DOOR_SQUARES & set(CANDIDATE_SQUARES)


def test_every_screen_type_with_drop_squares_keeps_a_candidate() -> None:
    """Leaving out the door squares leaves no screen type with drop squares but none among the candidates,
    so the coverage rule never fails for want of one."""
    assert [f"${code:02X}" for code, squares in DROP_SQUARES.items()
            if squares and not squares & set(CANDIDATE_SQUARES)] == []


@pytest.mark.parametrize("name", list(FLAGS))
@pytest.mark.parametrize("seed", SEEDS)
def test_built_seeds(name: str, seed: int) -> None:
    world = built(FLAGS[name], seed).world
    assert misplaced_drops(world.levels) == []
    for level in world.levels:
        table = level.item_position_table
        assert CENTER in table and len(set(table)) == len(table)
        assert not DOOR_SQUARES & set(table), (level.level_num, [f"${square:02X}" for square in table])
        for room in level.rooms:
            if room.item != Item.NOTHING:
                assert room.palette_1 != MARKED_PALETTE, (level.level_num, f"${room.room_num:02X}")
            # the center is the Triforce rooms' alone (Ganon's Triforce of Power drops at his ashes)
            if room.item not in (Item.NOTHING, Item.TRIFORCE, Item.TRIFORCE_OF_POWER):
                assert table[room.item_position] != CENTER, (level.level_num, f"${room.room_num:02X}", room.item)


def test_the_center_keeps_its_index() -> None:
    """Item cellars point at the center's index (SH-STAIR-16), so the level tables keep it there."""
    off = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1), remember_repo_base_rom()).world
    on = built(FLAGS["baseline"], 1).world
    for before, after in zip(off.levels, on.levels, strict=True):
        assert after.item_position_table.index(CENTER) == before.item_position_table.index(CENTER)


def test_dealing_moves_only_the_item() -> None:
    rooms = parse_rom(remember_repo_base_rom()).levels[0].rooms[:6]
    rooms[0].item_info = replace(rooms[0].item_info, item=Item.KEY, is_dark=True)
    before = [(room.item_info.is_dark, room.item_info.boss_sound) for room in rooms]
    items = sorted(room.item for room in rooms)
    deal_drops(rooms, Rng(7))
    assert [(room.item_info.is_dark, room.item_info.boss_sound) for room in rooms] == before
    assert sorted(room.item for room in rooms) == items


def test_the_center_is_the_triforce_rooms_alone() -> None:
    """A room holding a Triforce piece takes the center whenever its squares hold it; every other room draws
    uniformly among the other three positions its squares hold, never the center (CustomShield's report on
    2.0.1; it replaces ruling 2026-11-06's center half the time)."""
    level = parse_rom(remember_repo_base_rom()).levels[0]
    room = level.rooms[0]
    level.item_position_table[:] = [CENTER, 0x26, 0x2C, 0xDC]
    plain = next(code for code, squares in DROP_SQUARES.items() if set(level.item_position_table) <= squares)
    room.layout_info = LayoutInfo.from_layout_code(plain)
    rng, draws = Rng(11), 3000
    others = {0x26, 0x2C, 0xDC}
    for item, expected in ((Item.TRIFORCE, {CENTER}), (Item.KEY, others), (Item.NOTHING, others)):
        room.item_info = replace(room.item_info, item=item)
        squares = set()
        for _ in range(draws if item != Item.TRIFORCE else 10):
            place_on_drop_square(level, room, rng)
            squares.add(level.item_position_table[room.item_position])
        assert squares == expected, (item, squares)
