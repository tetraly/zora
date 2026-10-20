"""The owner's 2.0 overworld gates (docs/design/zora-flags-2.0.md sections 3, 4, 12, 13; owner
decisions 2026-10-07): the screens each flag puts behind the raft, the power bracelet, the
ladder or a maze's hint, for the cave shuffle's placement rules and the acceptance check. A screen
needs a maze's hint only when its cave entrance is reached solely through the maze; Add Lost Woods
Shortcut (B88) and Add Bridges to the River (B87) give the Dead Woods' west half another way in.

The block screens are the document's. The maze sets are derived from the overworld map
(zora/rom/vanilla_overworld/walkability.py), on the layouts as the flags' patches leave them,
from PRG0's start screen $77; tests/test_overworld_gates.py derives them again. The engine's
mazes (aldonunez CheckMazes): leaving a maze screen repeats it unless the step matches the
sequence (the fourth match leaves in its direction) or the side is the maze's free exit
(Lost Hills: west; Dead Woods: east). The sets are judged from a start outside them: the
start-screen draw (OW-START-01, -02) leaves out the screens past each randomized maze and the
screens the raft and bracelet edits wall in (start_barred).
"""
from dataclasses import dataclass

from ...model.enums import Destination, Item

# Extra Raft Blocks (§3): open to raft, and $1E bomb to raft-and-bomb (the wooden sword is always
# held, so raft-and-bomb needs the raft alone).
RAFT_BLOCK_SCREENS = frozenset({0x0E, 0x0F, 0x1E, 0x1F, 0x34, 0x44})
# Extra Power Bracelet Blocks (§4): bomb to bracelet-and-bomb on West Death Mountain.
BRACELET_BLOCK_SCREENS = frozenset({0x00, 0x01, 0x02, 0x03, 0x10, 0x12, 0x13})
# The screens each block flag's layout edits wall in: Link cannot walk out of them without the
# raft or the bracelet. The raft's two islands (with PRG0's $2F and $45), and West Death
# Mountain's pocket (with $11, and $23's west part, its cave's and Link's start spot's, which
# opens only north into the pocket; both entrances already need the bracelet).
RAFT_ENCLOSED_SCREENS = RAFT_BLOCK_SCREENS | {0x2F, 0x45}
BRACELET_ENCLOSED_SCREENS = BRACELET_BLOCK_SCREENS | {0x11, 0x23}

LOST_HILLS_SCREEN = 0x1B              # MountainMazeDirs' maze (CheckMazes)
DEAD_WOODS_SCREEN = 0x61              # ForestMazeDirs' maze
# Randomize Lost Hills: with its patch's edits, $0B-$0D are reached only through the maze (its
# fixed last step is up, to $0B); the ladder does not help.
LOST_HILLS_GATED = frozenset({0x0B, 0x0C, 0x0D})
# Randomize Dead Woods: the fixed last step is south (owner decision), to $71; with its patch's
# edit $70-$71 are reached only through the maze, and so is $72's cave: a wall splits $72, and the
# part with its entrance opens only west, to $71 (Link's start spot is in the open part).
DEAD_WOODS_GATED = frozenset({0x70, 0x71, 0x72})
# ... and the forest no longer leads west: the west half of the map, reached in PRG0 only through
# the forest's west exit or with the ladder over a one-square river, then needs the ladder, unless
# Add Lost Woods Shortcut (B88, FP-WOODS-01: one-way in from $51 to $50, out again by the maze's free
# east exit) or Add Bridges to the River (B87, FP-BRIDGE-01: $17 and $27, both ways) is on; then it
# needs nothing, and only $70-$72 are reached solely through the maze. Randomize Dead Woods turns the
# shortcut on (owner rule, beta 7; zora_flags.shortcut_forced_on), so seeds never ask for the ladder.
# The west half is FP-BRIDGE-01's 34 rooms.
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
    # Add Lost Woods Shortcut (B88) or Add Bridges to the River (B87) on: the west half is walked into
    # without the maze or the ladder
    river_west_open: bool = False

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
            if not self.river_west_open:
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

    def start_barred(self) -> frozenset[int]:
        """Screens the start-screen draw leaves out: the ones a block flag walls in, where Link
        would start shut in until he holds the raft or the bracelet, and the screens past each
        randomized maze, reached otherwise only by solving it (owner decision, 2026-10-13: only
        those; Dead Woods' west half, open by the shortcut or the bridges, stays a start)."""
        barred: frozenset[int] = frozenset()
        if self.raft_blocks:
            barred |= RAFT_ENCLOSED_SCREENS
        if self.bracelet_blocks:
            barred |= BRACELET_ENCLOSED_SCREENS
        if self.lost_hills:
            barred |= LOST_HILLS_GATED
        if self.dead_woods:
            barred |= DEAD_WOODS_GATED
        return barred

    def barred_for(self, code: Destination) -> frozenset[int]:
        """Screens a cave may not move to: a hint shop never behind its own maze."""
        if self.lost_hills and code == LOST_HILLS_HINT_SHOP:
            return LOST_HILLS_GATED
        if self.dead_woods and code == DEAD_WOODS_HINT_SHOP:
            return DEAD_WOODS_GATED
        return frozenset()


NO_GATES = OverworldGates()
