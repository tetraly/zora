"""The owner's 2.0 overworld gates (zora/generate/steps/overworld_gates.py) derived again from the
overworld map (zora/rom/vanilla_overworld/walkability.py), on PRG0 with the flags' layout edits."""
from functools import cache

import pytest

from zora.generate.steps import overworld_gates as gates
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.vanilla_overworld.walkability import ScreenGraph, screen_graph, screen_tiles

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

START = 0x77
# OW-START-01's 51 start screens.
START_SCREENS = (24, 28, 29, 39, 40, 41, 43, 44, 45, 58, 59, 61, 66, 70, 71, 72, 73, 74, 75, 77, 78, 81, 83,
                 86, 88, 91, 94, 96, 99, 100, 102, 103, 104, 106, 107, 108, 109, 110, 111, 112, 113, 114,
                 116, 117, 118, 119, 120, 121, 123, 124, 125)
# The layout edits of the flags' patches (docs/design/zora-flags-2.0.md; asm/flags2/*/patch.toml).
LAYOUT_EDITS = {
    "raft": [(0x154F8, "0C"), (0x155F7, "0C 0C"), (0x15613, "EB"), (0x15615, "AF"), (0x15715, "B6"),
             (0x15765, "91 78"), (0x1582F, "02 08 0B 0B 0B 0B 0B 0B 0B 0B 01"), (0x1592F, "17 17")],
    "bracelet": [(0x1554E, "38"), (0x15554, "06 E7 00 00 00"), (0x15649, "00 A9"), (0x1564E, "B6"),
                 (0x1574E, "02")],
    "lost_hills": [(0x154D7, "01 01 01 01 01 01 01"), (0x154F1, "09"), (0x154F5, "06"), (0x155DD, "02"),
                   (0x155F5, "51")],
    "dead_woods": [(0x15B08, "29")],
}
LOST_HILLS_REPEATS = frozenset({(gates.LOST_HILLS_SCREEN, side) for side in "NSE"})     # free exit: west
DEAD_WOODS_REPEATS = frozenset({(gates.DEAD_WOODS_SCREEN, side) for side in "NSW"})     # free exit: east


@cache
def graph(edits: tuple[str, ...], ladder: bool = False) -> ScreenGraph:
    rom = bytearray(verify_base_rom().read_bytes())
    for name in edits:
        for offset, new in LAYOUT_EDITS[name]:
            data = bytes.fromhex(new)
            rom[offset:offset + len(data)] = data
    return screen_graph(bytes(rom), ladder)


def beyond(world: ScreenGraph, closed: frozenset[tuple[int, str]], start: int = START) -> set[int]:
    return world.reach(start) - world.reach(start, closed)


def test_the_map_reaches_what_the_game_does() -> None:
    """From the start screen everything but the raft's two islands; $0F only through $1F's false
    wall; the PRG0 mazes guard $0B (Lost Hills) and the west half (the Dead Woods, without the
    ladder)."""
    plain = graph(())
    assert set(range(128)) - plain.reach(START) == {0x2F, 0x45}
    assert beyond(plain, LOST_HILLS_REPEATS) == {0x0B}
    assert beyond(plain, DEAD_WOODS_REPEATS) == gates.DEAD_WOODS_WEST
    assert beyond(graph((), ladder=True), DEAD_WOODS_REPEATS) == set()


@pytest.mark.parametrize("blocks", [(), ("raft", "bracelet")])
def test_the_maze_sets_come_from_the_map(blocks: tuple[str, ...]) -> None:
    edits = ("lost_hills", "dead_woods", *blocks)
    walk, ladder = graph(edits), graph(edits, ladder=True)
    assert beyond(walk, LOST_HILLS_REPEATS) == beyond(ladder, LOST_HILLS_REPEATS) == gates.LOST_HILLS_GATED
    # Dead Woods randomized: the forest leaves only south; the pocket needs its hint, and the west
    # half (the forest's old west exit closed too) needs the ladder.
    assert beyond(ladder, DEAD_WOODS_REPEATS) == gates.DEAD_WOODS_GATED
    no_west = DEAD_WOODS_REPEATS | {(gates.DEAD_WOODS_SCREEN, "W")}
    unreached_blocks = set(range(128)) - walk.reach(START)          # entered by raft or bracelet
    assert beyond(walk, no_west) == (gates.DEAD_WOODS_GATED | gates.DEAD_WOODS_WEST) - unreached_blocks
    if blocks:
        assert unreached_blocks == {0x2F, 0x45, 0x11} | gates.RAFT_BLOCK_SCREENS | gates.BRACELET_BLOCK_SCREENS


def test_no_start_screen_gates_more() -> None:
    edits = ("lost_hills", "dead_woods", "raft", "bracelet")
    walk, ladder = graph(edits), graph(edits, ladder=True)
    for start in START_SCREENS:
        assert beyond(walk, LOST_HILLS_REPEATS, start) <= gates.LOST_HILLS_GATED, start
        assert beyond(ladder, DEAD_WOODS_REPEATS, start) <= gates.DEAD_WOODS_GATED, start


@pytest.mark.parametrize(("edits", "screen"), [
    ((), gates.LOST_HILLS_SCREEN), (("lost_hills",), gates.LOST_HILLS_SCREEN),
    ((), gates.DEAD_WOODS_SCREEN), (("dead_woods",), gates.DEAD_WOODS_SCREEN)])
def test_every_maze_step_can_repeat_the_screen(edits: tuple[str, ...], screen: int) -> None:
    """A repeated step leaves by one edge and comes back by the opposite one at the same position:
    the maze screens are open across, both ways, so every sequence can be walked."""
    world = graph(edits)
    regions = world.screens[screen]
    for side, opposite in (("N", "S"), ("W", "E")):
        across = {position for position, region in regions.edges[side].items()
                  if region is not None and regions.edges[opposite][position] is not None}
        assert across, (hex(screen), side)
    assert screen_tiles(verify_base_rom().read_bytes(), screen)
