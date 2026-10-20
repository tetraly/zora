"""Expanded Dungeon Locations (ZORA Extra, version 8; owner and Bogie, 2026-10-18; the private
design expanded-dungeon-locations.md). ZORA's own option, beyond the spec.

The nine dungeons are dealt onto 9 of 15 spots, from the option's own random stream: the nine
first-quest dungeon entrances and the six second-quest entrances on other screens. Spots are named
1Qn / 2Qn by quest and the level number the game shows there; three screens hold a level in both
quests (1Q1/2Q1, 1Q2/2Q3, 1Q4/2Q5). The same rules run under either base quest (BaseQuest), the
2nd Quest's the mirror of the 1st's:

  - A chosen spot shows the version with its entrance and holds its dungeon's code: a secret of the
    other quest is shown (2Q4 to 2Q9 under a 1st Quest overworld, 1Q8 and 1Q9 under a 2nd), a
    chosen recorder spot's entry is live (2Q6 under a 1st Quest overworld turns the recorder's
    second-quest reveal on in the first quest; a chosen 1Q7's entry 0 reveals in either), and a
    chosen 1Q5 under a 2nd Quest overworld keeps its first-quest doorway (no fountain).
  - An unchosen spot that can close stays closed: 1Q5 shows the second quest's fairy fountain, 1Q7
    keeps its lake with the recorder entry off (and 2Q3's pond under a 2nd Quest overworld), and the
    secrets stay hidden.
  - The caves on spots that take a dungeon are displaced, the base quest's own first, then those
    shown only at the unchosen spot (borrowed): SHOP_4 at 2Q2, and SHOP_2 at 1Q3 and MEDIUM_SECRET
    at 1Q6 (the second quest's). Each moves into a vacated open cave, 1Q1/2Q1 or 1Q4/2Q5 first,
    then 1Q2/2Q3 (a 1st Quest overworld only: under a 2nd it is the pond). A leftover displaced cave
    with another entrance is dropped; SHOP_4 under a 1st Quest overworld, whose only entrance is
    2Q2, takes an unchosen 1Q3's or 1Q6's place instead, and with neither the deal is redrawn.
  - A vacated 1Q2/2Q3 with nothing displaced into it closes as the second quest's recorder lake; a
    vacated 1Q1/2Q1 or 1Q4/2Q5 takes a cave that sits at a level location of the other quest
    (under a 1st Quest overworld SHOP_2 at 1Q3's or MEDIUM_SECRET at 1Q6's, under a 2nd SHOP_4 at
    2Q2's). With more such caves left over than those caves, the deal is redrawn (owner ruling,
    2026-10-18: only a 2nd Quest overworld has one such cave, SHOP_4, for two leftovers).

Every closed spot holds no cave code (no stale dungeon code for the door map or E9), and every pool
recorder entry but a chosen spot's is off; under a 1st Quest overworld every other entry is off too,
under a 2nd Quest overworld the second quest's other recorder secrets stay. The Armos item screen
avoids 2Q2 while it holds a dungeon (shuffle_armos).

The mode follows Cave Shuffle. Dungeons Only, "Expanded Brackets": the deal replaces the walk's
dungeon part and nothing else moves. All Caves, "Expanded + shuffle everything else": the walk's
non-dungeon part then runs over the dealt list (deal_entries: closed spots out, chosen secrets of
the other quest in), the wooden-sword cave's partner never a dungeon door (shuffle_caves'
dungeons_dealt)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto

from ...model.enums import Destination, QuestVisibility
from ...model.overworld import Overworld
from ..rng import IntRng, Rng
from .cave_entries import RECORDER_ENTRY_OFF, Entry
from .mixed_overworld_quest import (
    SCREEN_11,
    SCREEN_60_EXIT_ROW,
    SCREEN_60_LAYOUT,
    prepare_second_quest_screen_11,
)


class SpotKind(Enum):
    """What an unchosen spot shows under its base quest."""
    OPEN_CAVE = auto()           # 1Q1/2Q1, 1Q4/2Q5: a doorway with no other version (vacated, tier 1)
    POND_CAVE = auto()           # 1Q2/2Q3 under a 1st Quest overworld: may close as 2Q3's lake (vacated, tier 2)
    CARRIER = auto()             # 1Q3, 1Q6, 2Q2: shows its carried cave
    FOUNTAIN = auto()            # 1Q5: the second quest's fairy fountain
    RECORDER_LAKE = auto()       # 1Q7, and 2Q3 under a 2nd Quest overworld: its lake, the recorder entry off
    HIDDEN = auto()              # the secrets: never shown


@dataclass(frozen=True)
class Spot:
    label: str
    screen: int
    kind: SpotKind
    carried: Destination | None = None       # a CARRIER's cave
    other_quest_secret: bool = False         # a secret the base quest hides: shown once chosen
    recorder_entry: int | None = None        # its FluteRoomSecretsOW entry, for a recorder spot


@dataclass(frozen=True)
class BaseQuest:
    """The rules' data under one base quest (Overworld Quest: 1st Quest or 2nd Quest)."""
    name: str
    spots: tuple[Spot, ...]
    carriers: tuple[str, ...]                # the displaced caves' placing order (own, then borrowed)
    vacated_tiers: tuple[tuple[str, ...], tuple[str, ...]]   # tier 1, then tier 2 (may close)
    # A vacated tier-1 cave with nothing displaced into it: a cave the other quest shows at a level
    # location of this one (owner and Bogie, 2026-10-18)
    opposite_quest_caves: tuple[Destination, ...]
    sole_entrance_caves: frozenset[Destination]   # never dropped: they would leave the game
    second_quest: bool                       # the recorder's second-quest secrets stay live

    @property
    def by_label(self) -> dict[str, Spot]:
        return {spot.label: spot for spot in self.spots}

    def spot(self, label: str) -> Spot:
        return self.by_label[label]


FIRST_QUEST = BaseQuest(
    "1st Quest",
    spots=(
        Spot("1Q1/2Q1", 0x37, SpotKind.OPEN_CAVE),
        Spot("1Q2/2Q3", 0x3C, SpotKind.POND_CAVE),
        Spot("1Q3", 0x74, SpotKind.CARRIER, carried=Destination.SHOP_2),
        Spot("1Q4/2Q5", 0x45, SpotKind.OPEN_CAVE),
        Spot("1Q5", 0x0B, SpotKind.FOUNTAIN),
        Spot("1Q6", 0x22, SpotKind.CARRIER, carried=Destination.MEDIUM_SECRET),
        Spot("1Q7", 0x42, SpotKind.RECORDER_LAKE, recorder_entry=0),
        Spot("1Q8", 0x6D, SpotKind.HIDDEN),
        Spot("1Q9", 0x05, SpotKind.HIDDEN),
        Spot("2Q2", 0x34, SpotKind.CARRIER, carried=Destination.SHOP_4),
        Spot("2Q4", 0x1B, SpotKind.HIDDEN, other_quest_secret=True),
        Spot("2Q6", 0x30, SpotKind.HIDDEN, other_quest_secret=True, recorder_entry=4),
        Spot("2Q7", 0x6C, SpotKind.HIDDEN, other_quest_secret=True),
        Spot("2Q8", 0x19, SpotKind.HIDDEN, other_quest_secret=True),
        Spot("2Q9", 0x00, SpotKind.HIDDEN, other_quest_secret=True),
    ),
    # SHOP_4 (own; 2Q2 is its only first-quest entrance), then the borrowed SHOP_2 and MEDIUM_SECRET
    carriers=("2Q2", "1Q3", "1Q6"),
    vacated_tiers=(("1Q1/2Q1", "1Q4/2Q5"), ("1Q2/2Q3",)),
    opposite_quest_caves=(Destination.SHOP_2, Destination.MEDIUM_SECRET),
    sole_entrance_caves=frozenset({Destination.SHOP_4}),
    second_quest=False,
)

# The mirror under a 2nd Quest overworld (phase 2, 2026-10-18). Its own caves on pool spots are SHOP_2
# at 1Q3 ($74, one of six entrances) and MEDIUM_SECRET at 1Q6 ($22, one of seven); SHOP_4 at 2Q2 is
# borrowed (the second quest's is on $0F), so no displaced cave lacks another entrance. 1Q2/2Q3 is
# 2Q3's recorder pond, so only 1Q1/2Q1 and 1Q4/2Q5 are vacated, and the one first-quest cave at a
# second-quest level location is SHOP_4 (2Q2's).
SECOND_QUEST = BaseQuest(
    "2nd Quest",
    spots=(
        Spot("1Q1/2Q1", 0x37, SpotKind.OPEN_CAVE),
        Spot("1Q2/2Q3", 0x3C, SpotKind.RECORDER_LAKE, recorder_entry=6),
        Spot("1Q3", 0x74, SpotKind.CARRIER, carried=Destination.SHOP_2),
        Spot("1Q4/2Q5", 0x45, SpotKind.OPEN_CAVE),
        Spot("1Q5", 0x0B, SpotKind.FOUNTAIN),
        Spot("1Q6", 0x22, SpotKind.CARRIER, carried=Destination.MEDIUM_SECRET),
        Spot("1Q7", 0x42, SpotKind.RECORDER_LAKE, recorder_entry=0),
        Spot("1Q8", 0x6D, SpotKind.HIDDEN, other_quest_secret=True),
        Spot("1Q9", 0x05, SpotKind.HIDDEN, other_quest_secret=True),
        Spot("2Q2", 0x34, SpotKind.CARRIER, carried=Destination.SHOP_4),
        Spot("2Q4", 0x1B, SpotKind.HIDDEN),
        Spot("2Q6", 0x30, SpotKind.HIDDEN, recorder_entry=4),
        Spot("2Q7", 0x6C, SpotKind.HIDDEN),
        Spot("2Q8", 0x19, SpotKind.HIDDEN),
        Spot("2Q9", 0x00, SpotKind.HIDDEN),
    ),
    carriers=("1Q3", "1Q6", "2Q2"),
    vacated_tiers=(("1Q1/2Q1", "1Q4/2Q5"), ()),
    opposite_quest_caves=(Destination.SHOP_4,),
    sole_entrance_caves=frozenset(),
    second_quest=True,
)

# The spots under a 1st Quest overworld (labels and screens are the same under either base)
SPOTS = FIRST_QUEST.spots
SPOTS_BY_LABEL = FIRST_QUEST.by_label
POOL_SCREENS = frozenset(spot.screen for spot in SPOTS)
DUNGEONS = range(1, 10)
CHOSEN_SPOTS = len(DUNGEONS)
# 2Q2's screen, an Armos screen: the Armos item's screen avoids it while it holds a dungeon
ARMOS_SPOT_SCREEN = SPOTS_BY_LABEL["2Q2"].screen
# The fairy fountain's look is OW-QST-04 step 3's (prepare_second_quest_screen_11)
FOUNTAIN_SCREEN = SPOTS_BY_LABEL["1Q5"].screen
assert FOUNTAIN_SCREEN == SCREEN_11
assert [(spot.label, spot.screen) for spot in SECOND_QUEST.spots] == [(spot.label, spot.screen) for spot in SPOTS]

EXPANDED_STREAM = b"zora expanded dl"       # 16 bytes at most (BLAKE2b's person)
SEED_BYTES = 8
KEY_SEPARATOR = " "


def expanded_dungeon_locations_seed(seed: int, z1r_canonical: str, zora_canonical: str) -> int:
    """The key of the option's own random stream: derived only from the seed number and both
    canonical strings, so its draws move nothing in the generation's stream."""
    message = KEY_SEPARATOR.join((str(seed), z1r_canonical, zora_canonical)).encode("utf-8")
    digest = hashlib.blake2b(message, digest_size=SEED_BYTES, person=EXPANDED_STREAM).digest()
    return int.from_bytes(digest, "little")


@dataclass
class ExpandedDeal:
    """The deal: each dungeon's spot, what each unchosen open or carrier spot holds, the spots that
    close, the displaced caves dropped, and how often the deal was drawn again."""
    dungeons: dict[int, Spot]                               # dungeon -> its spot
    base: BaseQuest = FIRST_QUEST
    contents: dict[int, Destination] = field(default_factory=dict)   # unchosen screen -> its cave
    closed_ponds: list[Spot] = field(default_factory=list)  # 1Q2/2Q3 closed as the lake
    dropped: list[Destination] = field(default_factory=list)
    redraws: int = 0             # deals drawn again: SHOP_4 found no home
    ban_redraws: int = 0         # deals drawn again: the start-room ban left a dungeon no spot
    leftover_redraws: int = 0    # deals drawn again: more leftover open caves than opposite-quest caves
    too_many_leftovers: bool = False

    @property
    def chosen(self) -> frozenset[str]:
        return frozenset(spot.label for spot in self.dungeons.values())

    def is_chosen(self, spot: Spot) -> bool:
        return spot.label in self.chosen

    @property
    def door_screens(self) -> dict[int, int]:
        return {dungeon: spot.screen for dungeon, spot in self.dungeons.items()}


def choose_spots(rng: IntRng, base: BaseQuest = FIRST_QUEST) -> list[Spot]:
    """Nine of the 15 spots, each nine-set equally likely: a partial Fisher-Yates shuffle."""
    spots = list(base.spots)
    for index in range(CHOSEN_SPOTS):
        other = index + rng.below(len(spots) - index)
        spots[index], spots[other] = spots[other], spots[index]
    return spots[:CHOSEN_SPOTS]


def deal_dungeons(chosen: list[Spot], start_rooms: dict[int, int], rng: IntRng) -> dict[int, Spot] | None:
    """Dungeons 1 to 9 dealt onto the chosen spots in turn, each drawn uniformly from those left; a
    spot on the dungeon's own start-room screen is refused and drawn again (the start-room ban,
    OW-CAVE-03). None when a dungeon has only refused spots left."""
    free = list(chosen)
    dealt: dict[int, Spot] = {}
    for dungeon in DUNGEONS:
        allowed = [spot for spot in free if spot.screen != start_rooms.get(dungeon)]
        if not allowed:
            return None
        while True:
            spot = free[rng.below(len(free))]
            if spot.screen != start_rooms.get(dungeon):
                break
        free.remove(spot)
        dealt[dungeon] = spot
    return dealt


def place_displaced_caves(deal: ExpandedDeal, rng: IntRng) -> bool:
    """The content-swap rule; False when the deal must be drawn again: a cave with no other entrance
    (SHOP_4 under a 1st Quest overworld) found no home, or more open caves are left over than there
    are opposite-quest caves for them (too_many_leftovers)."""
    base = deal.base
    tiers = [[base.spot(label) for label in tier if label not in deal.chosen] for tier in base.vacated_tiers]
    carriers = [base.spot(label) for label in base.carriers]
    for carrier in carriers:
        if not deal.is_chosen(carrier):
            continue
        assert carrier.carried is not None
        free = next((tier for tier in tiers if tier), None)
        if free is not None:
            deal.contents[free.pop(rng.below(len(free))).screen] = carrier.carried
        elif carrier.carried in base.sole_entrance_caves:
            homes = [spot for spot in carriers
                     if spot.carried not in base.sole_entrance_caves and not deal.is_chosen(spot)]
            if not homes:
                return False
            home = homes[rng.below(len(homes))]
            assert home.carried is not None
            deal.dropped.append(home.carried)
            deal.contents[home.screen] = carrier.carried
        else:
            deal.dropped.append(carrier.carried)
    tier_1, tier_2 = tiers
    # !!! Owner ruling, 2026-10-18 (phase 2): each leftover open cave takes a different opposite-quest
    # cave. Under a 2nd Quest overworld there is only one (SHOP_4), so a deal leaving both 1Q1/2Q1 and
    # 1Q4/2Q5 with nothing displaced (1Q3, 1Q6 and 2Q2 all unchosen: 10 of 5,005 nine-sets) is drawn
    # again, rather than giving SHOP_4 a third and fourth entrance. A 1st Quest overworld has two such
    # caves, so it never redraws here.
    if len(tier_1) > len(base.opposite_quest_caves):
        deal.too_many_leftovers = True
        return False
    deal.closed_ponds = list(tier_2)
    caves = list(base.opposite_quest_caves)
    for spot in tier_1:
        deal.contents[spot.screen] = caves.pop(rng.below(len(caves)))
    return True


def deal_expanded_dungeon_locations(key: int, start_rooms: dict[int, int],
                                    base: BaseQuest = FIRST_QUEST) -> ExpandedDeal:
    """The whole deal from the option's own stream (expanded_dungeon_locations_seed), drawn again
    until every displaced cave that needs one has a home, every leftover open cave a cave, and every
    dungeon a spot the start-room ban allows."""
    rng = Rng(key)
    redraws = ban_redraws = leftover_redraws = 0
    while True:
        dungeons = deal_dungeons(choose_spots(rng, base), start_rooms, rng)
        if dungeons is None:
            ban_redraws += 1
            continue
        deal = ExpandedDeal(dungeons, base, redraws=redraws, ban_redraws=ban_redraws,
                            leftover_redraws=leftover_redraws)
        if place_displaced_caves(deal, rng):
            return deal
        if deal.too_many_leftovers:
            leftover_redraws += 1
        else:
            redraws += 1


def close_pond(overworld: Overworld, screen: int) -> None:
    """1Q2/2Q3 as the second quest's recorder lake (OW-MIX-04 step 3's screen-60 bytes), its
    recorder entry off: no cave."""
    pond = overworld.screens[screen]
    pond.screen_code = SCREEN_60_LAYOUT
    pond.exit_y_position = SCREEN_60_EXIT_ROW
    pond.enemies_from_sides = False
    pond.stairs_position_code = 0
    pond.quest_visibility = QuestVisibility.BOTH_QUESTS
    pond.destination = Destination.NONE


def restore_first_quest_screen_11(overworld: Overworld, first_quest: Overworld) -> None:
    """A chosen 1Q5 under a 2nd Quest overworld: screen 11's first-quest doorway (layout $0A) and
    monster bytes, undoing OW-QST-04 step 3's fountain (prepare_second_quest_screen_11)."""
    screen, kept = overworld.screens[SCREEN_11], first_quest.screens[SCREEN_11]
    screen.screen_code = kept.screen_code
    screen.enemy_spec = kept.enemy_spec
    screen.enemy_quantity = kept.enemy_quantity


def apply_deal(overworld: Overworld, deal: ExpandedDeal, first_quest: Overworld | None = None) -> None:
    """Each spot's look and cave code, and the recorder entries, on the staged overworld. Runs
    before the overworld monster pass, which then leaves the fountain's monster byte (as under
    2nd Quest, OW-QST-04 step 3). Under a 2nd Quest overworld it runs after the second quest's own
    looks and codes (mixed_overworld_quest.show_second_quest_overworld), and first_quest gives a
    chosen 1Q5 its first-quest bytes back."""
    base = deal.base
    spot_of = {spot.label: dungeon for dungeon, spot in deal.dungeons.items()}
    closed_ponds = {spot.screen for spot in deal.closed_ponds}
    for spot in base.spots:
        screen = overworld.screens[spot.screen]
        if spot.label in spot_of:
            screen.destination = Destination(spot_of[spot.label])
            if spot.other_quest_secret:
                screen.quest_visibility = QuestVisibility.BOTH_QUESTS
            if spot.kind is SpotKind.FOUNTAIN and base.second_quest:
                assert first_quest is not None
                restore_first_quest_screen_11(overworld, first_quest)
        elif spot.screen in deal.contents:
            screen.destination = deal.contents[spot.screen]
        elif spot.screen in closed_ponds:
            close_pond(overworld, spot.screen)
        elif spot.kind is SpotKind.CARRIER:
            assert spot.carried is not None
            screen.destination = spot.carried
        elif spot.kind is SpotKind.FOUNTAIN:
            prepare_second_quest_screen_11(overworld)
            screen.destination = Destination.NONE
        elif spot.kind is SpotKind.RECORDER_LAKE:
            screen.destination = Destination.NONE
        else:
            assert spot.kind is SpotKind.HIDDEN, spot
            screen.quest_visibility = QuestVisibility.NEITHER_QUEST
            screen.destination = Destination.NONE
    # A pool spot's entry is live only while the spot is chosen; the other entries are the second
    # quest's secrets, kept under a 2nd Quest overworld and off under a 1st
    entry_spots = {spot.recorder_entry: spot for spot in base.spots if spot.recorder_entry is not None}
    overworld.recorder_secret_screens = [
        (entry_spots[entry].screen if entry_spots[entry].label in spot_of else RECORDER_ENTRY_OFF)
        if entry in entry_spots else (screen if base.second_quest else RECORDER_ENTRY_OFF)
        for entry, screen in enumerate(overworld.recorder_secret_screens)]
    # a chosen 2Q6 needs the second quest's reveal in the first quest (OW-MIX-04's branch, $D0),
    # which a 2nd Quest overworld always has
    overworld.recorder_reveals_listed_secrets_in_first_quest = base.second_quest or "2Q6" in spot_of


def deal_entries(overworld: Overworld, entries: list[Entry]) -> list[Entry]:
    """The cave list under the deal: a closed spot is no entrance and leaves it; a chosen spot not
    in the base quest's list (a secret of the other quest, and 1Q5 and 1Q7 under a 2nd Quest
    overworld) joins it before the wooden-sword entry (last)."""
    kept = [entry for entry in entries
            if not (entry.screen in POOL_SCREENS and overworld.screens[entry.screen].destination == Destination.NONE)]
    listed = {entry.screen for entry in kept}
    joining = [Entry(spot.screen, overworld.screens[spot.screen].destination,
                     overworld.screens[spot.screen].inner_palette)
               for spot in SPOTS if spot.screen not in listed and overworld.screens[spot.screen].destination.is_level]
    *listed_entries, wood_sword = kept
    return [*listed_entries, *joining, wood_sword]
