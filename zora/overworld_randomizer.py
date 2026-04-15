import logging

from zora.data_model import Destination, EntranceType, GameWorld, Overworld, OverworldDirection
from zora.game_config import GameConfig
from zora.rng import Rng

log = logging.getLogger(__name__)


# 44 special overworld screens (the initial candidate pool for EASY_SHUFFLE exclusion).
_ALL_SCREENS: list[int] = [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
    0x30, 0x31, 0x32, 0x33,
    0x40, 0x41,
    0x0A, 0x0B,
    0x1A, 0x19, 0x1B, 0x0F,
    0x1F, 0x1E,
    0x0D, 0x0C,
    0x3C, 0x37, 0x34, 0x44,
]

# Screens always excluded regardless of mode.
_BASE_EXCLUDE: list[int] = [0x0E, 0x62, 0x23, 0x2F, 0x45]

# Per-screen column widths (128 entries, index = screen number).
# Used to calculate start_position_y = screen_widths[screen] * 16 + 13.
_SCREEN_WIDTHS: list[int] = [
    #   0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F
        8, 8, 8, 8, 8, 8, 8, 8, 8, 7,10,10, 8, 8, 8, 8,  # Row 0
        7, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,  # Row 1
        8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,10, 8, 8, 8,  # Row 2
        8, 8, 8, 8, 8, 8, 8, 8, 8,10, 8, 8,10, 8, 8, 8,  # Row 3
        8, 8,10,10, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,  # Row 4
        8, 8, 5, 8, 8, 8, 8, 8, 8, 8, 8, 8, 5, 8, 8, 8,  # Row 5
        8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 5, 7, 8,  # Row 6
        8, 8, 5, 8, 8, 7, 7, 8, 8, 7, 8, 8, 8, 8, 8, 8,  # Row 7
]

# Vanilla start screen (0x77 = screen 119, row 7 col 7).
_DEFAULT_START_SCREEN: int = 0x77

# Explicit remapping table for WOOD_SWORD_SCREEN: screens that cannot simply
# have 0x10 added (because they sit on the last row or have a known relocation).
_REMAP_DOWN_ONE_ROW: dict[int, int] = {
    0x2F: 0x3F,
    0x0E: 0x1E,
    0x45: 0x55,
}


def remap_game_start(world: GameWorld, config: GameConfig, rng: Rng) -> None:
    if not (config.easy_start_shuffle or config.full_start_shuffle or config.wood_sword_cave_start):
        return
    """
    Randomizes which overworld screen the player starts on, mutating world in place.

    For easy_start_shuffle and full_start_shuffle:
      - Builds a candidate exclusion list from _BASE_EXCLUDE plus any screen
        whose entrance_type is not NONE (i.e. has a dungeon/cave entrance).
      - easy_start_shuffle additionally excludes all 44 screens in _ALL_SCREENS.
      - Picks a random screen not in the exclusion list.

    For wood_sword_cave_start:
      - Finds the screen currently holding Destination.WOOD_SWORD_CAVE and
        remaps it to the screen one row below (screen_num + 0x10).

    In all cases:
      - Sets overworld.start_screen to the chosen screen number.
      - Sets overworld.start_position_y = _SCREEN_WIDTHS[screen] * 16 + 13.
      - Swaps table_2_raw (enemy code byte) between the chosen screen and
        the default start screen (0x77).
      - If the chosen screen has the mixed-enemy flag set in table_3_raw
        (bit 0x80), clears it on the chosen screen and sets it on 0x77.
    """
    overworld: Overworld = world.overworld
    screens = overworld.screens  # list[Screen], index = screen_num

    if config.wood_sword_cave_start:
        # Find the screen currently holding the wood sword cave entrance,
        # then step it down by one row (+ 0x10) so Link starts below it.
        anchor = next(
            s.screen_num for s in screens
            if s.destination == Destination.WOOD_SWORD_CAVE
        )
        start_screen = _REMAP_DOWN_ONE_ROW.get(anchor, anchor + 0x10)
    else:
        # Build exclusion set: always exclude base screens ...
        exclude = set(_BASE_EXCLUDE)

        # ... plus all screens that have any entrance (destination != NONE).
        for s in screens:
            if s.entrance_type != EntranceType.NONE:
                exclude.add(s.screen_num)

        # easy_start_shuffle additionally excludes the 44 special screens.
        if config.easy_start_shuffle:
            exclude.update(_ALL_SCREENS)

        # Pick a random screen in [0x00, 0x7F] not in the exclusion set.
        candidates = [n for n in range(0x80) if n not in exclude]
        start_screen = rng.choice(candidates)

    # Write the new start screen.
    overworld.start_screen = start_screen

    # Calculate start Y position from the per-screen column width table.
    overworld.start_position_y = _SCREEN_WIDTHS[start_screen] * 16 + 13

    # Swap table_2_raw (enemy spec and quantity) between the chosen screen and the
    # default start screen (0x77). In the ROM this is the cave data row 2 swap.
    chosen = screens[start_screen]
    default = screens[_DEFAULT_START_SCREEN]
    chosen.enemy_spec, default.enemy_spec = default.enemy_spec, chosen.enemy_spec
    chosen.enemy_quantity, default.enemy_quantity = default.enemy_quantity, chosen.enemy_quantity

    # Transfer the mixed-enemy flag (bit 0x80 of table_3_raw) from the chosen
    # screen to the default start screen, if set. In the ROM this is the cave
    # data row 3 high-bit transfer.
    #
    # In the python translation this is not needed and intentionally commented out because
    # since the high bit of the enemey spec is shuffled allong with the enemy_spec
    # if chosen.table_3_raw & 0x80:
    #    chosen.table_3_raw &= 0x7F
    #    default.table_3_raw |= 0x80


# Lost Hills direction options: Up, Down, Right. The sequence always ends Up.
_LOST_HILLS_OPTIONS: list[OverworldDirection] = [
    OverworldDirection.UP_NORTH,
    OverworldDirection.DOWN_SOUTH,
    OverworldDirection.RIGHT_EAST,
]

# Dead Woods direction options: North, West, South. The sequence always ends South.
_DEAD_WOODS_OPTIONS: list[OverworldDirection] = [
    OverworldDirection.UP_NORTH,
    OverworldDirection.LEFT_WEST,
    OverworldDirection.DOWN_SOUTH,
]


def randomize_maze_directions(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Randomize Lost Hills and/or Dead Woods direction sequences in place.

    Mutates game_world.overworld.lost_hills_directions and
    game_world.overworld.dead_woods_directions. Must be called before
    randomize_hints() so the hint text can be derived from the new sequences.

    Lost Hills: 3 random directions from {Up, Down, Right} + Up at end.
    Dead Woods: 3 random directions from {North, West, South} + South at end.
    """
    if not (config.randomize_lost_hills or config.randomize_dead_woods):
        return

    if config.randomize_lost_hills:
        game_world.overworld.lost_hills_directions = [
            rng.choice(_LOST_HILLS_OPTIONS),
            rng.choice(_LOST_HILLS_OPTIONS),
            rng.choice(_LOST_HILLS_OPTIONS),
            OverworldDirection.UP_NORTH,
        ]

    if config.randomize_dead_woods:
        game_world.overworld.dead_woods_directions = [
            rng.choice(_DEAD_WOODS_OPTIONS),
            rng.choice(_DEAD_WOODS_OPTIONS),
            rng.choice(_DEAD_WOODS_OPTIONS),
            OverworldDirection.DOWN_SOUTH,
        ]


# Overworld screens where Link's Y coordinate after a recorder warp should be
# placed lower (0xAD instead of the default 0x8D).
_WARP_LOW_Y_SCREENS: frozenset[int] = frozenset([
    0x3C, 0x0B, 0x42, 0x05, 0x09, 0x0A, 0x2C,
])

# Overworld screens where Link's Y coordinate after a recorder warp should be
# placed higher (0x5D).
_WARP_HIGH_Y_SCREENS: frozenset[int] = frozenset([
    0x6D,
])

# Level 1-8 destinations in order (index 0 = Level 1, index 7 = Level 8).
_LEVEL_DESTINATIONS: list[Destination] = [
    Destination.LEVEL_1,
    Destination.LEVEL_2,
    Destination.LEVEL_3,
    Destination.LEVEL_4,
    Destination.LEVEL_5,
    Destination.LEVEL_6,
    Destination.LEVEL_7,
    Destination.LEVEL_8,
]


def _recorder_warp_y(level_screen: int) -> int:
    """Return the Y coordinate for a recorder warp arriving at level_screen."""
    if level_screen in _WARP_HIGH_Y_SCREENS:
        return 0x5D
    if level_screen in _WARP_LOW_Y_SCREENS:
        return 0xAD
    return 0x8D


def recalculate_recorder_warp_screens(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Recalculate recorder warp destinations based on shuffled dungeon locations.

    The recorder warps Link to the screen one to the left of each level 1-8
    entrance. The whirlwind then scrolls him right onto the dungeon screen.

    Special cases:
      - If the dungeon is at screen 0, the warp destination stays at screen 0.
      - If the dungeon is at screen 0x0E, the warp destination is 0x1D (wraps
        to the row below rather than the prior screen which is off-map).

    Mutates overworld.recorder_warp_destinations and
    overworld.recorder_warp_y_coordinates in place.
    """
    if not config.update_recorder_warp_screens:
        return

    overworld = game_world.overworld
    screen_by_dest: dict[Destination, int] = {
        s.destination: s.screen_num
        for s in overworld.screens
        if isinstance(s.destination, Destination)
    }

    warp_destinations: list[int] = []
    warp_y_coordinates: list[int] = []

    for level_num, dest in enumerate(_LEVEL_DESTINATIONS, start=1):
        level_screen = screen_by_dest.get(dest)
        if level_screen is None:
            raise ValueError(f"Could not find overworld screen for Level {level_num}")

        if level_screen == 0:
            warp_screen = 0
        elif level_screen == 0x0E:
            warp_screen = 0x1D
        else:
            warp_screen = level_screen - 1

        log.debug(
            "Level %d at screen %s, recorder warp to %s",
            level_num, hex(level_screen), hex(warp_screen),
        )
        warp_destinations.append(warp_screen)
        warp_y_coordinates.append(_recorder_warp_y(level_screen))

    overworld.recorder_warp_destinations = warp_destinations
    overworld.recorder_warp_y_coordinates = warp_y_coordinates
