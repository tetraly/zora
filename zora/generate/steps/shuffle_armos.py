"""Shuffle Armos (B13; OW-CAVE-05): the secret Armos and its screen."""

from zora.generate.rng import IntRng
from zora.generate.steps.cave_entries import Entry
from zora.model.enums import QuestVisibility
from zora.model.overworld import Overworld

# OW-APP-A5: the secret Armos formation screens, in table order, and the Xs
# each may draw.
ARMOS_FORMATION = ((36, (32, 80, 128, 176, 224)), (11, (48, 80, 144, 176)),
                   (28, (112, 144, 176, 208)), (34, (48, 64, 80, 160, 176, 192)),
                   (52, (32, 64, 96)), (61, (96, 144)), (78, (80, 160)))
ARMOS_SWAP_POSITIONS = (0, 2, 4, 5, 6)                          # OW-CAVE-05 step 2

ARMOS_SCREEN = 36                    # the formation's always-written screen
ARMOS_SCREEN_EXIT_X = 0x4            # LevelBlockAttrsA[36] = $43: exit X nibble 4 ...
ARMOS_SCREEN_OUTER_PALETTE = 3       # ... outer palette 3, no zora, no sea sound
ARMOS_SCREEN_EXIT_ROW = 3            # LevelBlockAttrsF[36] = $03
REPOINTED_INNER_PALETTE = 3


def shuffle_armos(overworld: Overworld, rng: IntRng, entries: list[Entry]) -> int:
    """OW-CAVE-05 steps 1-4: the formation tables, screen 36's bytes and
    the re-pointed entry. Returns the armos screen A."""
    screens = [screen for screen, _ in ARMOS_FORMATION]
    x_positions = [x_choices[rng.below(len(x_choices))] for _, x_choices in ARMOS_FORMATION]
    swap = ARMOS_SWAP_POSITIONS[rng.below(len(ARMOS_SWAP_POSITIONS))]
    for table in (screens, x_positions):
        table[0], table[swap] = table[swap], table[0]
    overworld.armos_screen_ids, overworld.armos_positions = screens, x_positions
    armos = screens[0]
    target = overworld.screens[ARMOS_SCREEN]
    target.exit_x_position = ARMOS_SCREEN_EXIT_X
    target.has_zola = target.has_ocean_sound = False
    target.outer_palette = ARMOS_SCREEN_OUTER_PALETTE
    target.quest_visibility = QuestVisibility.BOTH_QUESTS
    target.stairs_position_code = 0
    target.enemies_from_sides = False
    target.exit_y_position = ARMOS_SCREEN_EXIT_ROW
    if armos != ARMOS_SCREEN:
        # every A but 36 is enrolled: its entry moves to 36, and A's own
        # cave byte stays PRG0's for the rest of the pass
        entry = next(candidate for candidate in entries if candidate.screen == armos)
        entry.screen, entry.inner_palette = ARMOS_SCREEN, REPOINTED_INNER_PALETTE
        overworld.screens[armos].quest_visibility = QuestVisibility.NEITHER_QUEST   # F |= $C0
    return armos
