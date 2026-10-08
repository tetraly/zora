"""The cave shuffle, the dungeon-door map and the recorder destinations
(overworld-behavior.md OW-CAVE-01..06, OW-ENTR-02, OW-WARP-01).

Works on a GameWorld's Overworld model (not raw bytes): a screen's
`destination` is its LevelBlockAttrsB bits 7-2, `inner_palette` bits 1-0,
`stairs_position_code` LevelBlockAttrsF bits 5-4 and `quest_visibility`
bits 7-6. The flow stages a copy of the model and ships it with the seed.
"""
from zora.generate.rng import IntRng
from zora.generate.steps.cave_entries import (
    BRACELET_SCREENS,
    DUNGEONS,
    ENROLLED_SCREENS,
    SHORTCUT_POSITION_INDEX,
    WOOD_SWORD_SCREENS,
    CaveShuffle,
    Entry,
)
from zora.generate.steps.overworld_gates import NO_GATES, OverworldGates
from zora.model.enums import Destination
from zora.model.overworld import Overworld


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
                           gates: OverworldGates = NO_GATES) -> None:
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
    is unchanged."""
    sword_barred = gates.wood_sword_barred()
    sword_partners = [index for index, entry in enumerate(entries)
                      if entry.screen in WOOD_SWORD_SCREENS and entry.screen not in sword_barred]
    for entry in entries:
        if entry.code in fixed:
            continue
        while True:
            partner = rng.below(len(entries))
            if entry.code == Destination.WOOD_SWORD_CAVE:
                partner = sword_partners[rng.below(len(sword_partners))]
            elif entries[partner].code == Destination.WOOD_SWORD_CAVE:
                continue
            if entries[partner].code in fixed:
                continue
            if not _is_illegal_exchange(entry, entries[partner], start_rooms) \
                    and not _is_gated_exchange(entry, entries[partner], gates):
                break
        entry.code, entries[partner].code = entries[partner].code, entry.code


def write_back(overworld: Overworld, entries: list[Entry]) -> None:
    """OW-CAVE-04: each entry's cave byte at its screen; the code-20
    screens into the take-any-road array (list order), and their shortcut
    position index from OW-APP-A6 unless on a Bracelet-set screen."""
    any_road = []
    for entry in entries:
        screen = overworld.screens[entry.screen]
        screen.destination, screen.inner_palette = entry.code, entry.inner_palette
        if entry.code == Destination.ANY_ROAD:
            any_road.append(entry.screen)
            if entry.screen not in BRACELET_SCREENS:
                screen.stairs_position_code = SHORTCUT_POSITION_INDEX[entry.screen]
    overworld.any_road_screens = any_road


def enrolled_entries(overworld: Overworld) -> list[Entry]:
    """OW-CAVE-02 step 1: the enrolled entries, in OW-APP-A1's order. Building
    the list in that order already includes step 2's exchange (it moves all
    three fields)."""
    return [Entry(screen, overworld.screens[screen].destination,
                  overworld.screens[screen].inner_palette) for screen in ENROLLED_SCREENS]


def prg0_armos_screen(overworld: Overworld) -> int:
    """With Shuffle Armos off (B13, FL-OFF-02) the formation tables keep PRG0's
    and the armos screen is the one PRG0's first entry names."""
    return overworld.armos_screen_ids[0]


def shuffle_caves(overworld: Overworld, entries: list[Entry], armos: int, start_rooms: dict[int, int],
                  rng: IntRng, shuffle_take_any_road_caves: bool = True,
                  gates: OverworldGates = NO_GATES) -> CaveShuffle:
    """OW-CAVE-02 step 3 and OW-CAVE-04's write-back, after Shuffle Armos
    (OW-CAVE-05) has re-pointed its entry. start_rooms: dungeon ->
    LevelInfo_StartRoomId. With B04 off (ZORA's own value) the take-any-road caves stay."""
    fixed = frozenset() if shuffle_take_any_road_caves else frozenset({Destination.ANY_ROAD})
    walk_destination_codes(entries, start_rooms, rng, fixed, gates)
    write_back(overworld, entries)
    return CaveShuffle(entries, armos)
