"""The overworld quests other than the first (overworld-behavior.md OW-MIX, OW-QST).

Mixed Quest - 1st (C01 = 2; OW-MIX-01 to OW-MIX-10): the eleven first-quest secret caves are dealt
over the 31 secret positions of both quests, the dealt positions are shown and the others hidden,
and the recorder reveals the secrets of the second quest's listed screens where they were dealt.
Mixed Quest - 2nd (C01 = 3; OW-QST-01, OW-QST-02): the same with the eighteen second-quest codes,
after the seven second-quest codes join their regular entries. 2nd Quest (C01 = 1; OW-QST-03 to
OW-QST-05): nothing is dealt; the cave list is the second quest's, screens 11, 60 and 116 take
their second-quest bytes, and the recorder reveals the second quest's secrets. The cave walk then
runs on the new list (shuffle_caves, with screen 60 out of the wooden-sword set). Random (C01 = 4)
resolves to one of 0-3 per seed (OW-QST-06, FL-DEP-04)."""
from dataclasses import dataclass

from ...model.enums import Destination, Enemy, QuestVisibility
from ...model.overworld import Overworld
from ...model.rooms import EnemySpec
from ..rng import IntRng
from .cave_entries import ENROLLED_SCREENS, Entry

# OW-APP-A7: the first-quest secret positions (PRG0 quest field 1), in OW-MIX-02's order, then the
# second-quest positions (field 2 with a nonzero code; screen 57 has code 0 and is none).
FIRST_QUEST_SECRET_POSITIONS = (5, 33, 39, 44, 71, 98, 103, 107, 109, 113, 123)
SECOND_QUEST_SECRET_POSITIONS = (0, 2, 6, 9, 17, 21, 24, 25, 27, 32, 41, 43, 48, 58, 83, 88, 96, 108,
                                 110, 114)
SECRET_POSITIONS = FIRST_QUEST_SECRET_POSITIONS + SECOND_QUEST_SECRET_POSITIONS
# OW-QST-01: the second-quest positions whose codes C01 = 3 deals (ascending, without 25 and 27,
# whose codes 7 and 5 stay out: one code 5 and one code 7 fewer than the second quest's caves)
SECOND_QUEST_DEALT_POSITIONS = tuple(screen for screen in SECOND_QUEST_SECRET_POSITIONS if screen not in (25, 27))
# OW-QST: the seven second-quest codes on regular screens: screen -> (code, inner palette)
SECOND_QUEST_REGULAR_CODES = {14: (30, 3), 15: (32, 3), 34: (33, 0), 52: (3, 3), 60: (2, 3), 69: (4, 2),
                              116: (30, 2)}
# OW-QST-03: the first-quest screens 2nd Quest leaves out of the regular entries; they keep their
# PRG0 dungeon codes 5 and 7 (OW-QST-05) and are not doors
SECOND_QUEST_LEFTOVER_SCREENS = frozenset({11, 66})
SECOND_QUEST_UNLISTED_SCREEN = 57    # quest field 2, code 0: keeps its field under 2nd Quest
# OW-CAVE-02's regular entries: the first 61 of OW-APP-A1's list, where step 2's exchange put 123
# in the wooden-sword screen's place; under C01 = 2 the last dealt entry takes that place instead.
REGULAR_ENTRY_COUNT = 61
WOOD_SWORD_SCREEN = 119
WOOD_SWORD_LIST_INDEX = ENROLLED_SCREENS.index(123)

# OW-MIX-04: the list byte that matches no screen, and screen 60's second-quest layout
NO_SCREEN = 0x80
SCREEN_60 = 60
SCREEN_60_LAYOUT = 0x7B              # LevelBlockAttrsD[60] bits 6-0 (bit 7 is the monster passes')
SCREEN_60_EXIT_ROW = 1               # LevelBlockAttrsF[60] = $01: exit row 1, quest field 0, index 0
# OW-QST-04 step 1: 2nd Quest switches off the recorder list's first entry (screen 66)
FIRST_RECORDER_ENTRY = 0
# OW-QST-04 steps 3 and 4: screen 11's layout and monster bytes, screen 116's exit and layout
SCREEN_11 = 11
SCREEN_11_LAYOUT = 0x7B              # LevelBlockAttrsD[11] = $7B (bit 7 clear)
SCREEN_11_MONSTERS = 0x2F            # LevelBlockAttrsC[11] = $2F: list $2F, count index 0
SCREEN_116 = 116
SCREEN_116_EXIT_X, SCREEN_116_OUTER_PALETTE = 7, 2    # LevelBlockAttrsA[116] = $72
SCREEN_116_LAYOUT = 0x5A             # LevelBlockAttrsD[116] bits 6-0 (bit 7 is the monster passes')


@dataclass(frozen=True)
class DealtSecret:
    """OW-MIX-02: one of the eleven first-quest codes and the position it was dealt to."""
    screen: int
    code: int


def deal_secret_positions(rng: IntRng, count: int = len(FIRST_QUEST_SECRET_POSITIONS)) -> list[int]:
    """OW-MIX-02 (and OW-QST-01 with 18 codes): for k = 1..count, r uniform in 0..31 - k (one
    draw each), T[k] and T[k + r] exchanged; p(k) = T[k]. Each p(k) is uniform over the positions
    not yet drawn."""
    positions = list(SECRET_POSITIONS)
    for index in range(count):
        offset = rng.below(len(positions) - index)
        positions[index], positions[index + offset] = positions[index + offset], positions[index]
    return positions[:count]


def _entry(overworld: Overworld, screen: int) -> Entry:
    """A list entry with the screen's own cave byte."""
    return Entry(screen, overworld.screens[screen].destination, overworld.screens[screen].inner_palette)


def _second_quest_code(screen: int) -> tuple[Destination, int]:
    code, palette = SECOND_QUEST_REGULAR_CODES[screen]
    return Destination(code), palette


def with_second_quest_codes(entries: list[Entry]) -> list[Entry]:
    """OW-QST-02 and OW-QST-03: the regular entries on the seven screens take the second-quest
    codes, code and inner palette (in the list entry; the walk then moves the codes)."""
    return [Entry(entry.screen, *_second_quest_code(entry.screen)) if entry.screen in SECOND_QUEST_REGULAR_CODES
            else entry for entry in entries]


def mixed_quest_entries(overworld: Overworld, rng: IntRng,
                        source_positions: tuple[int, ...] = FIRST_QUEST_SECRET_POSITIONS) -> list[Entry]:
    """OW-MIX-02 and OW-MIX-03 (OW-QST-01 for the second-quest variant): the deal, the quest fields,
    and the cave list it gives: the 61 regular entries, then the dealt pairs in deal order with
    OW-CAVE-02 step 2's exchange (the wooden-sword entry last, the last dealt pair in its place).
    Each dealt position keeps its own inner palette; only the code moves."""
    codes = [overworld.screens[screen].destination for screen in source_positions]
    dealt = deal_secret_positions(rng, len(source_positions))
    show_dealt_positions(overworld, frozenset(dealt))
    dealt_entries = [Entry(screen, code, overworld.screens[screen].inner_palette)
                     for screen, code in zip(dealt, codes, strict=True)]
    regular = [_entry(overworld, screen) for screen in ENROLLED_SCREENS[:REGULAR_ENTRY_COUNT]]
    if source_positions == SECOND_QUEST_DEALT_POSITIONS:
        regular = with_second_quest_codes(regular)
    wood_sword = _entry(overworld, WOOD_SWORD_SCREEN)
    regular[WOOD_SWORD_LIST_INDEX] = dealt_entries[-1]
    return [*regular, *dealt_entries[:-1], wood_sword]


def show_dealt_positions(overworld: Overworld, dealt: frozenset[int]) -> None:
    """OW-MIX-03: a dealt position's hidden bit is cleared (a first-quest position keeps field 1,
    a second-quest one goes from 2 to 0); every other position becomes field 3, never shown. A
    hidden position keeps its cave byte."""
    for screen_num in SECRET_POSITIONS:
        screen = overworld.screens[screen_num]
        if screen_num not in dealt:
            screen.quest_visibility = QuestVisibility.NEITHER_QUEST
        elif screen.quest_visibility is QuestVisibility.SECOND_QUEST:
            screen.quest_visibility = QuestVisibility.BOTH_QUESTS


def open_recorder_secrets(overworld: Overworld, dealt: frozenset[int]) -> None:
    """OW-MIX-04 steps 1-3: the first quest reveals every listed screen's secret; a listed
    second-quest position that was not dealt matches no screen; screen 60 takes its second-quest
    layout (LevelBlockAttrsA[60] already holds PRG0's second-quest $72)."""
    overworld.recorder_reveals_listed_secrets_in_first_quest = True
    overworld.recorder_secret_screens = [
        NO_SCREEN if screen in SECOND_QUEST_SECRET_POSITIONS and screen not in dealt else screen
        for screen in overworld.recorder_secret_screens]
    screen = overworld.screens[SCREEN_60]
    screen.screen_code = SCREEN_60_LAYOUT
    screen.exit_y_position = SCREEN_60_EXIT_ROW
    screen.enemies_from_sides = False
    screen.stairs_position_code = 0
    screen.quest_visibility = QuestVisibility.BOTH_QUESTS


def mix_overworld_quest(overworld: Overworld, rng: IntRng,
                        source_positions: tuple[int, ...] = FIRST_QUEST_SECRET_POSITIONS) -> list[Entry]:
    """OW-MIX-02 to OW-MIX-04 (Mixed Quest - 1st), or with SECOND_QUEST_DEALT_POSITIONS OW-QST-01
    and OW-QST-02 (Mixed Quest - 2nd), before the cave walk: the cave list the walk runs on."""
    entries = mixed_quest_entries(overworld, rng, source_positions)
    open_recorder_secrets(overworld, frozenset(entry.screen for entry in entries
                                               if entry.screen in SECRET_POSITIONS))
    return entries


def prepare_second_quest_screen_11(overworld: Overworld) -> None:
    """OW-QST-04 step 3 (2nd Quest), before the overworld monster pass: screen 11's layout byte
    $7B and monster byte $2F, which PS-OWM-01 then leaves (not a candidate)."""
    screen = overworld.screens[SCREEN_11]
    screen.screen_code = SCREEN_11_LAYOUT
    screen.enemy_spec = EnemySpec(enemy=Enemy(SCREEN_11_MONSTERS))
    screen.enemy_quantity = overworld.qty_table[0]


def second_quest_entries(overworld: Overworld) -> list[Entry]:
    """OW-QST-03: the 61 regular entries without screens 11 and 66 (59), then the 20 second-quest
    positions in ascending order with their PRG0 cave bytes; the seven second-quest codes join
    their entries and their screens' cave bytes; OW-CAVE-02 step 2 exchanges the wooden-sword
    entry with the last (114). No draws."""
    regular = [_entry(overworld, screen) for screen in ENROLLED_SCREENS[:REGULAR_ENTRY_COUNT]]
    regular[WOOD_SWORD_LIST_INDEX] = _entry(overworld, WOOD_SWORD_SCREEN)      # PRG0's order, before step 2
    entries = with_second_quest_codes(
        [entry for entry in regular if entry.screen not in SECOND_QUEST_LEFTOVER_SCREENS]
        + [_entry(overworld, screen) for screen in SECOND_QUEST_SECRET_POSITIONS])
    for screen_num in SECOND_QUEST_REGULAR_CODES:
        screen = overworld.screens[screen_num]
        screen.destination, screen.inner_palette = _second_quest_code(screen_num)
    sword = next(index for index, entry in enumerate(entries) if entry.screen == WOOD_SWORD_SCREEN)
    entries[sword], entries[-1] = entries[-1], entries[sword]
    return entries


def show_second_quest(overworld: Overworld) -> None:
    """OW-QST-03's quest fields and OW-QST-04 steps 1, 2 and 4: the 20 second-quest positions shown,
    the 11 first-quest positions never (57 keeps field 2); the recorder list's first entry off
    and the branch reversed, so the first quest reveals the second quest's ten recorder secrets;
    screen 60 as OW-MIX-04 step 3; screen 116's exit and layout bytes."""
    for screen_num in SECRET_POSITIONS:
        screen = overworld.screens[screen_num]
        screen.quest_visibility = (QuestVisibility.BOTH_QUESTS if screen_num in SECOND_QUEST_SECRET_POSITIONS
                                   else QuestVisibility.NEITHER_QUEST)
    open_recorder_secrets(overworld, frozenset(SECOND_QUEST_SECRET_POSITIONS))
    overworld.recorder_secret_screens[FIRST_RECORDER_ENTRY] = NO_SCREEN
    screen = overworld.screens[SCREEN_116]
    screen.exit_x_position, screen.outer_palette = SCREEN_116_EXIT_X, SCREEN_116_OUTER_PALETTE
    screen.has_zola = screen.has_ocean_sound = False
    screen.screen_code = SCREEN_116_LAYOUT
    screen.exit_y_position = 0
    screen.enemies_from_sides = False
    screen.stairs_position_code = 0
    screen.quest_visibility = QuestVisibility.BOTH_QUESTS


def second_quest_overworld(overworld: Overworld) -> list[Entry]:
    """OW-QST-03 and OW-QST-04 (2nd Quest), before the cave walk: the cave list the walk runs on."""
    entries = second_quest_entries(overworld)
    show_second_quest(overworld)
    return entries


SHOWN = (QuestVisibility.BOTH_QUESTS, QuestVisibility.FIRST_QUEST)


def is_second_quest_overworld(overworld: Overworld) -> bool:
    """2nd Quest's mark in any finished world: the recorder list's first entry (screen 66)
    switched off (OW-QST-04 step 1; OW-QST-06 reads it the same way)."""
    return overworld.recorder_secret_screens[FIRST_RECORDER_ENTRY] == NO_SCREEN


def door_screen(overworld: Overworld, level: int) -> int | None:
    """A level's door: the lowest-numbered shown screen holding its code, except that under
    2nd Quest screens 11 and 66 keep dungeon codes 5 and 7 but are not doors (OW-QST-05: every
    rule that looks for a door uses the entry door)."""
    leftovers = SECOND_QUEST_LEFTOVER_SCREENS if is_second_quest_overworld(overworld) else frozenset()
    return next((screen.screen_num for screen in overworld.screens
                 if screen.destination.is_level and screen.destination.level_num == level
                 and screen.quest_visibility in SHOWN and screen.screen_num not in leftovers), None)
