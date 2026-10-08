"""The owner's 2.0 overworld gates (docs/design/zora-flags-2.0.md sections 3, 4, 12, 13; owner
decisions 2026-10-07): the screens each flag puts behind the raft, the power bracelet, the
ladder or a maze's hint, for the cave shuffle's placement rules and the acceptance check.

The block screens are the document's. The maze sets are derived from the overworld map
(zora/rom/vanilla_overworld/walkability.py), on the layouts as the flags' patches leave them,
from PRG0's start screen $77; tests/test_overworld_gates.py derives them again. The engine's
mazes (aldonunez CheckMazes): leaving a maze screen repeats it unless the step matches the
sequence (the fourth match leaves in its direction) or the side is the maze's free exit
(Lost Hills: west; Dead Woods: east). A different start screen (OW-START-01) only makes fewer
screens gated, so the sets hold for every start.
"""
from dataclasses import dataclass

from zora.model.enums import Destination, Item

# Extra Raft Blocks (§3): open to raft, and $1E bomb to raft-and-bomb (the wooden sword is always
# held, so raft-and-bomb needs the raft alone).
RAFT_BLOCK_SCREENS = frozenset({0x0E, 0x0F, 0x1E, 0x1F, 0x34, 0x44})
# Extra Power Bracelet Blocks (§4): bomb to bracelet-and-bomb on West Death Mountain.
BRACELET_BLOCK_SCREENS = frozenset({0x00, 0x01, 0x02, 0x03, 0x10, 0x12, 0x13})

LOST_HILLS_SCREEN = 0x1B              # MountainMazeDirs' maze (CheckMazes)
DEAD_WOODS_SCREEN = 0x61              # ForestMazeDirs' maze
# Randomize Lost Hills: with its patch's edits, $0B-$0D are reached only through the maze (its
# fixed last step is up, to $0B); the ladder does not help.
LOST_HILLS_GATED = frozenset({0x0B, 0x0C, 0x0D})
# Randomize Dead Woods: the fixed last step is south (owner decision), to $71; with its patch's
# edit $70-$71 are reached only through the maze.
DEAD_WOODS_GATED = frozenset({0x70, 0x71})
# ... and the forest no longer leads west: the west half of the map, reached in PRG0 only through
# the forest's west exit or with the ladder over a one-square river, then needs the ladder.
DEAD_WOODS_WEST = frozenset({
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15,
    0x16, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x30, 0x31, 0x32, 0x33, 0x35, 0x36, 0x40, 0x41,
    0x50, 0x60,
})
# The hint shop that sells each maze's path in PRG0 (texts 11 and 12) sells the new one, for 1
# rupee (owner design); reaching it is the maze's hint.
LOST_HILLS_HINT_SHOP = Destination.HINT_SHOP_1
DEAD_WOODS_HINT_SHOP = Destination.HINT_SHOP_2
# The held set's pseudo-items for each maze's hint (as acceptance_check.LEVEL9_ENTRY).
LOST_HILLS_HINT = -10
DEAD_WOODS_HINT = -11


@dataclass(frozen=True)
class OverworldGates:
    """Which of the owner's overworld gates a seed has (its resolved flags)."""
    raft_blocks: bool = False
    bracelet_blocks: bool = False
    lost_hills: bool = False
    dead_woods: bool = False

    @property
    def any(self) -> bool:
        return self.raft_blocks or self.bracelet_blocks or self.lost_hills or self.dead_woods

    def screen_needs(self) -> tuple[tuple[frozenset[int], int], ...]:
        """The acceptance check's extra screen sets, each with what it needs."""
        needs: list[tuple[frozenset[int], int]] = []
        if self.raft_blocks:
            needs.append((RAFT_BLOCK_SCREENS, Item.RAFT))
        if self.bracelet_blocks:
            needs.append((BRACELET_BLOCK_SCREENS, Item.POWER_BRACELET))
        if self.lost_hills:
            needs.append((LOST_HILLS_GATED, LOST_HILLS_HINT))
        if self.dead_woods:
            needs.append((DEAD_WOODS_GATED, DEAD_WOODS_HINT))
            needs.append((DEAD_WOODS_WEST, Item.LADDER))
        return tuple(needs)

    def maze_hints(self) -> tuple[tuple[int, Destination], ...]:
        """Each gated maze's hint pseudo-item and the hint shop that gives it."""
        hints = []
        if self.lost_hills:
            hints.append((LOST_HILLS_HINT, LOST_HILLS_HINT_SHOP))
        if self.dead_woods:
            hints.append((DEAD_WOODS_HINT, DEAD_WOODS_HINT_SHOP))
        return tuple(hints)

    def gated_screens(self) -> frozenset[int]:
        """Every screen one of the gates puts something in front of."""
        return frozenset().union(*(screens for screens, _ in self.screen_needs()))

    def wood_sword_barred(self) -> frozenset[int]:
        """Screens the wooden-sword cave may not move to: every gated screen (the sword is the
        start's; never behind a maze, owner decision)."""
        return self.gated_screens()

    def barred_for(self, code: Destination) -> frozenset[int]:
        """Screens a cave may not move to: a hint shop never behind its own maze."""
        if self.lost_hills and code == LOST_HILLS_HINT_SHOP:
            return LOST_HILLS_GATED
        if self.dead_woods and code == DEAD_WOODS_HINT_SHOP:
            return DEAD_WOODS_GATED
        return frozenset()


NO_GATES = OverworldGates()
