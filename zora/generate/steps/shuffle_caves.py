"""The cave shuffle, the dungeon-door map and the recorder destinations
(overworld-behavior.md OW-CAVE-01..06, OW-ENTR-02, OW-WARP-01).

Works on a GameWorld's Overworld model (not raw bytes): a screen's
`destination` is its LevelBlockAttrsB bits 7-2, `inner_palette` bits 1-0,
`stairs_position_code` LevelBlockAttrsF bits 5-4 and `quest_visibility`
bits 7-6. The flow stages a copy of the model and ships it with the seed.
"""
from dataclasses import dataclass

from ...flags.fields import CaveShuffle as CaveShuffleValue
from ...model.enums import Destination
from ...model.overworld import Overworld
from ..rng import IntRng
from .cave_entries import (
    BRACELET_SCREENS,
    DUNGEONS,
    ENROLLED_SCREENS,
    LADDER_SCREENS,
    SHORTCUT_POSITION_INDEX,
    WOOD_SWORD_SCREENS,
    CaveShuffle,
    Entry,
)
from .mixed_overworld_quest import SCREEN_60
from .overworld_gates import DEAD_WOODS_HINT_SHOP, LOST_HILLS_HINT_SHOP, NO_GATES, OverworldGates


@dataclass(frozen=True)
class CaveWalkParts:
    """OW-CAVE-09: the walk's two parts. The dungeon part visits the entries holding a dungeon code
    (1-9) and exchanges them only among themselves; the non-dungeon part visits the entries holding
    a code above 9 and exchanges them only among themselves, but for the wooden-sword visit, whose
    partner comes from OW-APP-A3 whatever its code (rule (b) of OW-CAVE-03). Both parts are
    OW-CAVE-02's walk; neither skips it."""
    dungeon_doors: bool = True
    non_dungeon_caves: bool = True

    @property
    def walks(self) -> bool:
        return self.dungeon_doors or self.non_dungeon_caves

    def visits(self, code: Destination) -> bool:
        return self.dungeon_doors if code in DUNGEONS else self.non_dungeon_caves

    def may_exchange(self, visitor: Destination, partner: Destination) -> bool:
        """With one part only, the partner is redrawn until it holds a code of the visitor's part."""
        return (self.dungeon_doors and self.non_dungeon_caves) or ((visitor in DUNGEONS) == (partner in DUNGEONS))


# OW-CAVE-09: the parts each C05 value turns on (C05 = 3, All Caves, both)
DUNGEON_PART_VALUES = frozenset({CaveShuffleValue.DUNGEON_DOORS_ONLY, CaveShuffleValue.ALL_CAVES})
NON_DUNGEON_PART_VALUES = frozenset({CaveShuffleValue.NON_DUNGEON_CAVES_ONLY, CaveShuffleValue.ALL_CAVES})
ALL_CAVES_WALK = CaveWalkParts()


def cave_walk_parts(cave_shuffle: CaveShuffleValue, mixed_overworld_quest: bool) -> CaveWalkParts:
    """OW-CAVE-09: C05's two parts; a mixed overworld quest (C01 = 2 or 3) turns the non-dungeon
    part on whatever C05 says (OW-MIX-05 step 1, OW-QST-02). C01 = 1 does not (OW-QST-03)."""
    return CaveWalkParts(dungeon_doors=cave_shuffle in DUNGEON_PART_VALUES,
                         non_dungeon_caves=cave_shuffle in NON_DUNGEON_PART_VALUES or mixed_overworld_quest)


def _is_illegal_exchange(first: Entry, second: Entry, start_rooms: dict[int, int]) -> bool:
    """OW-CAVE-03's start-room ban, both ways. Quirk (OW-K-02): S(d) is a
    dungeon room number read as an overworld screen."""
    return ((first.code in DUNGEONS and second.screen == start_rooms[first.code])
            or (second.code in DUNGEONS and first.screen == start_rooms[second.code]))


def _is_gated_exchange(first: Entry, second: Entry, gates: OverworldGates) -> bool:
    """A hint shop would move behind its own maze (either way)."""
    return second.screen in gates.barred_for(first.code) or first.screen in gates.barred_for(second.code)


def walk_destination_codes(entries: list[Entry], start_rooms: dict[int, int],
                           rng: IntRng, fixed: frozenset[Destination] = frozenset(),
                           gates: OverworldGates = NO_GATES,
                           wood_sword_screens: frozenset[int] = WOOD_SWORD_SCREENS,
                           parts: CaveWalkParts = ALL_CAVES_WALK, sword_partner_caves_only: bool = False) -> None:
    """OW-CAVE-02 step 3 with OW-CAVE-03's rules: each entry exchanges its
    code with a drawn partner, redrawn until legal. Rule (a) bars a partner
    holding the wooden-sword code, but only on visits by other entries. On
    the wooden-sword entry's own (last) visit, rule (b), the drawn partner is
    discarded and the partner comes from the entries on OW-APP-A3 screens;
    choosing itself is a legal self-exchange (the finals keep code 16 on
    119 in 45 of 1,000). When the start-room ban refuses that pair, the
    whole visit repeats: a new partner is drawn and discarded, then a new one
    (OW-CAVE-03, W9).

    fixed: codes that never move (ZORA's B04 off: the take-any-road caves keep their PRG0
    screens). Their entries are not visited and a draw landing on one is redrawn; with none
    fixed the walk is OW-CAVE-02's exactly.

    gates: the owner's 2.0 overworld gates (owner decisions, 2026-10-07): the wooden-sword cave's
    partners leave out every gated screen, and an exchange that would put a hint shop behind its
    own maze is refused like the start-room ban (the whole visit repeats). With no gates the walk
    is unchanged.

    wood_sword_screens: OW-APP-A3, less screen 60 under a mixed overworld quest (OW-MIX-05 step 2:
    its layout is no longer $0A).

    parts: OW-CAVE-09's parts: an entry whose code's part is off is not visited, and with one part
    only a drawn partner of the other part is redrawn (the wooden-sword visit aside).

    sword_partner_caves_only: ZORA's own (Expanded Dungeon Locations' "Expanded + shuffle everything
    else"): the wooden-sword visit's partners leave out the dungeon doors, which the deal placed and
    the walk never moves; the spec's partner may be a dungeon door on an OW-APP-A3 screen."""
    sword_barred = gates.wood_sword_barred()
    sword_partners = [index for index, entry in enumerate(entries)
                      if entry.screen in wood_sword_screens and entry.screen not in sword_barred
                      and not (sword_partner_caves_only and entry.code in DUNGEONS)]
    for entry in entries:
        if entry.code in fixed or not parts.visits(entry.code):
            continue
        while True:
            partner = rng.below(len(entries))
            if entry.code == Destination.WOOD_SWORD_CAVE:
                partner = sword_partners[rng.below(len(sword_partners))]
            elif entries[partner].code == Destination.WOOD_SWORD_CAVE:
                continue
            elif not parts.may_exchange(entry.code, entries[partner].code):
                continue
            if entries[partner].code in fixed:
                continue
            if not _is_illegal_exchange(entry, entries[partner], start_rooms) \
                    and not _is_gated_exchange(entry, entries[partner], gates):
                break
        entry.code, entries[partner].code = entries[partner].code, entry.code


# OW-MIX-05 step 3: a take-any-road cave on a ladder screen (24 or 25, entries only under a mixed
# overworld quest) takes cave-exit row 4 (2 when its shortcut index V is 0) and the cave-exit X
# L(V) for V = 0, 1, 2, 3
LADDER_ANY_ROAD_EXIT_ROW, LADDER_ANY_ROAD_EXIT_ROW_AT_0 = 4, 2
LADDER_ANY_ROAD_EXIT_X = (5, 4, 9, 6)


def write_back(overworld: Overworld, entries: list[Entry]) -> None:
    """OW-CAVE-04: each entry's cave byte at its screen; the code-20
    screens into the take-any-road array (list order), and their shortcut
    position index from OW-APP-A6 unless on a Bracelet-set screen (on a
    ladder screen, OW-MIX-05 step 3's exit first)."""
    any_road = []
    for entry in entries:
        screen = overworld.screens[entry.screen]
        screen.destination, screen.inner_palette = entry.code, entry.inner_palette
        if entry.code == Destination.ANY_ROAD:
            any_road.append(entry.screen)
            if entry.screen in LADDER_SCREENS:
                shortcut_index = SHORTCUT_POSITION_INDEX[entry.screen]
                screen.exit_y_position = (LADDER_ANY_ROAD_EXIT_ROW if shortcut_index
                                          else LADDER_ANY_ROAD_EXIT_ROW_AT_0)
                screen.exit_x_position = LADDER_ANY_ROAD_EXIT_X[shortcut_index]
            if entry.screen not in BRACELET_SCREENS:
                screen.stairs_position_code = SHORTCUT_POSITION_INDEX[entry.screen]
    overworld.any_road_screens = any_road


def enrolled_entries(overworld: Overworld) -> list[Entry]:
    """OW-CAVE-02 step 1: the enrolled entries, in OW-APP-A1's order. Building
    the list in that order already includes step 2's exchange (it moves all
    three fields)."""
    return [Entry(screen, overworld.screens[screen].destination,
                  overworld.screens[screen].inner_palette) for screen in ENROLLED_SCREENS]


# OW-APP-A1's entries before the wooden-sword entry's list position (OW-CAVE-02 step 2 puts 123, or
# under an overworld quest another entry, in its place)
ENTRIES_BEFORE_WOOD_SWORD = frozenset(ENROLLED_SCREENS[:ENROLLED_SCREENS.index(123)])


def leave_wood_sword_cave_in_place(entries: list[Entry]) -> list[Entry]:
    """OW-CAVE-12, Shuffle Wood Sword Cave off (B02): screen 119 is left out of the cave list, so
    step 2 of OW-CAVE-02 finds no code 16 and the list keeps PRG0's order. Every list is built with
    step 2's exchange already made (the wooden-sword entry last, the former last entry in its
    place); this undoes it. The wooden-sword entry stays in the list, but the walk never visits it
    and never draws it (shuffle_caves fixes code 16), which is the walk without it. Runs before
    Shuffle Armos, which may re-point an entry before the wooden-sword position to screen 36."""
    *listed, wood_sword = entries
    assert wood_sword.code == Destination.WOOD_SWORD_CAVE, wood_sword
    position = next(index for index, entry in enumerate(listed) if entry.screen not in ENTRIES_BEFORE_WOOD_SWORD)
    former_last = listed[position]
    listed[position] = wood_sword
    return [*listed, former_last]


def sell_dead_woods_path_outside_the_forest(entries: list[Entry], gates: OverworldGates,
                                            parts: CaveWalkParts) -> None:
    """ZORA's own rule (owner, 2026-10-15; docs/deviations.md): with Randomize Dead Woods on and
    the non-dungeon caves left in place (no non-dungeon part, OW-CAVE-09), the two hint shops that
    sell the maze paths exchange screens. In place, the shop selling the Dead Woods' path stands
    on $70, past the Dead Woods itself; after the exchange it stands on the Lost Hills' shop's
    screen ($1A, outside both mazes and the ladder's west half), and the Lost Hills' path is sold
    on $70, which needs only the Dead Woods' path. A walk with the non-dungeon part keeps each
    shop off its own maze already (_is_gated_exchange)."""
    if not gates.dead_woods or parts.non_dungeon_caves:
        return
    lost_hills_shop = next(entry for entry in entries if entry.code == LOST_HILLS_HINT_SHOP)
    dead_woods_shop = next(entry for entry in entries if entry.code == DEAD_WOODS_HINT_SHOP)
    lost_hills_shop.code, dead_woods_shop.code = dead_woods_shop.code, lost_hills_shop.code


def prg0_armos_screen(overworld: Overworld) -> int:
    """With Shuffle Armos off (B13, FL-OFF-02) the formation tables keep PRG0's
    and the armos screen is the one PRG0's first entry names."""
    return overworld.armos_screen_ids[0]


def shuffle_caves(overworld: Overworld, entries: list[Entry], armos: int, start_rooms: dict[int, int],
                  rng: IntRng, shuffle_take_any_road_caves: bool = True,
                  gates: OverworldGates = NO_GATES, screen_60_relaid: bool = False,
                  wood_sword_extra: frozenset[int] = frozenset(), move_wood_sword_cave: bool = True,
                  parts: CaveWalkParts = ALL_CAVES_WALK, dungeons_dealt: bool = False) -> CaveShuffle:
    """OW-CAVE-02 step 3 and OW-CAVE-04's write-back, after Shuffle Armos
    (OW-CAVE-05) has re-pointed its entry. start_rooms: dungeon ->
    LevelInfo_StartRoomId. With B04 off (ZORA's own value) the take-any-road caves stay.
    Every overworld quest but the first (C01 = 1, 2, 3) gives screen 60 its second-quest layout, so it
    leaves the wooden-sword set (OW-MIX-05, OW-QST-02, OW-QST-04). wood_sword_extra: the screens
    Allow OW Blocks of Wood Sword (B03) adds to the wooden-sword set (OW-CAVE-07). With Shuffle Wood
    Sword Cave off (B02, OW-CAVE-12) the wooden-sword cave stays on screen 119. parts: the walk's
    parts (OW-CAVE-09); with neither, step 3 is skipped and only the write-back runs. With Randomize
    Dead Woods on and no non-dungeon part, the two maze hint shops exchange screens first (ZORA's own
    rule: sell_dead_woods_path_outside_the_forest). dungeons_dealt: Expanded Dungeon Locations placed
    the dungeon doors (its deal), so the walk's dungeon part is off and the wooden-sword cave's
    partner is never a door."""
    if dungeons_dealt:
        parts = CaveWalkParts(dungeon_doors=False, non_dungeon_caves=parts.non_dungeon_caves)
    fixed = frozenset({code for code, moves in ((Destination.ANY_ROAD, shuffle_take_any_road_caves),
                                                (Destination.WOOD_SWORD_CAVE, move_wood_sword_cave)) if not moves})
    wood_sword_screens = WOOD_SWORD_SCREENS - {SCREEN_60} if screen_60_relaid else WOOD_SWORD_SCREENS
    wood_sword_screens |= wood_sword_extra
    if parts.walks:
        walk_destination_codes(entries, start_rooms, rng, fixed, gates, wood_sword_screens, parts,
                               sword_partner_caves_only=dungeons_dealt)
    sell_dead_woods_path_outside_the_forest(entries, gates, parts)
    write_back(overworld, entries)
    return CaveShuffle(entries, armos)
