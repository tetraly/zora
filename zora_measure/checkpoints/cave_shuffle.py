"""Cave Shuffle's other values (C05 = 0, 1, 2 and 4) and Shuffle Wood Sword Cave and Shuffle Take
Any Road Caves off (B02, B04) (overworld-behavior.md OW-CAVE-09 to OW-CAVE-12; acceptance.md
VA-REJ-21): the Checks measured on finished ROMs, against the one-field corpora of the MVP
baseline's string (zora_measure.corpora.corpus(name))."""
from zora.generate.steps.cave_entries import DUNGEONS, ENROLLED_SCREENS, FIXED_SCREENS, WOOD_SWORD_SCREENS
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora_measure.checkpoints.groups_and_palettes import _vanilla
from zora_measure.checkpoints.overworld import destinations_changed, start_room_ban
from zora_measure.checkpoints.overworld_quests import RANGE
from zora_measure.checkpoints.start_rooms import start_room_on_own_door
from zora_measure.checkpoints.summaries import FLAG_COUNTS, Checkpoint, count_true, distribution, ratio_total

SPEC_CAVES = "overworld-behavior.md @ W25"
SPEC_E9 = "acceptance.md @ A66"
# The one-field corpora's strings: the MVP baseline corpus string with one field changed
VANILLA_CAVES_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UEpV"          # C05 = 0
DUNGEON_DOORS_ONLY_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UGEO"     # C05 = 1
NON_DUNGEON_CAVES_ONLY_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UHeH"  # C05 = 2
RANDOM_CAVES_FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UKT3"           # C05 = 4
WOOD_SWORD_CAVE_OFF_FLAGS = "8hq4BeR1JXo89AzFrUYy8uZIJkiJ3A"    # B02 off
ANY_ROAD_CAVES_OFF_FLAGS = "8hq4BeR1JXo898Ktie!3Xv2FhbUJ3A"     # B04 off

WOOD_SWORD_HOME = 119                  # $77, the wooden-sword cave's PRG0 screen
ARMOS_SCREEN = 36
ANY_ROAD_HOMES = (29, 35, 73, 121)     # the code-20 screens of PRG0
# What the walk did, read from a finished first-quest ROM (OW-CAVE-09)
NO_WALK, DOORS_ONLY, NON_DUNGEON_ONLY, BOTH_PARTS = "no walk", "doors only", "non-dungeon only", "both parts"
WALKS = (NO_WALK, DOORS_ONLY, NON_DUNGEON_ONLY, BOTH_PARTS)


def _is_door(code: int) -> bool:
    return code in DUNGEONS


def _starting_codes(gw: GameWorld) -> dict[int, int]:
    """Each first-quest entry's screen as the walk found it (OW-CAVE-05's re-pointing made: the
    armos screen's entry moved to 36) and the PRG0 code it held then."""
    prg0 = [int(screen.destination) for screen in _vanilla().overworld.screens]
    armos = gw.overworld.armos_screen_ids[0]
    return {ARMOS_SCREEN if screen == armos else screen: prg0[screen] for screen in ENROLLED_SCREENS}


def walk_parts(gw: GameWorld) -> str:
    """OW-CAVE-09: which parts of the walk ran, from the codes that changed screen. Doors only: only
    door codes moved, among door screens. Non-dungeon only: no door moved but, at most, the one
    exchanged with the wooden-sword cave. A walk that left every code in place reads as no walk."""
    codes = [int(screen.destination) for screen in gw.overworld.screens]
    changed = [(start, codes[screen]) for screen, start in _starting_codes(gw).items() if codes[screen] != start]
    if not changed:
        return NO_WALK
    if all(_is_door(start) and _is_door(final) for start, final in changed):
        return DOORS_ONLY
    crossings = [(start, final) for start, final in changed if _is_door(start) != _is_door(final)]
    doors_moved = any(_is_door(start) and _is_door(final) for start, final in changed)
    wood_sword_exchange = (len(crossings) == 2
                           and {Destination.WOOD_SWORD_CAVE} == {code for pair in crossings for code in pair
                                                                 if not _is_door(code)})
    if not doors_moved and (not crossings or wood_sword_exchange):
        return NON_DUNGEON_ONLY
    return BOTH_PARTS


def door_on_wood_sword_home(gw: GameWorld) -> dict[str, bool]:
    """OW-CAVE-09 (C05 = 2): the dungeon whose door the wooden-sword cave's exchange put on $77."""
    code = int(gw.overworld.screens[WOOD_SWORD_HOME].destination)
    return {f"D{dungeon}": code == dungeon for dungeon in (1, 2, 3, 5, 6)}


def wood_sword_placement(gw: GameWorld) -> dict[str, bool]:
    """OW-CAVE-09 and OW-CAVE-12: code 16 on an OW-APP-A3 screen; on $77."""
    screen = next(screen.screen_num for screen in gw.overworld.screens
                  if screen.destination == Destination.WOOD_SWORD_CAVE)
    return {"on A3": screen in WOOD_SWORD_SCREENS, "on $77": screen == WOOD_SWORD_HOME}


def fixed_screens_kept(gw: GameWorld) -> bool:
    """OW-CAVE-09 and OW-CAVE-12: the fixed screens (OW-APP-A2) keep their PRG0 cave bytes."""
    base = _vanilla().overworld.screens
    return all((gw.overworld.screens[screen].destination, gw.overworld.screens[screen].inner_palette)
               == (base[screen].destination, base[screen].inner_palette) for screen in FIXED_SCREENS)


def any_road_caves_at_home(gw: GameWorld) -> bool:
    """OW-CAVE-12 (B04 off): code 20 on 29, 35, 73 and 121, the take-any-road record and those
    screens' `LevelBlockAttrsF` bytes as PRG0 has them."""
    base, overworld = _vanilla().overworld, gw.overworld
    return (all(overworld.screens[screen].destination == Destination.ANY_ROAD for screen in ANY_ROAD_HOMES)
            and list(overworld.any_road_screens) == list(base.any_road_screens)
            and all(overworld.screens[screen].stairs_position_code == base.screens[screen].stairs_position_code
                    for screen in ANY_ROAD_HOMES))


def any_road_record_follows(gw: GameWorld) -> bool:
    """OW-CAVE-09: the four bytes at 0x19344 are the code-20 screens in list order."""
    armos = gw.overworld.armos_screen_ids[0]
    order = [ARMOS_SCREEN if screen == armos else screen for screen in ENROLLED_SCREENS]
    screens = [screen.screen_num for screen in gw.overworld.screens if screen.destination == Destination.ANY_ROAD]
    return list(gw.overworld.any_road_screens) == sorted(screens, key=order.index)


WALK_PARTS = distribution(WALKS)
_BAN = Checkpoint("OW-CAVE-03", "no door of dungeon d on S(d)", "9000/9000", SPEC_CAVES, start_room_ban, ratio_total)
_FIXED = Checkpoint("OW-CAVE-09", "fixed screens keep their PRG0 cave bytes", "1000/1000", SPEC_CAVES,
                    fixed_screens_kept, count_true)
_E9 = Checkpoint("VA-REJ-21", "a level's start room on its own door (E9 lets none through)", "0/1000", SPEC_E9,
                 start_room_on_own_door, count_true)
_CHANGED = Checkpoint("OW-CAVE-02", "screens whose cave code differs from PRG0", "(see the value's row)",
                      SPEC_CAVES, destinations_changed, RANGE)


def _walks(spec: str) -> Checkpoint:
    return Checkpoint("OW-CAVE-09", "walk: none / doors only / non-dungeon only / both parts", spec, SPEC_CAVES,
                      walk_parts, WALK_PARTS)


def _wood_sword(spec: str) -> Checkpoint:
    return Checkpoint("OW-CAVE-09", "code 16 on an A3 screen / on $77", spec, SPEC_CAVES, wood_sword_placement,
                      FLAG_COUNTS)


def _door_on_77(spec: str) -> Checkpoint:
    return Checkpoint("OW-CAVE-09", "door on $77: dungeon 1 / 2 / 3 / 5 / 6", spec, SPEC_CAVES,
                      door_on_wood_sword_home, FLAG_COUNTS)


_RECORD = Checkpoint("OW-CAVE-04", "take-any-road record is the code-20 screens in list order", "1000/1000",
                     SPEC_CAVES, any_road_record_follows, count_true)

# Each corpus's rows; the spec's figures from OW-CAVE-09 to OW-CAVE-12 (the C05 = 0 and 1 corpora
# also hold the seeds where OW-CAVE-10's coin turned the non-dungeon part on)
CAVE_SHUFFLE_SETS = {
    "c05-vanilla": (_walks("525 / 0 / 475 / 0 (coin 475 of 1,000)"),
                    _door_on_77("88 in all (OW-CAVE-10)"), _wood_sword("1000 / -"), _BAN, _FIXED, _RECORD, _E9),
    "c05-dungeons": (_walks("0 / 507 / 0 / 493 (coin 493 of 1,000)"), _wood_sword("1000 / -"), _BAN, _FIXED,
                     _RECORD, _E9),
    "c05-nondungeons": (_walks("0 / 0 / 1000 / 0"), _door_on_77("33 / 45 / 38 / 26 / 42 (184 in all)"),
                        _wood_sword("1000 / 43"), Checkpoint("OW-CAVE-09", "screens whose cave code differs from PRG0",
                                                             "49 to 64", SPEC_CAVES, destinations_changed, RANGE),
                        _BAN, _FIXED, _RECORD, _E9),
    "c05-random": (_walks("140 / 128 / 389 / 343"), _door_on_77("69 in all (non-dungeon part only)"),
                   _wood_sword("1000 / -"), _BAN, _FIXED, _RECORD, _E9),
    "b02-off": (_wood_sword("1000 / 1000"), Checkpoint("OW-CAVE-12", "screens whose cave code differs from PRG0",
                                                       "59 to 71", SPEC_CAVES, destinations_changed, RANGE),
                _BAN, _FIXED, _E9),       # no record row: with B02 off the list keeps PRG0's order
    "b04-off": (Checkpoint("OW-CAVE-12", "code 20, its record and F bytes as PRG0's", "1000/1000", SPEC_CAVES,
                           any_road_caves_at_home, count_true), _wood_sword("1000 / 38"), _CHANGED, _BAN, _FIXED, _E9),
}
CAVE_SHUFFLE_FLAGS = {"c05-vanilla": VANILLA_CAVES_FLAGS, "c05-dungeons": DUNGEON_DOORS_ONLY_FLAGS,
                      "c05-nondungeons": NON_DUNGEON_CAVES_ONLY_FLAGS, "c05-random": RANDOM_CAVES_FLAGS,
                      "b02-off": WOOD_SWORD_CAVE_OFF_FLAGS, "b04-off": ANY_ROAD_CAVES_OFF_FLAGS}
