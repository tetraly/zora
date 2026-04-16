from dataclasses import dataclass, field

from zora.data_model import Destination, EntranceType, GameWorld, QuestVisibility
from zora.game_config import GameConfig
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CAVE_TYPE_WOOD_SWORD = Destination.WOOD_SWORD_CAVE.value   # 0x10
_CAVE_TYPE_ANY_ROAD   = Destination.ANY_ROAD.value          # 0x14
_CAVE_TYPE_ARMOS      = Destination.ARMOS_ITEM.value        # 0x24

# Default armos screen when shuffle_armos is False.
_DEFAULT_ARMOS_SCREEN = 36

_LADDER_LOCATIONS = frozenset([0x18, 0x19])


_ANY_ROAD_STAIRS_CODE = 5


# ---------------------------------------------------------------------------
# Location requirement helpers
# ---------------------------------------------------------------------------

def _need_raft(loc: int, raft_locations: list[int]) -> bool:
    return loc in raft_locations


def _need_recorder(loc: int, recorder_locations: list[int]) -> bool:
    return loc in recorder_locations


def _need_ladder(loc: int) -> bool:
    return loc in _LADDER_LOCATIONS


def _need_bracelet(loc: int, bracelet_locations: list[int]) -> bool:
    return loc in bracelet_locations


def _need_lost_hills_hint(loc: int, lost_hills_screens: frozenset[int]) -> bool:
    return loc in lost_hills_screens


def _need_dead_woods_hint(loc: int, dead_woods_screens: frozenset[int]) -> bool:
    return loc in dead_woods_screens


def _screens_with_destination(game_world: GameWorld, dest: Destination) -> frozenset[int]:
    """Return the set of overworld screen numbers that have the given destination."""
    return frozenset(
        s.screen_num for s in game_world.overworld.screens if s.destination == dest
    )


def _need_no_item_to_enter(
    loc: int,
    raft_locations: list[int],
    recorder_locations: list[int],
    bracelet_locations: list[int],
    lost_hills_screens: frozenset[int] = frozenset(),
    dead_woods_screens: frozenset[int] = frozenset(),
) -> bool:
    """Returns True if the screen can be reached without any special item or virtual item."""
    return not (
        _need_raft(loc, raft_locations)
        or _need_recorder(loc, recorder_locations)
        or _need_ladder(loc)
        or _need_bracelet(loc, bracelet_locations)
        or _need_lost_hills_hint(loc, lost_hills_screens)
        or _need_dead_woods_hint(loc, dead_woods_screens)
    )


# ---------------------------------------------------------------------------
# Overworld block existence check 
# ---------------------------------------------------------------------------

def _overworld_block_exists(
    cave_types: list[int],
    screen_locations: list[int],
    raft_locations: list[int],
    recorder_locations: list[int],
    bracelet_locations: list[int],
) -> bool:
    """
    Returns True if the shuffled cave assignment contains at least one
    screen that is inaccessible without a special item, for cave types < 10
    or == LETTER_CAVE (0x18). This is the "overworld block" check that
    gates certain game-completion paths.
    """
    for i, cave_type in enumerate(cave_types):
        if cave_type >= 10 and cave_type != Destination.LETTER_CAVE.value:
            continue
        loc = screen_locations[i]
        if (not _need_recorder(loc, recorder_locations)
                and not _need_raft(loc, raft_locations)
                and not _need_ladder(loc)):
            # Freely accessible without recorder/raft/ladder — check bracelet.
            # Screens 0x20 and 0x21 are exempt from the bracelet check.
            if _need_bracelet(loc, bracelet_locations) and loc not in (0x20, 0x21):
                return True
        else:
            # Requires recorder, raft, or ladder — counts as a block.
            return True
    return False


# ---------------------------------------------------------------------------
# Armos shuffle
# ---------------------------------------------------------------------------

@dataclass
class _ArmosResult:
    screen: int
    screen_ids: list[int]
    positions: list[int]


def _remap_armos(rng: Rng) -> _ArmosResult:
    """
    Shuffles the armos item screen location.

    Returns the chosen armos screen number plus the full shuffled lookup tables
    (screen_ids and sprite X-positions) to be written back into the data model.
    """
    screen_ids = [36, 11, 28, 34, 52, 61, 78]
    positions  = [224, 176, 176, 48, 64, 144, 160]

    position_groups = [
        [32, 80, 128, 176, 224],
        [48, 80, 144, 176],
        [112, 144, 176, 208],
        [48, 64, 80, 160, 176, 192],
        [32, 64, 96],
        [96, 144],
        [80, 160],
    ]

    # For each position pick a random value from its group.
    for i, group in enumerate(position_groups):
        positions[i] = rng.choice(group)

    # Swap a random entry from {0, 2, 4, 5, 6} with index 0.
    swap_indices = [0, 2, 4, 5, 6]
    swap_idx = rng.choice(swap_indices)
    screen_ids[0], screen_ids[swap_idx] = screen_ids[swap_idx], screen_ids[0]
    positions[0],  positions[swap_idx]  = positions[swap_idx],  positions[0]

    return _ArmosResult(screen=screen_ids[0], screen_ids=screen_ids, positions=positions)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CaveShuffleResult:
    """
    Output of shuffle_caves. Contains post-shuffle state needed by
    downstream randomizer functions.
    """
    # Mapping from dungeon number (1-9) to overworld screen index.
    # Index 0 is unused. Updated during the write-back phase.
    dungeon_entrance_screens: list[int] = field(default_factory=lambda: [0] * 16)

    # Overworld screen number of the wood sword cave after shuffling.
    wood_sword_screen: int | None = None


# ---------------------------------------------------------------------------
# Main shuffle function
# ---------------------------------------------------------------------------

def shuffle_caves(
    world: GameWorld,
    rng: Rng,
    shuffle: bool,
    include_bracelet_caves: bool,
    include_wood_sword_cave: bool,
    shuffle_armos: bool,
    add_armos_item: bool,
    mirror_ow: bool,
    just_dungeons: bool,
    shuffle_dungeons: bool,
    overworld_block_needed: bool,
    raft_locations: list[int] | None = None,
    recorder_locations: list[int] | None = None,
    bracelet_locations: list[int] | None = None,
    lost_hills_screens: frozenset[int] = frozenset(),
    dead_woods_screens: frozenset[int] = frozenset(),
) -> CaveShuffleResult | None:
    """
    Shuffles cave entrance assignments on the overworld, mutating world in place.

    Parameters
    ----------
    shuffle               : shuffle non-dungeon cave types
    include_bracelet_caves: include power-bracelet-gated screens in the pool
    include_wood_sword_cave: include screen 0x77 (wood sword) in the pool
    shuffle_armos         : randomize the armos item screen
    add_armos_item        : whether armos item is enabled (affects accessibility)
    mirror_ow             : if True, XOR each dungeon entrance_room with 0x0F
    just_dungeons         : shuffle dungeon entrances only (no non-dungeon caves)
    shuffle_dungeons      : include dungeon entrances in the shuffle pool
    overworld_block_needed: if True, return None when no overworld block exists
    raft_locations        : screens requiring the raft (default: [0x2F, 0x45])
    recorder_locations    : screens requiring the recorder (default: vanilla list)
    bracelet_locations    : screens requiring the power bracelet (default: [])
    lost_hills_screens    : screens in the lost hills maze area (excluded from wood sword placement)
    dead_woods_screens    : screens in the dead woods maze area (excluded from wood sword placement)
    """
    if raft_locations is None:
        raft_locations = [0x2F, 0x45]
    if recorder_locations is None:
        recorder_locations = [66, 6, 41, 43, 48, 58, 60, 88, 96, 110, 114]
    if bracelet_locations is None:
        bracelet_locations = []

    overworld = world.overworld
    screens_by_num = {s.screen_num: s for s in overworld.screens}

    # ------------------------------------------------------------------
    # Step 1: Handle armos shuffle
    # ------------------------------------------------------------------
    armos_screen = _DEFAULT_ARMOS_SCREEN
    if shuffle_armos:
        armos_result = _remap_armos(rng)
        armos_screen = armos_result.screen
        world.overworld.armos_screen_ids = armos_result.screen_ids
        world.overworld.armos_positions  = armos_result.positions

    # When armos moves to a different screen, swap the destination field so that
    # the ARMOS_ITEM destination sits on the new screen and screen 36 gets the
    # destination that was previously at the new screen.  This must happen before
    # Step 3 builds the cave pool, otherwise the pool still has ARMOS_ITEM at
    # screen 36 and the new screen's original destination at the new screen.
    if shuffle_armos and armos_screen != _DEFAULT_ARMOS_SCREEN:
        old_screen = screens_by_num.get(_DEFAULT_ARMOS_SCREEN)
        new_screen = screens_by_num.get(armos_screen)
        if old_screen is not None and new_screen is not None:
            old_screen.destination, new_screen.destination = (
                new_screen.destination,
                old_screen.destination,
            )

    if 36 in screens_by_num:
        screens_by_num[36].exit_x_position = 4
        screens_by_num[36].exit_y_position = 3

    # Mark the armos screen in the Q2 cave table (set high 2 bits of table_3_raw).
    if armos_screen in screens_by_num:
        screens_by_num[armos_screen].quest_visibility = QuestVisibility.BOTH_QUESTS

    # ------------------------------------------------------------------
    # Step 2: Build dungeon_original_screens from Level.entrance_room
    # ------------------------------------------------------------------
    dungeon_original_screens: list[int] = [0]  # index 0 unused
    for level in world.levels:                  # levels[0] = dungeon 1, etc.
        dungeon_original_screens.append(level.entrance_room)


    # ------------------------------------------------------------------
    # Step 3: Build the three parallel working lists from overworld screens
    #
    # Each Screen with a non-NONE destination contributes one entry:
    #   cave_type = screen.destination.value
    #   tile_data = screen.table_1_low2
    # ------------------------------------------------------------------
    cave_screens:   list[int] = []
    cave_types:     list[int] = []
    #cave_tile_data: list[int] = []

    for s in overworld.screens:
        if s.destination == Destination.NONE:
            continue
        # Second-quest-only screens don't exist in first-quest play; excluding
        # them prevents dungeon destinations from appearing more than once in the
        # pool (e.g. L5 has both a Q1 and a Q2 entrance in vanilla).
        if s.quest_visibility == QuestVisibility.SECOND_QUEST:
            continue
        if not include_bracelet_caves and s.entrance_type == EntranceType.POWER_BRACELET:
            continue
        if not include_wood_sword_cave and s.screen_num == 0x77:
            continue
        cave_screens.append(s.screen_num)
        cave_types.append(s.destination.value)

    # ------------------------------------------------------------------
    # Step 4: Move wood sword cave to end of list so it is handled
    # specially during the shuffle loop.
    # ------------------------------------------------------------------
    wood_sword_idx = next(
        (i for i, ct in enumerate(cave_types) if ct == _CAVE_TYPE_WOOD_SWORD),
        -1
    )
    if 0 <= wood_sword_idx < len(cave_types) - 1:
        last = len(cave_types) - 1
        cave_screens[wood_sword_idx],   cave_screens[last]   = cave_screens[last],   cave_screens[wood_sword_idx]
        cave_types[wood_sword_idx],     cave_types[last]     = cave_types[last],     cave_types[wood_sword_idx]

    # ------------------------------------------------------------------
    # Step 5: Main shuffle loop
    #
    # Only cave_types is swapped; cave_screens and cave_tile_data stay
    # in their original positions throughout.
    # ------------------------------------------------------------------
    if shuffle or just_dungeons or shuffle_dungeons:
        i = 0
        while i < len(cave_types):
            advance = True

            # Skip non-dungeon caves when not shuffling them.
            if not shuffle and cave_types[i] > 9:
                i += 1
                continue

            # Skip dungeon entrances when neither just_dungeons nor shuffle_dungeons.
            if not just_dungeons and not shuffle_dungeons and cave_types[i] <= 9:
                i += 1
                continue

            # Consume one RNG value unconditionally (mirrors line 86856).
            rng.random()

            # Build valid target pool and pick one.
            # A target j is valid if:
            #   cave_types[j] > 9  implies shuffle is True
            #   cave_types[j] <= 9 implies just_dungeons or shuffle_dungeons is True
            valid_targets = [
                j for j in range(len(cave_types))
                if (cave_types[j] <= 9 or shuffle)
                and (cave_types[j] > 9 or just_dungeons or shuffle_dungeons)
            ]
            j = rng.choice(valid_targets)
            offset = j - i
            do_swap = False

            if cave_types[i] == _CAVE_TYPE_WOOD_SWORD:
                # Wood sword: must land on a screen reachable without any item or virtual item.
                accessible = [
                    k for k in range(len(cave_screens))
                    if _need_no_item_to_enter(
                        cave_screens[k],
                        raft_locations, recorder_locations, bracelet_locations,
                        lost_hills_screens, dead_woods_screens,
                    )
                ]
                k = rng.choice(accessible)
                offset = k - i
                do_swap = True
            else:
                target_idx = offset + i

                # If the chosen target is the wood sword cave, retry.
                if (0 <= target_idx < len(cave_types)
                        and cave_types[target_idx] == _CAVE_TYPE_WOOD_SWORD):
                    advance = False
                else:
                    swap_idx = target_idx
                    current_type = cave_types[i]

                    if current_type >= 10:
                        # Both non-dungeon: swap freely.
                        if 0 <= swap_idx < len(cave_types) and cave_types[swap_idx] >= 10:
                            do_swap = True
                    else:
                        # Current is a dungeon: check it won't glitch by landing
                        # on the overworld screen matching its entrance_room.
                        if 0 <= swap_idx < len(cave_screens):
                            dungeon_num = current_type
                            if (0 <= dungeon_num < len(dungeon_original_screens)
                                    and cave_screens[swap_idx] == dungeon_original_screens[dungeon_num]):
                                # Would cause glitch — retry.
                                advance = False
                            else:
                                # Also check the target dungeon won't glitch.
                                if 0 <= swap_idx < len(cave_types):
                                    target_type = cave_types[swap_idx]
                                    if (target_type < 10
                                            and 0 <= target_type < len(dungeon_original_screens)
                                            and cave_screens[i] == dungeon_original_screens[target_type]):
                                        advance = False
                                    else:
                                        do_swap = True

            if do_swap:
                swap_idx = offset + i
                if 0 <= swap_idx < len(cave_types):
                    cave_types[i], cave_types[swap_idx] = cave_types[swap_idx], cave_types[i]

            if advance:
                i += 1

    # ------------------------------------------------------------------
    # Step 6: Write back to GameWorld
    # ------------------------------------------------------------------
    result = CaveShuffleResult()
    any_road_slot = 0  # sequential index into overworld.any_road_screens

    for i, screen_num in enumerate(cave_screens):
        cave_type = cave_types[i]
        screen = screens_by_num.get(screen_num)
        if screen is None:
            continue

        # Update destination and tile data for this screen.
        screen.destination  = Destination(cave_type)

        if 1 <= cave_type <= 9:
            # Dungeon entrance: record which overworld screen this dungeon now uses.
            result.dungeon_entrance_screens[cave_type] = screen_num

        elif cave_type == _CAVE_TYPE_ANY_ROAD:
            # Any-road cave: update the any_road_screens list and patch
            # exit_x_position and stairs_position_code for the new screen.
            if any_road_slot < len(overworld.any_road_screens):
                overworld.any_road_screens[any_road_slot] = screen_num
            any_road_slot += 1
            screen.exit_x_position      = _ANY_ROAD_STAIRS_CODE
            screen.stairs_position_code = _ANY_ROAD_STAIRS_CODE

        elif cave_type == _CAVE_TYPE_WOOD_SWORD:
            result.wood_sword_screen = screen_num

    # ------------------------------------------------------------------
    # Step 7: Final validation
    # ------------------------------------------------------------------
    if overworld_block_needed:
        if not _overworld_block_exists(
            cave_types, cave_screens,
            raft_locations, recorder_locations, bracelet_locations,
        ):
            return None

    return result


# ---------------------------------------------------------------------------
# Overworld block flag screen sets
# ---------------------------------------------------------------------------

# Screens that become RAFT-gated when extra_raft_blocks is on.
# (Westlake Mall and Casino Corner region; vanilla type: OPEN)
_EXTRA_RAFT_SCREENS = frozenset([0x0E, 0x0F, 0x1F, 0x34, 0x44])

# Screen that becomes RAFT_AND_BOMB when extra_raft_blocks is on.
# (vanilla type: BOMB — already bomb-gated, so it becomes both)
_EXTRA_RAFT_AND_BOMB_SCREENS = frozenset([0x1E])

# Screens that become POWER_BRACELET_AND_BOMB when extra_power_bracelet_blocks
# is on. (West Death Mountain; vanilla type: BOMB)
_EXTRA_PB_AND_BOMB_SCREENS = frozenset([0x00, 0x01, 0x02, 0x03, 0x10, 0x12, 0x13])


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------

def apply_entrance_type_overrides(game_world: GameWorld, config: GameConfig) -> None:
    """Apply entrance type overrides for active overworld block flags, mutating game_world.

    Must be called before shuffle_caves() and assumed_fill() — both derive
    reachability from Screen.entrance_type.
    """
    if not (config.extra_raft_blocks or config.extra_power_bracelet_blocks):
        return
    for screen in game_world.overworld.screens:
        s = screen.screen_num
        if config.extra_raft_blocks:
            if s in _EXTRA_RAFT_SCREENS:
                screen.entrance_type = EntranceType.RAFT
            elif s in _EXTRA_RAFT_AND_BOMB_SCREENS:
                screen.entrance_type = EntranceType.RAFT_AND_BOMB
        if config.extra_power_bracelet_blocks:
            if s in _EXTRA_PB_AND_BOMB_SCREENS:
                screen.entrance_type = EntranceType.POWER_BRACELET_AND_BOMB


def randomize_entrances(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Apply entrance type overrides and shuffle cave entrances.

    ORDERING CONSTRAINT: must run before assumed_fill(). Both the cave
    shuffler and the game validator derive reachability from
    Screen.entrance_type. If overrides are applied after either step,
    items can be placed behind requirements the logic doesn't know exist,
    producing unbeatable seeds.

    Mutates game_world in place.
    """
    # Step 1: Apply entrance type overrides for active overworld block flags.
    apply_entrance_type_overrides(game_world, config)

    # Step 2: Shuffle cave entrances if any shuffle flag is on.
    if not (config.shuffle_dungeon_entrances or config.shuffle_non_dungeon_caves or config.shuffle_armos_location):
        return

    raft_locations = [0x2F, 0x45]
    if config.extra_raft_blocks:
        raft_locations = raft_locations + list(_EXTRA_RAFT_SCREENS) + list(_EXTRA_RAFT_AND_BOMB_SCREENS)

    bracelet_locations: list[int] = []
    if config.extra_power_bracelet_blocks:
        bracelet_locations = list(_EXTRA_PB_AND_BOMB_SCREENS)

    lost_hills_screens: frozenset[int] = frozenset()
    dead_woods_screens: frozenset[int] = frozenset()
    if config.randomize_lost_hills:
        lost_hills_screens = _screens_with_destination(game_world, Destination.LOST_HILLS_HINT)
    if config.randomize_dead_woods:
        dead_woods_screens = _screens_with_destination(game_world, Destination.DEAD_WOODS_HINT)

    shuffle_kwargs = dict(
        shuffle=config.shuffle_non_dungeon_caves,
        include_bracelet_caves=config.include_any_road_caves,
        include_wood_sword_cave=config.include_wood_sword_cave,
        shuffle_armos=config.shuffle_armos_location,
        add_armos_item=config.shuffle_armos_item,
        mirror_ow=False,
        just_dungeons=config.shuffle_dungeon_entrances and not config.shuffle_non_dungeon_caves,
        shuffle_dungeons=config.shuffle_dungeon_entrances,
        overworld_block_needed=config.shuffle_non_dungeon_caves,
        raft_locations=raft_locations,
        bracelet_locations=bracelet_locations,
        lost_hills_screens=lost_hills_screens,
        dead_woods_screens=dead_woods_screens,
    )

    # The shuffle is randomized and may produce an arrangement that fails the
    # overworld block check. Retry up to 50 times with fresh RNG draws before
    # giving up. Each failed attempt already wrote back to game_world, but the
    # next attempt rebuilds working lists from the (now-shuffled) state and
    # re-shuffles, so stale state doesn't accumulate.
    max_attempts = 50
    result = None
    for _ in range(max_attempts):
        result = shuffle_caves(game_world, rng, **shuffle_kwargs)
        if result is not None:
            break
    if result is None:
        raise RuntimeError("Cave shuffle failed — overworld block check not satisfied after "
                           f"{max_attempts} attempts")
