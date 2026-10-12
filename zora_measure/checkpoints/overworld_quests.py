"""Overworld Quest: 2nd Quest (C01 = 1), Mixed Quest - 2nd (C01 = 3) and Random (C01 = 4)
(overworld-behavior.md OW-QST-01 to OW-QST-06): the Checks measured on finished ROMs. The spec's
figures are the original randomizer's quest2, mixed2 and quest-random corpora
(zora_measure.corpora.corpus(name); hash manifests in docs/spec/)."""
from collections import Counter

from zora.generate.steps.cave_entries import WOOD_SWORD_SCREENS
from zora.generate.steps.mixed_overworld_quest import (
    FIRST_QUEST_SECRET_POSITIONS,
    NO_SCREEN,
    SCREEN_11,
    SCREEN_11_LAYOUT,
    SCREEN_11_MONSTERS,
    SCREEN_60,
    SCREEN_60_EXIT_ROW,
    SCREEN_60_LAYOUT,
    SCREEN_116,
    SCREEN_116_EXIT_X,
    SCREEN_116_LAYOUT,
    SCREEN_116_OUTER_PALETTE,
    SECOND_QUEST_LEFTOVER_SCREENS,
    SECOND_QUEST_REGULAR_CODES,
    SECOND_QUEST_SECRET_POSITIONS,
    SECOND_QUEST_UNLISTED_SCREEN,
    SECRET_POSITIONS,
    is_second_quest_overworld,
)
from zora.model.enums import Destination, QuestVisibility
from zora.model.game_world import GameWorld
from zora.model.overworld import Screen
from zora_measure.checkpoints.mixed_overworld import (
    SHOWN,
    dealt_positions,
    prg0_recorder_list,
    prg0_world,
    wood_sword_screen,
)
from zora_measure.checkpoints.summaries import Summary

SPEC_QST = "overworld-behavior.md @ e24b9ed"
SECOND_QUEST_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3B"        # CP-5 with C01 = 1
MIXED_SECOND_QUEST_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3D"  # CP-5 with C01 = 3
RANDOM_QUEST_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3E"        # CP-5 with C01 = 4
DUNGEONS = range(1, 10)
ARMOS_SCREEN = 36
SCREEN_52 = 52
MIXED_SECOND_DEALT = 18


def _shown(screen: Screen) -> bool:
    return screen.quest_visibility in SHOWN


def _visible_codes(gw: GameWorld) -> Counter[int]:
    return Counter(int(screen.destination) for screen in gw.overworld.screens
                   if _shown(screen) and screen.destination != Destination.NONE)


def _second_quest_caves() -> Counter[int]:
    """PRG0's second-quest caves (quest field 0 or 2, nonzero code) with the seven codes written."""
    caves: Counter[int] = Counter()
    for screen in prg0_world().overworld.screens:
        if screen.quest_visibility in (QuestVisibility.BOTH_QUESTS, QuestVisibility.SECOND_QUEST):
            code = SECOND_QUEST_REGULAR_CODES.get(screen.screen_num, (int(screen.destination), 0))[0]
            if code:
                caves[code] += 1
    return caves


def resolved_quest(gw: GameWorld) -> int:
    """OW-QST-06: the quest a finished ROM shows: 0 with PRG0's branch, 1 with the first recorder
    entry off, else 2 or 3 by how many secret positions are shown (11 or 18)."""
    overworld = gw.overworld
    if not overworld.recorder_reveals_listed_secrets_in_first_quest:
        return 0
    if is_second_quest_overworld(overworld):
        return 1
    return 3 if len(dealt_positions(gw)) == MIXED_SECOND_DEALT else 2


def second_quest_fields(gw: GameWorld) -> dict[str, bool]:
    """OW-QST-03: the 20 second-quest positions field 0, the 11 first-quest positions field 3,
    screen 57 field 2, every other screen its PRG0 field (the vacated Armos screen aside)."""
    screens, base = gw.overworld.screens, prg0_world().overworld.screens
    armos = gw.overworld.armos_screen_ids[0]
    others = all(screen.quest_visibility == base[screen.screen_num].quest_visibility for screen in screens
                 if screen.screen_num not in SECRET_POSITIONS
                 and screen.screen_num not in (SECOND_QUEST_UNLISTED_SCREEN, ARMOS_SCREEN, armos, SCREEN_60,
                                               SCREEN_116))
    return {"second-quest positions shown": all(screens[s].quest_visibility is QuestVisibility.BOTH_QUESTS
                                                for s in SECOND_QUEST_SECRET_POSITIONS),
            "first-quest positions never": all(screens[s].quest_visibility is QuestVisibility.NEITHER_QUEST
                                               for s in FIRST_QUEST_SECRET_POSITIONS),
            "57 field 2": screens[SECOND_QUEST_UNLISTED_SCREEN].quest_visibility is QuestVisibility.SECOND_QUEST,
            "others PRG0's": others}


def seven_codes_palettes(gw: GameWorld) -> dict[str, bool]:
    """OW-QST-02/03: the seven screens hold the second-quest palette bits (52 its own byte when the
    Armos formation vacates it), every other screen PRG0's."""
    screens, base = gw.overworld.screens, prg0_world().overworld.screens
    armos = gw.overworld.armos_screen_ids[0]
    seven = all(screens[s].inner_palette == palette for s, (_code, palette) in SECOND_QUEST_REGULAR_CODES.items()
                if not (s == SCREEN_52 and armos == SCREEN_52))
    elsewhere = all(screens[s].inner_palette == base[s].inner_palette for s in range(len(screens))
                    if s not in SECOND_QUEST_REGULAR_CODES and s != ARMOS_SCREEN)
    return {"the seven": seven, "elsewhere PRG0's": elsewhere, "52 vacated": armos == SCREEN_52}


def leftovers_kept(gw: GameWorld) -> bool:
    """OW-QST-03/05: screens 11 and 66 keep their PRG0 cave bytes."""
    screens, base = gw.overworld.screens, prg0_world().overworld.screens
    return all((screens[s].destination, screens[s].inner_palette) == (base[s].destination, base[s].inner_palette)
               for s in SECOND_QUEST_LEFTOVER_SCREENS)


def second_quest_visible_caves(gw: GameWorld) -> bool:
    """OW-QST-03: the visible caves are PRG0's second-quest caves with the seven codes (81)."""
    return _visible_codes(gw) == _second_quest_caves()


def mixed_second_visible_caves(gw: GameWorld) -> bool:
    """OW-QST-02: the visible caves are the second quest's without one code 5 and one code 7 (79)."""
    expected = _second_quest_caves() - Counter({5: 1, 7: 1})
    return _visible_codes(gw) == expected


def second_quest_screens(gw: GameWorld) -> dict[str, bool]:
    """OW-QST-04: the recorder list and branch; screens 60, 11 and 116's bytes."""
    overworld = gw.overworld
    s60, s11, s116 = (overworld.screens[s] for s in (SCREEN_60, SCREEN_11, SCREEN_116))
    return {"list": overworld.recorder_secret_screens == [NO_SCREEN, *prg0_recorder_list()[1:]],
            "branch $D0": overworld.recorder_reveals_listed_secrets_in_first_quest,
            "60": s60.screen_code == SCREEN_60_LAYOUT and s60.exit_y_position == SCREEN_60_EXIT_ROW,
            "11": s11.screen_code == SCREEN_11_LAYOUT and s11.enemy_spec.enemy.value == SCREEN_11_MONSTERS,
            "116": (s116.exit_x_position == SCREEN_116_EXIT_X and s116.outer_palette == SCREEN_116_OUTER_PALETTE
                    and s116.screen_code == SCREEN_116_LAYOUT and s116.exit_y_position == 0
                    and s116.quest_visibility is QuestVisibility.BOTH_QUESTS)}


def second_quest_doors(gw: GameWorld) -> dict[str, bool]:
    """OW-QST-05: visible door counts 1,1,1,1,2,1,2,1,1 (the second door 11 or 66); without 11 and
    66 one each; code 16 on OW-APP-A3 without 11, 33 and 60."""
    doors = Counter(screen.destination.level_num for screen in gw.overworld.screens
                    if _shown(screen) and screen.destination.is_level)
    without = Counter(screen.destination.level_num for screen in gw.overworld.screens
                      if _shown(screen) and screen.destination.is_level
                      and screen.screen_num not in SECOND_QUEST_LEFTOVER_SCREENS)
    return {"counts 1,1,1,1,2,1,2,1,1": [doors[d] for d in DUNGEONS] == [1, 1, 1, 1, 2, 1, 2, 1, 1],
            "one each without 11 and 66": all(without[d] == 1 for d in DUNGEONS),
            "code 16 on A3 less 11, 33, 60": wood_sword_screen(gw) in WOOD_SWORD_SCREENS - {11, 33, 60}}


def mixed_second_shown(gw: GameWorld) -> bool:
    """OW-QST-01: 18 of the 31 positions shown."""
    return len(dealt_positions(gw)) == MIXED_SECOND_DEALT


def first_quest_among_dealt(gw: GameWorld) -> int:
    """OW-QST-01: first-quest positions among the 18 dealt (3 to 10)."""
    return sum(screen in FIRST_QUEST_SECRET_POSITIONS for screen in dealt_positions(gw))


def _range_text(values: list[int]) -> str:
    return f"{min(values)} to {max(values)}"


RANGE = Summary(_range_text, lambda value: {"mean": float(value)})


def quest_value(gw: GameWorld) -> str:
    return str(resolved_quest(gw))


def random_quest_checks(gw: GameWorld) -> dict[str, bool]:
    """OW-QST-06: each ROM passes its resolved value's checks (keyed by that value)."""
    from zora_measure.checkpoints.mixed_overworld import eleven_shown, one_visible_door_each, recorder_bytes
    value = resolved_quest(gw)
    if value == 0:
        passed = gw.overworld.recorder_secret_screens == list(prg0_recorder_list()) and one_visible_door_each(gw)
    elif value == 1:
        passed = (all(second_quest_fields(gw).values()) and all(second_quest_screens(gw).values())
                  and second_quest_visible_caves(gw)
                  and all(v for k, v in second_quest_doors(gw).items()))
    elif value == 2:
        passed = eleven_shown(gw) and all(recorder_bytes(gw).values()) and one_visible_door_each(gw)
    else:
        passed = (mixed_second_shown(gw) and all(recorder_bytes(gw).values()) and one_visible_door_each(gw)
                  and mixed_second_visible_caves(gw))
    return {f"{v} passes": passed if v == value else False for v in range(4)}


# Force Overworld Block (B81, OW-CAVE-08): --set b81, at the b81 corpus's string
FORCE_BLOCK_FLAGS = "GmCbTYod8E8ige5DkbI77QKcaPh6lF8PHUJ3A"     # CP-5 with B81 on
FORCE_BLOCK_SCREENS = frozenset({29, 35, 47, 66, 69, 73, 121})   # the screens that can pass the test under C01 = 0


def gated_doors(gw: GameWorld) -> int:
    """OW-CAVE-08: visible dungeon doors and the white-sword cave on the screens that can pass the test."""
    return sum(1 for screen in gw.overworld.screens
               if screen.screen_num in FORCE_BLOCK_SCREENS and _shown(screen)
               and (screen.destination.is_level or screen.destination == Destination.WHITE_SWORD_CAVE))


def _gated_text(values: list[int]) -> str:
    counts = Counter(min(value, 3) for value in values)
    return f"{sum(v > 0 for v in values)}/{len(values)} (one {counts[1]}, two {counts[2]}, three to five {counts[3]})"


GATED_DOORS = Summary(_gated_text, lambda value: {"some": float(value > 0), "one": float(value == 1),
                                                  "two": float(value == 2), "three+": float(value >= 3)})


# Allow OW Blocks of Wood Sword (B03, OW-CAVE-07): --set b03, at the spec's B03 run string (no
# corpus: the rows compare ZORA with the figures the spec reports)
WOOD_SWORD_BLOCKS_FLAGS = "8hq4BeR1JXo89CIRQPLPRuKJdJpJ3A"     # the corpus string with B03 on


def wood_sword_widened(gw: GameWorld) -> dict[str, bool]:
    """OW-CAVE-07: code 16 sits on the widened set computed from the finished ROM (its Armos and
    coast items, and its start items: FP-START-04); and outside OW-APP-A3."""
    from zora.generate.steps.wood_sword_behind_blocks import wood_sword_extra_screens
    from zora.model.overworld import OverworldItem
    overworld = gw.overworld
    armos = overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    coast = overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    assert armos is not None and coast is not None
    widened = WOOD_SWORD_SCREENS | wood_sword_extra_screens(overworld, int(armos.item), int(coast.item),
                                                            frozenset(gw.start_items))
    screen = wood_sword_screen(gw)
    return {"on the widened set": screen in widened, "outside A3": screen not in WOOD_SWORD_SCREENS}
