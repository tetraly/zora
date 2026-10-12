"""Force Overworld Block (B81; overworld-behavior.md OW-CAVE-08): at the end of the cave pass, a
cave result with no dungeon door and no white-sword cave behind an item gate restarts the whole
seed, as an acceptance rejection does (VA-REJ-06). B81 writes no byte."""
from ...model.enums import Destination
from ...model.overworld import Overworld
from .cave_entries import BRACELET_SCREENS, LADDER_SCREENS, RAFT_SCREENS, CaveShuffle, recorder_screens

# The item-gate sets of OW-APP-A4 the test reads: the Recorder set as the overworld quest gives it,
# the Raft and Ladder sets, and the Bracelet set without 32 and 33 (BRACELET_SCREENS holds none of
# them); the Burnable set does not count.
NOT_AN_ITEM_GATE_FAILURE = "no dungeon door or white-sword cave behind an item gate (OW-CAVE-08)"


def item_gate_screens(overworld: Overworld) -> frozenset[int]:
    return recorder_screens(overworld) | RAFT_SCREENS | LADDER_SCREENS | BRACELET_SCREENS


def has_gated_door(overworld: Overworld, caves: CaveShuffle) -> bool:
    """OW-CAVE-08's test: some cave-list entry holding a dungeon code (1-9) or the white-sword cave
    (code 18) stands on an item-gate screen. Only entries count, at their final screens (an
    entry the Armos formation re-pointed counts at 36): a fixed screen never does."""
    gated = item_gate_screens(overworld)
    return any(entry.screen in gated and (entry.code.is_level or entry.code == Destination.WHITE_SWORD_CAVE)
               for entry in caves.entries)


def force_overworld_block(overworld: Overworld, caves: CaveShuffle) -> str | None:
    """OW-CAVE-08: the restart reason when the test fails, else None."""
    return None if has_gated_door(overworld, caves) else NOT_AN_ITEM_GATE_FAILURE
