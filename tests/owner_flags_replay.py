"""Beatability of a finished seed under the owner's 2.0 flags, judged on the FINISHED ROM.

The generator's acceptance check runs on its staged model. This replays it on what shipped: the
seed is generated, serialized and parsed back; every tracked item must sit in the parsed ROM where
the generator's records put it; then the acceptance check's E1 (VA-REJ-07 with the seed's logic
rules: the overworld gates, the maze hints, the potion shop's letter) and E3 run on the parsed
levels and overworld. The flags' own invariants are checked too (zora_measure/owner_flags.py).
Shared by tests/test_owner_flags_wired.py and scripts/qa_sweep.py-style runs in temp/.
"""
from __future__ import annotations

from dataclasses import dataclass

from zora.flags.zora_flags import L4Sword
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.pipeline import extra_options, generate_world, overworld_gates, plan
from zora.generate.steps.item_shuffle_result import EXTRA_SLOT_CAVES, shop_of_slot
from zora_measure.owner_flags import owner_flag_problems
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, OverworldItem, Shop
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

CAVE_SLOT_DESTINATIONS = {"armos": Destination.ARMOS_ITEM, "white_sword": Destination.WHITE_SWORD_CAVE,
                          "coast": Destination.COAST_ITEM}
ITEM_CODE = 0x3F


@dataclass
class Replay:
    rom: bytes
    problems: list[str]

    @property
    def beatable(self) -> bool:
        return not self.problems


def _holds(world: GameWorld, place_item: int, level: int | None, slot: str | None) -> bool:
    """The parsed ROM holds the item at a tracked record's place."""
    item = place_item & ITEM_CODE
    overworld = world.overworld
    if level is not None:
        levels = [lv for lv in world.levels if lv.level_num == level]
        rooms = [int(room.item) & ITEM_CODE for lv in levels for room in lv.rooms]
        cellars = [int(stair.item) & ITEM_CODE for lv in levels for stair in lv.block.staircases
                   if stair.item is not None and stair.return_dest in lv.room_nums]
        return item in rooms or item in cellars
    assert slot is not None
    if slot in CAVE_SLOT_DESTINATIONS:
        slot_cave = next(c for c in overworld.caves if c.destination == CAVE_SLOT_DESTINATIONS[slot])
        assert isinstance(slot_cave, (ItemCave, OverworldItem))
        return int(slot_cave.item) & ITEM_CODE == item
    if slot in EXTRA_SLOT_CAVES:
        extra_cave = overworld.get_cave(EXTRA_SLOT_CAVES[slot], ItemCave)
        return extra_cave is not None and int(extra_cave.item) & ITEM_CODE == item
    shop_destination = shop_of_slot(slot)
    assert shop_destination is not None, slot
    shop = overworld.get_cave(shop_destination, Shop)
    position = int(slot.split()[-1])
    return isinstance(shop, Shop) and int(shop.ware(position).item) & ITEM_CODE == item


def replay(flags: str, seed: int, zora: str, base: bytes) -> Replay:
    chosen = plan(flags, seed, zora)
    staged, result = generate_world(chosen, base)
    rom = serialize_to_rom(staged, base, config=chosen.config)
    world = parse_rom(rom)
    problems: list[str] = []
    state = result.item_shuffle_result
    assert state is not None and result.overworld is not None
    problems.extend(f"tracked {Item(place.item & ITEM_CODE).name} not at {place.level or place.slot}"
                    for place in state.tracked if not _holds(world, place.item, place.level, place.slot))
    extras = extra_options(chosen)
    check = AcceptanceCheck(world.levels, state, world.overworld, result.overworld, extras.logic_rules)
    if not check.collects_everything():
        problems.append("E1 fails on the finished ROM")
    if not check.is_zelda_reachable():
        problems.append("E3 fails on the finished ROM")
    problems += owner_flag_problems(world, overworld_gates(chosen.zora_resolved),
                                    chosen.zora_resolved.l4_sword is L4Sword.LEVEL_9,
                                    chosen.zora_resolved.l4_sword is L4Sword.LEVEL_2)
    return Replay(rom, problems)
