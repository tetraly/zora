"""Speed Up Text (B54; FP-TEXT-01)."""

from zora.model.game_world import GameWorld


def speed_up_text(gw: GameWorld) -> None:
    """Speed Up Text (FP-TEXT-01): the person text's delay operand."""
    gw.text_speed_value = 0x02
