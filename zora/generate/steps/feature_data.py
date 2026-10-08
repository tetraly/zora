"""B10 DATA pass: draw and apply the values specified by features-behavior.md.

This module is DATA-only: it mutates fields in GameWorld that the serializer
writes as byte patches. The flag-switched DATA steps (change_bomb_upgrades,
change_money_making_game, speed_up_text) are generation steps of their own
(generation_pass.STEPS); this module writes the items with no flag. The
CODE patches are zora/rom/code_patches.py; FP-PERSON-01's draw is
zora/generate/steps/person_appearances.py, which runs before the hint text.
"""
from zora.model.game_world import GameWorld
from zora.rom.layout import CREDITS_COPYRIGHT_POINTER, CREDITS_RECORD_CPU_ADDRESSES
from zora.version import PLAYER_NAME, PLAYER_VERSION


def write_fixed_feature_data(gw: GameWorld, seed: int) -> None:
    """The DATA items with no flag of their own, which come with the
    feature switch: the title, the fixes and the level-9 refusal text."""
    # FP-TITLE-01: seed number shown on title screen.
    gw.title_seed_number = seed
    gw.title_version_line = f"{PLAYER_NAME} {PLAYER_VERSION}".upper()      # "ZORA 2.0 BETA 1"

    # FP-RESET-01, FP-BEEP-01, FP-FIX-01, FP-Q2R-01, FP-LEVEL-01.
    gw.reset_controller1 = 0xFA
    gw.low_health_beep_value = 0x00
    gw.dmc_level_value = 0x40
    gw.q2_room_trigger_value = 0x01
    gw.level_dash_tile = 0x2F

    # FP-LOCK-02: replacement records in bank-2 free space.
    # Line 15 keeps PRG0's copyright pointer.
    gw.credits_pointers = (*CREDITS_RECORD_CPU_ADDRESSES, CREDITS_COPYRIGHT_POINTER)

    # FP-TRIF-01: the level-9 entrance refusal text, ZORA's own wording. The
    # serializer writes it outside the hint block and points slot 34 at it.
    gw.level9_refusal_text = "YOU NEED EIGHT\nTRIFORCE PIECES."
