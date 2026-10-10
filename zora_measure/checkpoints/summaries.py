"""Checkpoint and Summary, and the helpers the per-area measures share."""

import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zora.model.enums import Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.levels import L9_ENTRY_PERSON_LIST, Level
from zora.model.rooms import Room, StaircaseRoom

SPEC_SHAPES = "shapes-behavior.md @ a7000eb"
SPEC_B1 = "post-shapes-b1.md @ a123227"
SPEC_GATE = "late-gate.md @ 429b79b"
SPEC_GATE_19 = "late-gate.md @ 43eb325"
SPEC_GATE_20 = "late-gate.md @ a6fbf0a"
SPEC_SHAPES_U30 = "shapes-behavior.md @ a6fbf0a"
SPEC_B2 = "post-shapes-b2.md @ a7000eb"
SPEC_B3 = "post-shapes-b3.md @ 2c6aac2"
SPEC_B25 = "post-shapes-b25.md @ a123227"
SPEC_B4 = "post-shapes-b4.md @ a7000eb"
SPEC_B5 = "post-shapes-b5.md @ 2c6aac2"

LEVELS_1_6, LEVELS_7_9 = 0, 1
THREE_LEVEL_CORNER = 0x7F            # the last cell of the levels-7-9 bottom row
BOMB_UPGRADE_LIST = 0x0F
# PS-ITEM-01's twelve progression items, in pool order
POOL_ITEMS = (Item.RECORDER, Item.RAFT, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG,
              Item.LADDER, Item.WAND, Item.BOW, Item.RED_RING, Item.MAGICAL_KEY,
              Item.RED_CANDLE, Item.SILVER_ARROWS, Item.BOOK)


@dataclass(frozen=True)
class Checkpoint:
    spec_id: str
    measure: str                               # what is counted, in game terms
    spec: str                                  # the spec's figure, as stated
    source: str                                # spec file @ commit
    per_rom: Callable[[GameWorld], Any]
    summary: "Summary"


# --- world helpers -------------------------------------------------------------

def _block_levels(gw: GameWorld, block: int) -> list[Level]:
    return gw.levels[:6] if block == LEVELS_1_6 else gw.levels[6:]


def _unowned(gw: GameWorld, block: int) -> list[Room]:
    """Ordinary rooms of the block that no level owns."""
    level_block = gw.blocks[block]
    return [room for room in level_block.rooms if level_block.owner_of(room.room_num) is None]


def _is_blank(room: Room) -> bool:
    """SH-GRID-17's blank room, palette bits aside."""
    blank = Room.blank(room.room_num, room.palette_0, room.palette_1)
    return room == blank


def _level9_person_room(gw: GameWorld) -> Room | None:
    level9 = gw.levels[8]
    return next((r for r in level9.rooms if r.is_person
                 and r.monster_list == L9_ENTRY_PERSON_LIST), None)


def _stair_exits(stair: StaircaseRoom) -> list[int]:
    if stair.room_type == RoomType.TRANSPORT_STAIRCASE:
        return [x for x in (stair.left_exit, stair.right_exit) if x is not None]
    return [x for x in (stair.return_dest, stair.return_dest_b) if x is not None]


def _dungeon_items(gw: GameWorld) -> set[Item]:
    """Items in both blocks' rooms and cellars."""
    items = {room.item for block in gw.blocks for room in block.rooms}
    items |= {s.item for block in gw.blocks for s in block.staircases if s.item is not None}
    return items


def _whole_bomb_upgrade_levels(gw: GameWorld) -> set[int]:
    """Levels holding a person whose whole monster byte is $0F."""
    return {level.level_num for level in gw.levels for room in level.rooms
            if room.has_monster_bit and room.monster_list == BOMB_UPGRADE_LIST
            and room.count_index == 0}


# --- summaries -------------------------------------------------------------------

# One numeric component of a checkpoint, per ROM: a number whose mean over the
# ROMs is the estimate, or a (hits, cases) pair whose ratio of sums is.
Component = float | tuple[float, float]


@dataclass(frozen=True)
class Summary:
    """How a checkpoint's per-ROM values are reported: `text` is the table
    cell over all ROMs; `components` splits one ROM's value into named
    numbers for the noise-aware comparison. `resolve`, when given, first
    turns one sample's per-ROM records into per-ROM values using the whole
    sample (the hint-information classifier, zora_measure/hint_information.py)."""
    text: Callable[[list[Any]], str]
    components: Callable[[Any], dict[str, Component]]
    resolve: Callable[[list[Any]], list[Any]] | None = None

    def column(self, records: list[Any]) -> list[Any]:
        """One sample's per-ROM values, resolved across the sample if needed."""
        return self.resolve(records) if self.resolve is not None else records


def mean_of(fmt: str = "{:.3f}") -> Summary:
    return Summary(lambda values: fmt.format(statistics.mean(values)),
                   lambda value: {"mean": float(value)})


def _count_true(values: list[Any]) -> str:
    return f"{sum(bool(v) for v in values)}/{len(values)}"


count_true = Summary(_count_true, lambda value: {"share": float(bool(value))})


def _flag_counts(values: list[dict[str, bool]]) -> str:
    """ROMs with each named flag set, " / "-separated in key order."""
    return " / ".join(str(sum(v[key] for v in values)) for key in values[0])


FLAG_COUNTS = Summary(_flag_counts, lambda flags: {key: float(hit) for key, hit in flags.items()})


def _key_label(key: Any) -> str:
    if isinstance(key, tuple):
        return "/".join(_key_label(k) for k in key)
    return key.name.lower() if hasattr(key, "name") else str(key)


def distribution(keys: tuple[Any, ...]) -> Summary:
    """Counts of each key, in key order ("a/b/c")."""
    def text(values: list[Any]) -> str:
        counts = Counter(values)
        return "/".join(str(counts[k]) for k in keys)
    return Summary(text, lambda value: {_key_label(k): float(value == k) for k in keys})


def _ratio_text(values: list[tuple[int, int]]) -> str:
    """Sum of hits over sum of cases, for per-ROM (hits, cases) pairs."""
    return f"{sum(h for h, _ in values)}/{sum(n for _, n in values)}"


ratio_total = Summary(_ratio_text, lambda value: {"ratio": (float(value[0]), float(value[1]))})


def per_thousand(values: list[Any]) -> str:
    return f"{1000 * sum(values) / len(values):.0f} per 1,000"


per_thousand_roms = Summary(per_thousand, lambda value: {"per ROM": float(value)})
