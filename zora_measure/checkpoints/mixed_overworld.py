"""Mixed overworld quest, first-quest variant (C01 = 2; overworld-behavior.md OW-MIX-01 to
OW-MIX-10): the Checks measured on finished ROMs. The spec's figures are the original randomizer's
"mixed finals" (flag string MIXED_OVERWORLD_FLAGS, seeds 1-1000), the corpus
corpus("ow-mixed") (hash manifest docs/spec/corpus-ow-mixed-final-hash-manifest.csv)."""
import statistics
from collections import Counter
from functools import cache

from zora.generate.steps.cave_entries import (
    LADDER_SCREENS,
    MIXED_RECORDER_SCREENS,
    SHORTCUT_POSITION_INDEX,
    WOOD_SWORD_SCREENS,
)
from zora.generate.steps.mixed_overworld_quest import (
    FIRST_QUEST_SECRET_POSITIONS,
    NO_SCREEN,
    SCREEN_60,
    SCREEN_60_EXIT_ROW,
    SCREEN_60_LAYOUT,
    SECOND_QUEST_SECRET_POSITIONS,
    SECRET_POSITIONS,
)
from zora.generate.steps.shuffle_caves import LADDER_ANY_ROAD_EXIT_ROW, LADDER_ANY_ROAD_EXIT_X
from zora.model.enums import Destination, QuestVisibility
from zora.model.game_world import GameWorld
from zora.model.overworld import Screen
from zora_measure.checkpoints.summaries import Summary

SPEC_MIX = "overworld-behavior.md @ a269b1a"
# OW-MIX's "mixed finals": the corpus string (CP-5) with C01 = 2 and no other change
MIXED_OVERWORLD_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3C"
SHOWN = (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST)
DUNGEONS = range(1, 10)


@cache
def prg0_world() -> GameWorld:
    """PRG0's world, to compare against (the measures run in scripts and tests only)."""
    from zora.rom.base_rom import remember_repo_base_rom
    from zora.rom.parse.rom_file import parse_rom
    return parse_rom(remember_repo_base_rom())


def prg0_recorder_list() -> tuple[int, ...]:
    """PRG0's recorder list (FluteRoomSecretsOW), in order, read from the base ROM."""
    return tuple(prg0_world().overworld.recorder_secret_screens)


def _shown(screen: Screen) -> bool:
    return screen.quest_visibility in SHOWN


def dealt_positions(gw: GameWorld) -> tuple[int, ...]:
    """OW-MIX-01/02: the secret positions whose quest field is not 3 (shown)."""
    return tuple(screen for screen in SECRET_POSITIONS
                 if gw.overworld.screens[screen].quest_visibility is not QuestVisibility.NEITHER_QUEST)


def eleven_shown(gw: GameWorld) -> bool:
    """OW-MIX-01: exactly 11 of the 31 positions are shown."""
    return len(dealt_positions(gw)) == len(FIRST_QUEST_SECRET_POSITIONS)


def first_quest_dealt(gw: GameWorld) -> int:
    """OW-MIX-02: how many of the eleven dealt positions are first-quest positions."""
    return sum(screen in FIRST_QUEST_SECRET_POSITIONS for screen in dealt_positions(gw))


def per_position(gw: GameWorld) -> tuple[bool, ...]:
    """OW-MIX-02: whether each of the 31 positions was dealt."""
    dealt = set(dealt_positions(gw))
    return tuple(screen in dealt for screen in SECRET_POSITIONS)


def _per_position_text(values: list[tuple[bool, ...]]) -> str:
    counts = [sum(value[index] for value in values) for index in range(len(SECRET_POSITIONS))]
    return f"each dealt in {min(counts)} to {max(counts)}"


PER_POSITION = Summary(_per_position_text, lambda value: {
    f"screen {screen}": float(flag) for screen, flag in zip(SECRET_POSITIONS, value, strict=True)})


def _visible_codes(gw: GameWorld) -> Counter[int]:
    return Counter(int(screen.destination) for screen in gw.overworld.screens
                   if _shown(screen) and screen.destination != Destination.NONE)


def visible_code_multiset(gw: GameWorld) -> bool:
    """OW-MIX-02: the visible cave codes (field 0 or 1, code not 0) are PRG0's first-quest ones."""
    return _visible_codes(gw) == _visible_codes(prg0_world())


def palette_bits_kept(gw: GameWorld) -> bool:
    """OW-MIX-02: every screen's inner-palette bits are PRG0's."""
    return all(screen.inner_palette == base.inner_palette
               for screen, base in zip(gw.overworld.screens, prg0_world().overworld.screens, strict=True))


def hidden_positions_kept(gw: GameWorld) -> bool:
    """OW-MIX-03: every hidden position keeps its PRG0 cave code and palette."""
    base = prg0_world().overworld.screens
    dealt = set(dealt_positions(gw))
    return all(gw.overworld.screens[screen].destination == base[screen].destination
               and gw.overworld.screens[screen].inner_palette == base[screen].inner_palette
               for screen in SECRET_POSITIONS if screen not in dealt)


def hidden_dungeon_codes(gw: GameWorld) -> dict[str, float]:
    """OW-MIX-03: hidden positions holding dungeon code 5..9."""
    dealt = set(dealt_positions(gw))
    codes = Counter(int(gw.overworld.screens[screen].destination) for screen in SECRET_POSITIONS
                    if screen not in dealt)
    return {f"code {code}": float(codes[code]) for code in range(5, 10)}


SUMMED = Summary(lambda values: " ".join(f"{key.split()[-1]}: {sum(v[key] for v in values):g}"
                                         for key in values[0]) if values else "-",
                 lambda value: value)


def recorder_bytes(gw: GameWorld) -> dict[str, bool]:
    """OW-MIX-04 steps 1-3: the branch, the list rule and screen 60's layout."""
    overworld = gw.overworld
    dealt = set(dealt_positions(gw))
    expected = [NO_SCREEN if screen in SECOND_QUEST_SECRET_POSITIONS and screen not in dealt else screen
                for screen in prg0_recorder_list()]
    screen_60 = overworld.screens[SCREEN_60]
    return {"branch": overworld.recorder_reveals_listed_secrets_in_first_quest,
            "list": overworld.recorder_secret_screens == expected,
            "screen 60": (screen_60.screen_code == SCREEN_60_LAYOUT and screen_60.exit_y_position == SCREEN_60_EXIT_ROW
                          and screen_60.quest_visibility is QuestVisibility.BOTH_QUESTS
                          and screen_60.stairs_position_code == 0 and not screen_60.enemies_from_sides)}


def live_second_quest_list_screens(gw: GameWorld) -> int:
    """OW-MIX-04: listed second-quest screens whose list byte still matches."""
    return sum(screen in SECOND_QUEST_SECRET_POSITIONS for screen in gw.overworld.recorder_secret_screens)


def _median_text(values: list[int]) -> str:
    return f"{min(values)} to {max(values)} (median {statistics.median(values):g})"


MEDIAN_RANGE = Summary(_median_text, lambda value: {"mean": float(value)})


def wood_sword_screen(gw: GameWorld) -> int | None:
    """OW-MIX-05: the screen of code 16 (the wooden-sword cave)."""
    return next((screen.screen_num for screen in gw.overworld.screens
                 if screen.destination == Destination.WOOD_SWORD_CAVE), None)


def wood_sword_placement(gw: GameWorld) -> dict[str, bool]:
    """OW-MIX-05: code 16 on OW-APP-A3 without 60; on 60, 32, 33 or 119."""
    screen = wood_sword_screen(gw)
    return {"in A3 without 60": screen in WOOD_SWORD_SCREENS - {SCREEN_60},
            "on 32": screen == 32, "on 33": screen == 33, "on 119": screen == 119}


def ladder_any_road_exits(gw: GameWorld) -> tuple[int, int]:
    """OW-MIX-05 step 3: (code-20 caves on screens 24/25 with exit row 4 and exit X L(V),
    code-20 caves on 24/25)."""
    placed = [gw.overworld.screens[screen] for screen in sorted(LADDER_SCREENS)
              if gw.overworld.screens[screen].destination == Destination.ANY_ROAD]
    right = [screen for screen in placed
             if screen.exit_y_position == LADDER_ANY_ROAD_EXIT_ROW
             and screen.exit_x_position == LADDER_ANY_ROAD_EXIT_X[SHORTCUT_POSITION_INDEX[screen.screen_num]]]
    return len(right), len(placed)


def changed_screens(gw: GameWorld) -> int:
    """OW-MIX-05: screens whose cave code differs from PRG0's."""
    return sum(screen.destination != base.destination
               for screen, base in zip(gw.overworld.screens, prg0_world().overworld.screens, strict=True))


def one_visible_door_each(gw: GameWorld) -> bool:
    """OW-MIX-06 and OW-MIX-10: each dungeon 1-9 has exactly one visible door."""
    doors = Counter(screen.destination.level_num for screen in gw.overworld.screens
                    if _shown(screen) and screen.destination.is_level)
    return all(doors[dungeon] == 1 for dungeon in DUNGEONS)


def door_on_recorder_screen(gw: GameWorld) -> bool:
    """OW-MIX-08: some visible door, or the white-sword cave, stands on a recorder-set screen."""
    return any(_shown(screen) and screen.screen_num in MIXED_RECORDER_SCREENS
               and (screen.destination.is_level or screen.destination == Destination.WHITE_SWORD_CAVE)
               for screen in gw.overworld.screens)


def single_codes(gw: GameWorld) -> dict[str, bool]:
    """OW-MIX-10: one visible code-19 screen; one code-18 screen."""
    screens = gw.overworld.screens
    return {"code 19 shown once": sum(_shown(s) and s.destination == Destination.MAGICAL_SWORD_CAVE
                                      for s in screens) == 1,
            "code 18 once": sum(s.destination == Destination.WHITE_SWORD_CAVE for s in screens) == 1}
