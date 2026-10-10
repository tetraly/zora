"""Starting hearts 4 (C16 = 3; flags-behavior.md FL-ALT-02)."""

from ...model.game_world import GameWorld

FOUR_HEART_CONTAINERS = 4
# Quirk (FL-ALT-02): the full hearts stay three, so the fourth heart starts empty.
FULL_HEARTS = 3


def start_with_four_hearts(gw: GameWorld) -> None:
    """FL-ALT-02: a new save file starts with four heart containers, three of them full.
    HeartPartial, the hearts a Continue restores, the life toll's heart count and every other
    starting value stay FP-START-01's; no draw."""
    gw.new_file_heart_containers = FOUR_HEART_CONTAINERS
    gw.new_file_full_hearts = FULL_HEARTS
