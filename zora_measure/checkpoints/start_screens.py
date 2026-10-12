"""Start Screen: Full Start Shuffle (C04 = 2, OW-START-02) and Wood Sword Screen (C04 = 3,
OW-START-03): the Checks measured on finished ROMs. The spec's figures are the original
randomizer's start-full and start-wsword corpora (corpus("start-full") and corpus("start-wsword");
hash manifests in docs/spec/)."""
from collections import Counter

from zora.generate.steps.shuffle_start_screen import (
    FULL_START_SCREENS,
    PRG0_START_SCREEN,
    REDIRECTED_START_SCREENS,
    SCREEN_BELOW,
    start_y,
)
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora_measure.checkpoints.mixed_overworld import prg0_world
from zora_measure.checkpoints.summaries import Summary

SPEC_START = "overworld-behavior.md @ e24b9ed"
FULL_START_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJFs"         # CP-5 with C04 = 2
WOOD_SWORD_START_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJSZ"   # CP-5 with C04 = 3
MIXED_CODE_BIT = 0x40          # the model's enemy code carries LevelBlockAttrsD bit 7 as $40
START_YS = (0x8D, 0x7D, 0xAD, 0x5D)


def start_screen_of(gw: GameWorld) -> int:
    return gw.overworld.start_screen


def start_in_full_list(gw: GameWorld) -> bool:
    """OW-START-02: S is one of the 90 screens."""
    return start_screen_of(gw) in FULL_START_SCREENS


def per_start_screen(gw: GameWorld) -> tuple[bool, ...]:
    """OW-START-02: which of the 90 screens is S."""
    return tuple(start_screen_of(gw) == screen for screen in sorted(FULL_START_SCREENS))


def _occurrence_text(values: list[tuple[bool, ...]]) -> str:
    counts = [sum(value[index] for value in values) for index in range(len(FULL_START_SCREENS))]
    occurring = sum(count > 0 for count in counts)
    return f"{occurring} of {len(counts)} occur, {min(counts)} to {max(counts)} times"


PER_START_SCREEN = Summary(_occurrence_text, lambda value: {
    f"screen ${screen:02X}": float(flag) for screen, flag in zip(sorted(FULL_START_SCREENS), value, strict=True)})


def start_y_values(gw: GameWorld) -> dict[str, bool]:
    """OW-START-01 step 2 with OW-START-02's table: Link's start Y as the formula gives it from S.
    The corpora keep PRG0's $8D in LevelInfo_StartY (the original randomizer stores the value elsewhere), so
    the byte is not measured; ZORA's is checked against the formula in tests/test_start_screens.py."""
    y = start_y(start_screen_of(gw))
    return {f"${value:02X}": y == value for value in START_YS}


def start_carries(gw: GameWorld) -> dict[str, bool]:
    """S carries a cave, a dungeon door, or code 16 (the wooden-sword cave)."""
    destination = gw.overworld.screens[start_screen_of(gw)].destination
    return {"a cave": destination != Destination.NONE, "a dungeon door": destination.is_level,
            "code 16": destination == Destination.WOOD_SWORD_CAVE}


def monster_exchange(gw: GameWorld) -> dict[str, bool]:
    """OW-START-01 steps 3-4 (S not 119): S holds monster byte $00 with its layout byte's bit 7
    clear, 119's monster byte differs from PRG0, 119's bit 7 is set, and the other seven bits
    of 119's layout byte are PRG0's."""
    screens, base = gw.overworld.screens, prg0_world().overworld.screens
    start = start_screen_of(gw)
    moved = start != PRG0_START_SCREEN
    s_screen, home = screens[start], screens[PRG0_START_SCREEN]
    empty = (s_screen.enemy_spec.enemy.value == 0 and s_screen.enemy_quantity == gw.overworld.qty_table[0])
    home_differs = (home.enemy_spec, home.enemy_quantity) != (base[PRG0_START_SCREEN].enemy_spec,
                                                              base[PRG0_START_SCREEN].enemy_quantity)
    return {"S not 119": moved,
            "S empty, bit 7 clear": moved and empty,
            "119's monsters differ": moved and home_differs,
            "119's bit 7 set": home.enemy_spec.enemy.value >= MIXED_CODE_BIT,
            "119's layout PRG0's": home.screen_code == base[PRG0_START_SCREEN].screen_code}


def wood_sword_screens(gw: GameWorld) -> list[int]:
    return [screen.screen_num for screen in gw.overworld.screens if screen.destination == Destination.WOOD_SWORD_CAVE]


def wood_sword_start(gw: GameWorld) -> dict[str, bool]:
    """OW-START-03: code 16 on exactly one screen; S is that screen, or the one below a
    redirected screen; S holds code 16; S is 30 because code 16 is on 14."""
    caves = wood_sword_screens(gw)
    expected = caves[0] + SCREEN_BELOW if caves and caves[0] in REDIRECTED_START_SCREENS else (caves or [0])[0]
    return {"code 16 once": len(caves) == 1, "S follows code 16": start_screen_of(gw) == expected,
            "S holds code 16": start_screen_of(gw) in caves, "14 to 30": bool(caves) and caves[0] == 14}


def _distinct_text(values: list[int]) -> str:
    return f"{len(Counter(values))} different screens"


DISTINCT_STARTS = Summary(_distinct_text, lambda value: {})
