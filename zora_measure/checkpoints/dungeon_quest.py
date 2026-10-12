"""Dungeon Quest (C02; shapes-behavior.md SH-SRC-01 to SH-SRC-10, post-shapes-b9.md PS-VAN-01 to
PS-VAN-07, post-shapes-b1.md PS-ROOM-16): the Checks measured on finished ROMs. The spec's figures
are the original randomizer's c02-quest1, c02-quest2, c02-mixed, c02-mixshapes, c02-random-noshapes
and c02-random corpora (zora_measure.corpora.corpus(name); hash manifests in docs/spec/)."""
from collections import Counter
from functools import cache

from zora.generate.steps.dungeon_quest import SET_LEVELS, SetSource
from zora.generate.steps.shuffle_items import POOL_ORDER
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.rooms import ITEM_MASK, MONSTER_LIST_BITS, Room, StaircaseRoom
from zora_measure.checkpoints.acceptance import _cave_slots
from zora_measure.checkpoints.mixed_overworld import prg0_world
from zora_measure.checkpoints.summaries import Summary, distribution

SPEC_SRC = "shapes-behavior.md @ eca85cc"
SPEC_VAN = "post-shapes-b9.md @ 95e983b"   # V25: trigger bytes are PRG0's
SPEC_ROOM16 = "post-shapes-b1.md @ eca85cc"
FLAGS_CP5_PREFIX = "8hq4BeR1JXo89BJ2!TFpTP02u8"
# SH-SRC-07: each value's corpus string, the MVP baseline's with only C02 changed
FIRST_QUEST_DUNGEONS_FLAGS = FLAGS_CP5_PREFIX + "UJ2n"
SECOND_QUEST_DUNGEONS_FLAGS = FLAGS_CP5_PREFIX + "UJ2v"
MIXED_DUNGEONS_FLAGS = FLAGS_CP5_PREFIX + "UJ32"
MIXED_WITH_SHAPES_FLAGS = FLAGS_CP5_PREFIX + "UJ3I"
RANDOM_NO_SHAPES_FLAGS = FLAGS_CP5_PREFIX + "UJ3Q"
RANDOM_DUNGEONS_FLAGS = FLAGS_CP5_PREFIX + "UJ3Y"

SOURCE_PAIRS = tuple((first, second) for first in SetSource for second in SetSource)
# PS-VAN-07: PRG0's second-quest people (monster low six bits), levels 1-8
PRG0_SECOND_QUEST_PEOPLE = {5: (0x0F, 0x11, 0x12), 6: (0x12,), 7: (0x0F,), 8: (0x11, 0x11)}
ZELDA_MONSTER = 0x37
GANON_MONSTER = 0x3E
START_ROOM_LAYOUT = 0x21
HEART_CONTAINERS = 9


@cache
def _prg0_maps() -> dict[int, tuple[int, bytes, bytes]]:
    return {level.level_num: _map_bytes(level) for level in prg0_world().levels}


def _map_bytes(level: Level) -> tuple[int, bytes, bytes]:
    """SH-SRC-02's map bytes: $2D and $3F-$7B."""
    return level.map_start, level.map_data, level.map_ppu_commands


def set_sources(gw: GameWorld) -> tuple[SetSource, SetSource]:
    """SH-SRC-02/03: each set's source: second quest when its levels point at the second-quest
    block; first quest when they point at the first-quest block and their maps are PRG0's
    first-quest maps; shapes otherwise."""
    sources = []
    for set_index, level_nums in enumerate(SET_LEVELS):
        levels = [gw.levels[level_num - 1] for level_num in level_nums]
        if levels[0].block is gw.blocks_2q[set_index]:
            sources.append(SetSource.SECOND_QUEST)
        elif all(_map_bytes(level) == _prg0_maps()[level.level_num] for level in levels):
            sources.append(SetSource.FIRST_QUEST)
        else:
            sources.append(SetSource.SHAPES)
    return sources[0], sources[1]


SOURCE_PAIR_SHARES = distribution(SOURCE_PAIRS)


def monster_branches(gw: GameWorld) -> dict[str, bool]:
    """SH-SRC-05/09: the three quest-number branches, against the set sources."""
    second = SetSource.SECOND_QUEST in set_sources(gw)
    return {"$D0": gw.monsters_take_second_quest_path, "second-quest set": second,
            "$D0 with a second-quest set": gw.monsters_take_second_quest_path and second}


def level_3_guard(gw: GameWorld) -> dict[str, bool]:
    """PS-ROOM-16: $34 of level 3 when levels 1-6 are first quest."""
    first_quest = set_sources(gw)[0] is SetSource.FIRST_QUEST
    level_3 = gw.levels[2]
    return {"levels 1-6 first quest": first_quest,
            "$0F there": first_quest and level_3.stairway_data_raw[0] == 0x0F}


def bomb_upgrade_moves(gw: GameWorld) -> dict[str, bool]:
    """SH-SRC-08: the bomb-upgrade path's branch: the move ran ($EA $EA) or PRG0's code ($90 $08,
    levels 5 and 7)."""
    return {"moved": gw.bomb_upgrade_levels is not None, "PRG0's": gw.bomb_upgrade_levels is None}


def level_2_bank(gw: GameWorld) -> dict[str, bool]:
    """PS-VAN-04: level 2's enemy sprite bank equals level 7's (with levels 1-6 second quest)."""
    second = set_sources(gw)[0] is SetSource.SECOND_QUEST
    same = gw.levels[1].enemy_sprite_set == gw.levels[6].enemy_sprite_set
    return {"levels 1-6 second quest": second, "bank = level 7's there": second and same,
            "equal otherwise": not second and same}


def _people(level: Level) -> tuple[int, ...]:
    return tuple(sorted(room.enemy_info.enemy & MONSTER_LIST_BITS for room in level.rooms if room.is_person))


def second_quest_people(gw: GameWorld) -> tuple[int, int]:
    """PS-VAN-07: second-quest levels 1-8 whose people keep PRG0's values, of all such levels."""
    levels = [level for level in gw.levels[:8] if level.block in gw.blocks_2q]
    kept = sum(_people(level) == PRG0_SECOND_QUEST_PEOPLE.get(level.level_num, ()) for level in levels)
    return kept, len(levels)


def _items_in_use(gw: GameWorld) -> Counter[int]:
    items: Counter[int] = Counter()
    for block in {id(level.block): level.block for level in gw.levels}.values():
        for cell in block.cells:
            if isinstance(cell, Room):
                items[cell.item_info.item_code] += 1
            elif isinstance(cell, StaircaseRoom) and cell.item is not None:
                items[int(cell.item)] += 1
    return items


def item_invariants(gw: GameWorld) -> dict[str, bool]:
    """PS-VAN-03: over the two blocks in use (all 128 cells each) and the three special-cave items,
    each of the twelve progression items once, and nine heart containers."""
    items = _items_in_use(gw)
    for item in _cave_slots(gw).values():
        items[int(item) & ITEM_MASK] += 1
    return {"twelve once": all(items[code] == 1 for code in POOL_ORDER),
            "nine hearts": items[int(Item.HEART_CONTAINER)] == HEART_CONTAINERS}


def level_9_rooms(gw: GameWorld) -> dict[str, bool]:
    """PS-VAN-01: level 9's block holds exactly one Zelda room (monster $37, no monster bit) and
    one Ganon room (low six bits $3E, no monster bit)."""
    rooms = [cell for cell in gw.levels[8].block.cells if isinstance(cell, Room)]
    zelda = sum(room.enemy_info.enemy == ZELDA_MONSTER for room in rooms)
    ganon = sum(room.enemy_info.enemy == GANON_MONSTER for room in rooms)
    return {"one Zelda": zelda == 1, "one Ganon": ganon == 1}


def start_rooms(gw: GameWorld) -> tuple[int, int]:
    """PS-VAN-01: levels whose start room is in the level and has layout $21."""
    good = sum(level.entrance_room in level.room_nums
               and level.block.room(level.entrance_room).layout_info.room_type == START_ROOM_LAYOUT
               for level in gw.levels)
    return good, len(gw.levels)


def hungry_goriya_rooms(gw: GameWorld) -> int:
    """SH-SRC-08: hungry-goriya rooms (monster $36, no monster bit) in the first-quest blocks
    the levels read (a block no level reads is left out: docs/deviations.md)."""
    read = [block for block in gw.level_blocks if any(block is first for first in gw.blocks)]
    return sum(isinstance(cell, Room) and cell.enemy_info.enemy == 0x36
               for block in read for cell in block.cells)


def trigger_7_without_item(gw: GameWorld) -> tuple[int, int]:
    """PS-VAN-02's Check (V25): rooms of the nine levels that end with trigger 7 (the item
    appears when the foes fall) and no item, of all the levels' rooms."""
    rooms = [room for level in gw.levels for room in level.rooms]
    return sum(room.item == Item.NOTHING and room.item_appears_on_clear for room in rooms), len(rooms)


def _range_text(values: list[int]) -> str:
    counts = Counter(values)
    return ", ".join(f"{value}: {counts[value]}" for value in sorted(counts))


HUNGRY_GORIYA_COUNTS = Summary(_range_text, lambda value: {"one": float(value == 1)})

