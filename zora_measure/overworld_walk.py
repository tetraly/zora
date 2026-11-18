"""The finished-ROM overworld walk: every shown cave entrance is reached on foot from the start
screen, the mazes solved and the ladder held (zora/rom/vanilla_overworld/walkability.py, on the
ROM's own layouts, so any layout a screen shows is walked, the fountain's $7B and Lost Hills' $7C-$7F included), except
the screens only the raft or the power bracelet reaches: PRG0's two raft islands, and the screens
Extra Raft Blocks and Extra Power Bracelet Blocks wall in. Those gates are the acceptance check's
(zora/generate/steps/overworld_gates.py). 2.0.0's fairy fountain on $0B, which cut $0C and $0D
off under Randomize Lost Hills, is the bug this walk exists to catch.
"""
from zora.generate.steps.overworld_gates import (
    BRACELET_ENCLOSED_SCREENS,
    RAFT_ENCLOSED_SCREENS,
    OverworldGates,
)
from zora.model.enums import Destination, QuestVisibility
from zora.model.game_world import GameWorld
from zora.rom.mirror_overworld import mirror_screen
from zora.rom.vanilla_overworld.walkability import screen_graph

# PRG0's raft islands: the raft's dock reaches them, no walk does
RAFT_ISLANDS = frozenset({0x2F, 0x45})
SHOWN = (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST)
SQUARE_WIDTH = 2                      # a square is two tile columns; Link's left foot is on one of them


def item_walled_screens(gates: OverworldGates) -> frozenset[int]:
    """The screens reached only with the raft or the bracelet (unmirrored numbering)."""
    walled = RAFT_ISLANDS
    if gates.raft_blocks:
        walled |= RAFT_ENCLOSED_SCREENS
    if gates.bracelet_blocks:
        walled |= BRACELET_ENCLOSED_SCREENS
    return walled


def unreached_caves(rom: bytes, world: GameWorld, gates: OverworldGates) -> dict[int, Destination]:
    """The shown caves no walk reaches, by screen, for a plain (unencoded) finished ROM and the world
    parsed from it. On a screen a wall splits, the cave counts as reached when a region at its
    entrance square is."""
    walled = item_walled_screens(gates)
    if world.overworld_mirrored:
        walled = frozenset(mirror_screen(screen) for screen in walled)
    graph = screen_graph(rom, ladder=True)
    reached = graph.reach_regions(world.overworld.start_screen)
    unreached: dict[int, Destination] = {}
    for screen in world.overworld.screens:
        number = screen.screen_num
        if screen.destination == Destination.NONE or screen.quest_visibility not in SHOWN or number in walled:
            continue
        regions = graph.screens[number]
        entrance = range(SQUARE_WIDTH * screen.exit_x_position, SQUARE_WIDTH * screen.exit_x_position + SQUARE_WIDTH)
        candidates = regions.regions_in_columns(entrance) or set(range(regions.count))
        if not any((number, region) in reached for region in candidates):
            unreached[number] = screen.destination
    return unreached
