"""Options for the shapes generator.

Defaults follow the spec text; options whose tables are missing from the spec
default off (see QUESTIONS.md #1/#2).

Options that are accepted but cannot yet produce correct output are listed in
BLOCKED_OPTIONS: any non-default value raises NotImplementedError at
construction, naming what the option waits on, so a blocked option fails at
once instead of inside the generation's retry loop.
"""
from dataclasses import dataclass

from ...rom.game_config import reject_blocked_options

# option name -> what it waits on
BLOCKED_OPTIONS = {
    "seed_placement": "QUESTIONS #29-33",
}


@dataclass(frozen=True)
class ShapeOptions:
    # SH-NUM-02: off means the size order is mapped through a shuffled list.
    sort_shapes: bool = True
    # SH-GRID-02 / SH-ENT-01: levels may start on any row and entrances be
    # anywhere (the "start room swap" option).
    start_room_swap: bool = False
    # SH-DOOR-02: add second-quest door weights (T1b; brings in walk-through walls). B21.
    second_quest_doors: bool = False
    # SH-STAIR-05 / SH-ROOM-09: add second-quest weights to stair/room layout
    # tables (both ARE given: T2 additions + T4 "Second quest addition").
    # Default True measured against the shapes-stage corpus (400 seeds):
    # trigger_push_stairs 3.99->7.90 (ref 9.18), item_bombs 9.74->8.63
    # (8.51), item_none 60.2->65.6 (68.4), person rooms 12.0->13.6 (14.35),
    # kill-for-item 37.4->34.9 (33.1). Pending the flag-set confirmation
    # (QUESTIONS #2 noted "second quest DOORS off" — doors stay off; rooms
    # are a different flag).
    second_quest_rooms: bool = True
    # SH-ENEMY-01: add second-quest levels' monster groups to the pools.
    second_quest_monsters: bool = False
    # SH-ROOM-11: extra allowed item positions ("universal drops in shapes").
    universal_drops: bool = False
    # SH-GRID-06 seed-cell placement. Blocked: nothing reads it; gridgen
    # always uses the SH-GRID-06 draw (QUESTIONS #29-33).
    seed_placement: str = "reference"
    # ASNB (docs/design/asnb.md section 4; ZORA's Add L4 Sword = Level 2): level 2's stair budget
    # is 1, an item cellar holding one sword upgrade (SH-STAIR-02/03 give it none).
    level_2_sword_cellar: bool = False
    # Do Not Segment Dungeons (ZORA flag, version 10; docs/reports/research-candles-and-segments.md
    # section 2): growth makes one piece per level (no SH-GRID-06 seed cells, the probe only beside
    # the level's own cells), and the late gate walks the level's doors without its transport
    # staircases, so its repair opens walls until doors alone join every room.
    do_not_segment_dungeons: bool = False

    def __post_init__(self) -> None:
        reject_blocked_options(self, BLOCKED_OPTIONS)
