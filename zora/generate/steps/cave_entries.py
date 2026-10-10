"""The cave shuffle's enrolled screens and entries (OW-CAVE-02), shared by the
cave shuffle, the Armos shuffle and the recorder."""

from dataclasses import dataclass

from ...model.enums import Destination
from ...model.overworld import Overworld

# OW-APP-A1: the 72 enrolled screens, in list order (after OW-CAVE-02 step
# 2's exchange put the wooden-sword screen 119 last and 123 in its place).
ENROLLED_SCREENS = (
    1, 3, 4, 7, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 22, 26, 28, 29, 30,
    31, 34, 35, 37, 38, 40, 45, 47, 51, 52, 55, 60, 61, 66, 68, 69, 70, 72,
    73, 74, 75, 77, 78, 81, 86, 91, 94, 99, 100, 102, 104, 106, 111, 112,
    116, 117, 118, 123, 120, 121, 124, 125, 5, 33, 39, 44, 71, 98, 103, 107,
    109, 113, 119
)
# OW-APP-A2: screens with a nonzero PRG0 code that never move.
FIXED_SCREENS = frozenset({0, 2, 6, 9, 17, 21, 24, 25, 27, 32, 41, 43, 48, 58, 83, 88,
                           96, 108, 110, 114})
FIXED_DUNGEON_DOORS = {5: 27, 6: 48, 7: 25, 8: 108, 9: 0}       # OW-ENTR-02
# OW-APP-A3: the screens the wooden-sword code may receive.
WOOD_SWORD_SCREENS = frozenset({4, 10, 11, 12, 14, 15, 26, 28, 31, 32, 33, 34, 36, 37, 52,
                                55, 60, 61, 68, 74, 78, 94, 100, 102, 111, 112, 116, 117, 119})
# OW-APP-A4: the reachability sets.
RAFT_SCREENS = frozenset({47, 69})
RECORDER_SCREENS = frozenset({66})
LADDER_SCREENS = frozenset({24, 25})
BRACELET_SCREENS = frozenset({9, 17, 27, 29, 35, 73, 121})
BURNABLE_SCREENS = frozenset({40, 70, 71, 72, 75, 77, 81, 83, 86, 91, 98, 99, 104, 106, 107,
                              108, 109, 120})
# OW-APP-A6: the shortcut position index V of every screen.
SHORTCUT_POSITION_INDEX = (
    3, 2, 2, 1, 2, 2, 3, 2, 3, 2, 0, 0, 2, 2, 3, 3,
    3, 2, 2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 2, 0, 1, 2,
    2, 2, 0, 1, 2, 2, 3, 2, 3, 2, 2, 2, 1, 3, 2, 0,
    2, 2, 2, 2, 3, 2, 2, 0, 2, 0, 2, 2, 0, 1, 0, 2,
    2, 2, 0, 0, 1, 1, 3, 2, 2, 0, 2, 3, 2, 3, 2, 3,
    3, 2, 0, 3, 3, 2, 2, 2, 3, 0, 2, 3, 0, 3, 2, 3,
    3, 2, 3, 3, 3, 2, 3, 2, 3, 3, 2, 3, 2, 1, 2, 2,
    3, 3, 3, 3, 3, 2, 3, 3, 3, 2, 3, 0, 2, 2, 0, 2
)
DUNGEONS = range(1, 10)


@dataclass
class Entry:
    """One enrolled entry: a screen, the code it carries, its palette bits."""
    screen: int
    code: Destination
    inner_palette: int


@dataclass
class CaveShuffle:
    """What the walk decided, for the checks that follow it."""
    entries: list[Entry]
    armos_screen: int                # A: the formation's first screen

    def movable_screens(self, code: Destination) -> list[int]:
        """OW-SHOP-06's movable entrances of a code: enrolled entries
        carrying it, at their final screens."""
        return [entry.screen for entry in self.entries if entry.code == code]

    def entry_door(self, dungeon: int) -> int:
        """OW-ENTR-02: the entry that carries the dungeon's code."""
        doors = self.movable_screens(Destination(dungeon))
        assert len(doors) == 1, f"dungeon {dungeon}: {len(doors)} entry doors"
        return doors[0]


@dataclass
class OverworldResult:
    """The overworld passes' result: the staged model, written at ship, and the cave shuffle."""
    overworld: Overworld
    caves: CaveShuffle
