"""The owner's 2.0 overworld gates (zora/generate/steps/overworld_gates.py) derived again from the
overworld map (zora/rom/vanilla_overworld/walkability.py), on PRG0 with the flags' layout edits."""
from functools import cache

import pytest

from zora.generate.acceptance_check import logic_rules
from zora.generate.steps import overworld_gates as gates
from zora.model.enums import Item
from zora.rom import overworld_crossings as crossings
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.extra_layouts import OWN_LAYOUTS, extra_layout_writes
from zora.rom.flags2_patch_data import PATCHES as FLAGS2_PATCHES
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.vanilla_overworld.tables import ATTRIBUTE_TABLE_SIZE, LEVEL_BLOCK_OW, ROOM_LAYOUTS_OW
from zora.rom.vanilla_overworld.walkability import LAYOUT_MASK, LAYOUT_TABLE, ScreenGraph, screen_graph, screen_tiles

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

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
    # and $0B on a layout of its own (own_layouts)
    "lost_hills": [(0x154D8, "01 01 01 01 01 01"), (0x154F1, "09"), (0x154F5, "06"), (0x155DD, "02"),
                   (0x155F5, "51")],
    "dead_woods": [(0x15B08, "29")],
    # Add Bridges to the River (B87, FP-BRIDGE-01) and Add Lost Woods Shortcut (B88, FP-WOODS-01)
    "bridges": [(crossings.ROOM_17_RIVER_ROWS, "4B"), (crossings.ROOM_27_RIVER_COLUMN, "12")],
    "shortcut": [(crossings.ROOM_51_WEST_EDGE, "16")],
}
# The second quest's fairy fountain on $0B and pond on $3C, layout 123 ($7B): 2nd Quest, Mixed Quest
# ($3C) and an unchosen 1Q5 or a closed pond under Expanded Dungeon Locations show them.
FOUNTAIN_LAYOUT = 0x7B
FOUNTAIN_SCREENS = (0x0B, 0x3C)
SCREEN_11 = 0x0B
LOOKS = {"fountain": FOUNTAIN_SCREENS}
LOST_HILLS_REPEATS = frozenset({(gates.LOST_HILLS_SCREEN, side) for side in "NSE"})     # free exit: west
DEAD_WOODS_REPEATS = frozenset({(gates.DEAD_WOODS_SCREEN, side) for side in "NSW"})     # free exit: east


def layout_byte(screen: int) -> int:
    return LEVEL_BLOCK_OW.file_offset + LAYOUT_TABLE * ATTRIBUTE_TABLE_SIZE + screen


@cache
def graph(edits: tuple[str, ...], ladder: bool = False, own_layout: bool = True) -> ScreenGraph:
    """PRG0 with the named flags' layout edits and the named looks (each look's screens on layout 123);
    with Lost Hills, $0B on its own copy of the layout it shows, as a finished ROM has it (own_layouts),
    unless `own_layout` is False."""
    rom = bytearray(verify_base_rom().read_bytes())
    for name in edits:
        for offset, new in LAYOUT_EDITS.get(name, ()):
            data = bytes.fromhex(new)
            rom[offset:offset + len(data)] = data
        for screen in LOOKS.get(name, ()):
            rom[layout_byte(screen)] = rom[layout_byte(screen)] & ~LAYOUT_MASK | FOUNTAIN_LAYOUT
    if "lost_hills" in edits and own_layout:
        own_layouts(rom)
    return screen_graph(bytes(rom), ladder)


def own_layouts(rom: bytearray) -> None:
    """Randomize Lost Hills' layouts $7C and $7D (zora/rom/extra_layouts.py, which writes them from the
    image's rows) and $0B on the one copying its layout (zora/generate/steps/lost_hills_layouts.py)."""
    for offset, data in extra_layout_writes(rom):
        rom[offset:offset + len(data)] = data
    at = layout_byte(SCREEN_11)
    rom[at] = rom[at] & ~LAYOUT_MASK | OWN_LAYOUTS[rom[at] & LAYOUT_MASK]


def beyond(world: ScreenGraph, closed: frozenset[tuple[int, str]], start: int = START) -> set[int]:
    return world.reach(start) - world.reach(start, closed)


@cache
def entrance_columns() -> dict[int, range]:
    """Each cave screen's entrance square, as Link's left-foot columns (LevelBlockAttrsA's exit
    X, which stays with the screen whatever cave the shuffle puts there)."""
    world = parse_rom(load_rom(verify_base_rom()))
    return {screen.screen_num: range(2 * screen.exit_x_position, 2 * screen.exit_x_position + 2)
            for screen in world.overworld.screens if screen.exit_x_position}


def cut_off(world: ScreenGraph, closed: frozenset[tuple[int, str]] = frozenset(), start: int = START) -> set[int]:
    """The screens whose cave entrance Link cannot walk to from the start: none of the screen's
    regions is reached, or, on a screen a wall splits, none of those at its entrance square."""
    reached = world.reach_regions(start, closed)
    cut = set()
    for screen, regions in world.screens.items():
        columns = entrance_columns().get(screen)
        candidates = regions.regions_in_columns(columns) if columns else set()
        if not any((screen, region) in reached for region in candidates or range(regions.count)):
            cut.add(screen)
    return cut


def test_the_map_reaches_what_the_game_does() -> None:
    """From the start screen everything but the raft's two islands; $0F only through $1F's false
    wall; the PRG0 mazes guard $0B (Lost Hills) and the west half (the Dead Woods, without the
    ladder)."""
    plain = graph(())
    assert set(range(128)) - plain.reach(START) == {0x2F, 0x45}
    assert beyond(plain, LOST_HILLS_REPEATS) == {0x0B}
    assert beyond(plain, DEAD_WOODS_REPEATS) == gates.DEAD_WOODS_WEST
    assert beyond(graph((), ladder=True), DEAD_WOODS_REPEATS) == set()


def gated(world: ScreenGraph, closed: frozenset[tuple[int, str]]) -> set[int]:
    """The screens whose cave entrance only the closed maze sides lead to."""
    return cut_off(world, closed) - cut_off(world)


@pytest.mark.parametrize("blocks", [(), ("raft", "bracelet")])
def test_the_maze_sets_come_from_the_map(blocks: tuple[str, ...]) -> None:
    """By each cave's entrance square: $72's cave is past the Dead Woods though most of $72 is
    not (a wall splits it; the entrance's side opens only to $71)."""
    edits = ("lost_hills", "dead_woods", *blocks)
    walk, ladder = graph(edits), graph(edits, ladder=True)
    assert gated(walk, LOST_HILLS_REPEATS) == gated(ladder, LOST_HILLS_REPEATS) == gates.LOST_HILLS_GATED
    # Dead Woods randomized: the forest leaves only south; the pocket needs its hint, and the west
    # half (the forest's old west exit closed too) needs the ladder.
    assert gated(ladder, DEAD_WOODS_REPEATS) == gates.DEAD_WOODS_GATED
    no_west = DEAD_WOODS_REPEATS | {(gates.DEAD_WOODS_SCREEN, "W")}
    unreached_blocks = cut_off(walk)                                # entered by raft or bracelet
    assert gated(walk, no_west) == (gates.DEAD_WOODS_GATED | gates.DEAD_WOODS_WEST) - unreached_blocks
    if blocks:
        assert unreached_blocks == gates.RAFT_ENCLOSED_SCREENS | gates.BRACELET_ENCLOSED_SCREENS


def test_the_lost_hills_edits_are_the_patch_s() -> None:
    """LAYOUT_EDITS' Lost Hills bytes are the layout bytes Randomize Lost Hills writes (asm/flags2/lost-hills;
    its other bytes are the routine and its hook)."""
    layouts = range(ROOM_LAYOUTS_OW.file_offset, ROOM_LAYOUTS_OW.file_offset + ROOM_LAYOUTS_OW.size)
    written = {offset: piece for offset, piece in FLAGS2_PATCHES["lost-hills"]
               if isinstance(piece, bytes) and offset in layouts}
    assert {offset: bytes.fromhex(new) for offset, new in LAYOUT_EDITS["lost_hills"]} == written


@pytest.mark.parametrize("look", [(), ("fountain",)])
@pytest.mark.parametrize("blocks", [(), ("raft", "bracelet")])
def test_the_maze_sets_hold_with_0b_s_own_layout(look: tuple[str, ...], blocks: tuple[str, ...]) -> None:
    """With $0B on its own layout ($7D, its doorway's copy, or with $0B and $3C on layout 123, the
    fountain and the pond, $7C) the maze sets are the same and no cave is cut off. On the layout it
    shares with $3C, which Lost Hills leaves as PRG0's, $0B shuts $0C and $0D off (2.0.0's bug with the
    fountain)."""
    edits = ("lost_hills", "dead_woods", *look, *blocks)
    walk, ladder = graph(edits), graph(edits, ladder=True)
    plain = graph(("lost_hills", "dead_woods", *blocks))
    assert gated(walk, LOST_HILLS_REPEATS) == gated(ladder, LOST_HILLS_REPEATS) == gates.LOST_HILLS_GATED
    assert gated(ladder, DEAD_WOODS_REPEATS) == gates.DEAD_WOODS_GATED
    assert cut_off(walk) == cut_off(plain)
    shared = graph(edits, own_layout=False)
    assert {0x0C, 0x0D} <= cut_off(shared) - cut_off(plain)


def test_the_fountain_screens_show_layout_123() -> None:
    """The screens the gate tests put on layout 123 are the ones generation does."""
    from zora.generate.steps.mixed_overworld_quest import SCREEN_11, SCREEN_11_LAYOUT, SCREEN_60, SCREEN_60_LAYOUT
    assert (SCREEN_11, SCREEN_60) == FOUNTAIN_SCREENS
    assert SCREEN_11_LAYOUT == SCREEN_60_LAYOUT == FOUNTAIN_LAYOUT


def test_the_cave_on_72_needs_the_dead_woods_hint() -> None:
    """The acceptance check's rules: with Randomize Dead Woods on, a cave on $72 needs the maze's
    hint like $70's and $71's."""
    rules = logic_rules(False, False, gates.OverworldGates(dead_woods=True))
    assert gates.DEAD_WOODS_HINT in rules.needs(0x72)
    assert gates.DEAD_WOODS_HINT not in logic_rules(False, False).needs(0x72)


@pytest.mark.parametrize(("blocks", "enclosed"), [(("raft",), gates.RAFT_ENCLOSED_SCREENS),
                                                  (("bracelet",), gates.BRACELET_ENCLOSED_SCREENS)])
def test_each_block_flag_walls_in_its_enclosed_screens(blocks: tuple[str, ...], enclosed: frozenset[int]) -> None:
    """The screens the start-screen draw leaves out (start_barred) are the ones each flag's edits
    cut off from $77, PRG0's raft islands with them ($23 by its west part, where its cave is)."""
    assert cut_off(graph(())) == {0x2F, 0x45}
    assert cut_off(graph(blocks)) == {0x2F, 0x45} | enclosed


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


# --- Add Bridges to the River (B87) and Add Lost Woods Shortcut (B88) ------------------------------

MAZE_SIDES = frozenset({(gates.DEAD_WOODS_SCREEN, side) for side in "NSWE"})
SHORTCUT_ROOM, PAST_THE_ROCK = 0x51, 0x50


@pytest.mark.parametrize("opening", [("shortcut",), ("bridges",), ("shortcut", "bridges")])
def test_the_west_half_is_walked_into_without_the_maze_or_the_ladder(opening: tuple[str, ...]) -> None:
    """FP-BRIDGE-01's and FP-WOODS-01's square-level walk: the 34 rooms from $77 with every side of
    the forest maze closed, and no ladder; without either edit they are not reached."""
    assert gates.DEAD_WOODS_WEST <= graph(opening).reach(START, MAZE_SIDES)
    assert not gates.DEAD_WOODS_WEST & graph(()).reach(START, MAZE_SIDES)


@pytest.mark.parametrize("blocks", [(), ("raft", "bracelet")])
@pytest.mark.parametrize("opening", [("shortcut",), ("bridges",), ("shortcut", "bridges")])
def test_only_the_pocket_needs_the_dead_woods_hint(opening: tuple[str, ...], blocks: tuple[str, ...]) -> None:
    """Randomize Dead Woods with the shortcut (which it forces on) or the bridges: the screens whose
    cave entrance only the maze leads to, walking without the ladder, are $70, $71 and $72's cave."""
    edits = ("lost_hills", "dead_woods", *opening, *blocks)
    no_west = DEAD_WOODS_REPEATS | {(gates.DEAD_WOODS_SCREEN, "W")}
    assert gated(graph(edits), no_west) == gates.DEAD_WOODS_GATED
    for start in START_SCREENS:
        assert beyond(graph(edits), DEAD_WOODS_REPEATS, start) <= gates.DEAD_WOODS_GATED, start


@pytest.mark.parametrize("opening", [("shortcut",), ("bridges",)])
def test_with_prg0s_maze_nothing_is_past_it(opening: tuple[str, ...]) -> None:
    assert beyond(graph(opening), DEAD_WOODS_REPEATS) == set()


def test_the_shortcut_is_one_way() -> None:
    """$51's west edge leads into $50 at rows 4 to 6 (Link's rows 8 to 13), though $50's east edge
    is rock; walking east from $50 never leads back."""
    world = graph(("shortcut",))
    into = {arrival for (screen, _region, side), arrivals in world.exits.items()
            if screen == SHORTCUT_ROOM and side == "W" for arrival in arrivals}
    assert {screen for screen, _ in into} == {PAST_THE_ROCK}
    assert world.screens[PAST_THE_ROCK].entries["E"].keys() >= set(range(8, 14))
    assert not leaves(world, PAST_THE_ROCK, "E")
    assert not leaves(graph(()), SHORTCUT_ROOM, "W")            # PRG0: $51 is closed to the west


def leaves(world: ScreenGraph, screen: int, side: str) -> bool:
    return any(world.exits.get((screen, region, side)) for region in range(world.screens[screen].count))


def test_the_bridges_are_two_way() -> None:
    """From the west half ($40) the start is reached again over the bridges, the maze closed."""
    world = graph(("bridges",))
    assert START in world.reach(0x40, MAZE_SIDES)
    assert START not in graph(("shortcut",)).reach(0x40, MAZE_SIDES)


def test_with_the_west_half_open_the_rules_ask_only_the_pocket_for_the_hint() -> None:
    open_rules = logic_rules(False, False, gates.OverworldGates(dead_woods=True, river_west_open=True))
    closed_rules = logic_rules(False, False, gates.OverworldGates(dead_woods=True))
    for screen in gates.DEAD_WOODS_WEST:
        assert Item.LADDER not in open_rules.needs(screen) and gates.DEAD_WOODS_HINT not in open_rules.needs(screen)
        assert Item.LADDER in closed_rules.needs(screen)
    for screen in gates.DEAD_WOODS_GATED:
        assert gates.DEAD_WOODS_HINT in open_rules.needs(screen)
