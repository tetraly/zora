"""Allow Universal Drops In Shapes (B91; shapes-behavior.md SH-ROOM-16): the Checks measured on
finished ROMs, against the b91 and b91-possible corpora, the MVP baseline corpus string with B91 on
and possible (zora_measure.corpora.corpus(name); hash manifests
docs/spec/corpus-b91-final-hash-manifest.csv and corpus-b91-possible-final-hash-manifest.csv)."""
from zora.generate.shapes.t5_positions import T5_BASE, t5_row
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.rooms import Room
from zora_measure.checkpoints.summaries import Checkpoint, Summary

SPEC_B91 = "shapes-behavior.md @ 1fd481e"
UNIVERSAL_DROPS_FLAGS = "3yQg5tF2n5KQHhSYHvzCNJnLSpcGkbm9GgwiUJ3A"            # B91 on
UNIVERSAL_DROPS_POSSIBLE_FLAGS = "7vrLBlU5ZAW8kJjS8pdrxVQVcbE4EO3uXJzHUJ3A"   # B91 possible


def _item_rooms(gw: GameWorld) -> list[tuple[Room, int]]:
    """Every level room holding an item, with the screen position its item stands on."""
    return [(room, level.item_position_table[room.item_position])
            for level in gw.levels for room in level.rooms if room.item != Item.NOTHING]


def rooms_without_base_row(gw: GameWorld) -> int:
    """SH-ROOM-16: item rooms whose screen type has no base T5 row (only the merged list seats an
    item there)."""
    return sum(room.layout_code not in T5_BASE for room, _position in _item_rooms(gw))


def positions_in_rows(gw: GameWorld) -> tuple[int, int, int]:
    """SH-ROOM-16: (item rooms whose position is in the merged row, in the base row, item rooms)."""
    rooms = _item_rooms(gw)
    merged = sum(position in t5_row(room.layout_code, universal_drops=True) for room, position in rooms)
    base = sum(position in t5_row(room.layout_code, universal_drops=False) for room, position in rooms)
    return merged, base, len(rooms)


def _rooms_and_roms(values: list[int]) -> str:
    return f"{sum(values):,} rooms in {sum(value > 0 for value in values)} ROMs"


ROOMS_AND_ROMS = Summary(_rooms_and_roms, lambda value: {"rooms": float(value), "share": float(value > 0)})


def _rows_text(values: list[tuple[int, int, int]]) -> str:
    merged, base, total = (sum(value[index] for value in values) for index in range(3))
    return f"{merged:,} / {base:,} of {total:,}"


IN_ROWS = Summary(_rows_text, lambda value: {"merged": (float(value[0]), float(value[2])),
                                             "base": (float(value[1]), float(value[2]))})

UNIVERSAL_DROPS_SETS = {
    "b91": (
        Checkpoint("SH-ROOM-16", "item rooms on a screen type without a base row", "2,100 rooms in 867 ROMs "
                   "(CP-5: 0)", SPEC_B91, rooms_without_base_row, ROOMS_AND_ROMS),
        Checkpoint("SH-ROOM-16", "item rooms positioned in the merged row / in the base row",
                   "112,880 / 59,637 of 113,127", SPEC_B91, positions_in_rows, IN_ROWS),
    ),
    "b91-possible": (
        Checkpoint("SH-ROOM-16", "item rooms on a screen type without a base row",
                   "1,060 rooms in 471 ROMs (expected about 434 ROMs)", SPEC_B91, rooms_without_base_row,
                   ROOMS_AND_ROMS),
    ),
}
UNIVERSAL_DROPS_FLAGS_BY_SET = {"b91": UNIVERSAL_DROPS_FLAGS, "b91-possible": UNIVERSAL_DROPS_POSSIBLE_FLAGS}
