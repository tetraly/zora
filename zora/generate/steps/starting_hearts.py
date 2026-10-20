"""Starting hearts at every value (C16; flags-behavior.md FL-ALT-02 and FL-ALT-07)."""

from ...model.game_world import GameWorld

# Quirk (FL-ALT-07): at most three of the containers start full, and a Continue restores as many.
MOST_FULL_HEARTS = 3
# FL-ALT-07: PRG0 draws the life meter blank when HeartValues is $00 (one container, none full);
# FormatHeartsInTextBuf's BEQ @EmitSpace (operand at 0x06731, PRG0 $04) becomes a branch of 0.
ONE_HEART_METER_BRANCH = 0x00


def set_starting_hearts(gw: GameWorld, heart_containers: int) -> None:
    """FL-ALT-02 and FL-ALT-07: a new save file (and the second-quest switch) starts with
    `heart_containers` containers, the smaller of that and three of them full; a Continue
    restores that many full hearts; with one container the meter draws its heart. HeartPartial
    stays $FF; the life toll's heart count follows the containers (person_code). No draw."""
    full_hearts = min(heart_containers, MOST_FULL_HEARTS)
    gw.new_file_heart_containers = heart_containers
    gw.new_file_full_hearts = full_hearts
    gw.continue_hearts_operand = full_hearts - 1
    if heart_containers == 1:
        gw.heart_meter_blank_branch = ONE_HEART_METER_BRANCH
