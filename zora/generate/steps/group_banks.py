"""The enemy and boss group passes' shared pieces: the groups, sprite objects
and the writes staged outside the room blocks."""

from dataclasses import dataclass, field

from ...model.enums import Enemy
from ...model.sprites import PatternBlock

E = Enemy
DISCARDED_DRAWS = 2
OVERWORLD = 3              # enemy group 3 (the overworld); boss block 3 (the common block)
GROUPS = (0, 1, 2, OVERWORLD)                    # groups 0-2 = enemy bank tiers 0-2


# --- PS-EGRP-01: the roster ------------------------------------------------------

@dataclass(frozen=True)
class SpriteObject:
    """An object whose tiles the repack copies (post-shapes-b5.md appendix):
    its tile count, source run (block, byte offset) and frame entries
    (ObjAnimFrameHeap offset, count; count 0 = none renumbered)."""
    tiles: int
    source: tuple[PatternBlock, int]
    frames: tuple[int, int]


@dataclass
class Staged:
    """Writes outside the room blocks, applied when the pass ships."""
    tiles: list[tuple[PatternBlock, int, bytes]] = field(default_factory=list)
    frames: dict[int, int] = field(default_factory=dict)          # heap offset -> byte
    aquamentus_tiles: list[int] | None = None
    aquamentus_open_mouth: int | None = None
    gleeok_body_tiles: list[int] | None = None
    gleeok_neck: int | None = None
    gleeok_head: int | None = None
    mixed_lists: bytearray | None = None
    overworld_monsters: dict[int, Enemy] = field(default_factory=dict)
    item_carrier_operands: tuple[int, int, int] | None = None
    red_wizzrobe_overworld: bool = False     # the four overworld-Wizzrobe byte runs
