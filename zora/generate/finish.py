"""FINISH with an assignment (Archipelago Phase 2, External mode; docs/archipelago.md): another
filler's item in each of a built world's places, then everything the ROM shows that depends on
which item sits where, done again for the new placement.

ZORA mode never comes here: pipeline.finish with no assignment serializes the built world as it
is. apply_assignment works on a copy of the built world, and draws only from its own stream
(finish_rng: the generation seed and "finish"), never BUILD's.
"""
from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..model.enums import Destination, DungeonNothingCode, Item, RoomType
from ..model.level_9_gate import TRIFORCE_LEVELS
from ..model.level_items import ALL_LEVEL_ITEM_NAMES, LevelItemKind, level_item, level_of
from ..model.overworld import Shop
from ..rom.game_config import GameConfig
from .level_swaps import NO_SWAPS, LevelSwaps
from .places import Place, PlaceKind, is_never_a_place, item_pool, read_item, write_item
from .rng import IntRng, Rng
from .steps.item_shuffle_result import (
    LETTER_SLOT,
    MAGICAL_SWORD_SLOT,
    WOOD_SWORD_SLOT,
    ItemShuffleResult,
    TrackedPlace,
    shop_ware_slot,
)
from .steps.potion_shop import BLUE_POTION_PRICES
from .steps.shop_prices import REQUIRED_PRICES, grouped_wares, price_groups, price_groups_rng

if TYPE_CHECKING:
    from ..model.game_world import GameWorld
    from .pipeline import Built
    from .steps.extra_pool_items import ExtraPoolItems


class ItemClass(Enum):
    """Another player's item's class, from Archipelago's classification (docs/design/
    archipelago-items.md piece 1): progression if its progression flag is set, else useful if its
    useful flag is set, else filler (a trap is filler)."""
    PROGRESSION = "progression"
    USEFUL = "useful"
    FILLER = "filler"


@dataclass(frozen=True)
class Foreign:
    """Another player's item (Archipelago): this player gets nothing from it. Its class prices a
    shop ware that holds it (FOREIGN_WARE_PRICES)."""
    item_class: ItemClass = ItemClass.FILLER

    def __repr__(self) -> str:
        return "FOREIGN" if self.item_class is ItemClass.FILLER else f"FOREIGN({self.item_class.value})"


FOREIGN = Foreign()                       # filler: what every caller before piece 1 passed

# A shop ware holding another player's item, by its class (decision 9, 2026-11-14): progression as
# a required item (SI-PRICE-01's 60-80), useful and filler 30-40, whatever the item looks like.
FOREIGN_MINOR_PRICES = (30, 40)
FOREIGN_WARE_PRICES = {ItemClass.PROGRESSION: REQUIRED_PRICES, ItemClass.USEFUL: FOREIGN_MINOR_PRICES,
                       ItemClass.FILLER: FOREIGN_MINOR_PRICES}


# The item code another player's item is written as, by its class (decision 4, 2026-11-14;
# docs/design/archipelago-items.md piece 5): the Archipelago logo, colored as the swords are, drawn and
# taken by asm/flags2/ap-items' far routines, which give nothing. Up to piece 5 it looked like a rupee
# ($18) or, with "Other players' items look like" (retired), like the logo in the magical shield's tiles.
FOREIGN_ITEMS = {ItemClass.PROGRESSION: Item.ARCHIPELAGO_PROGRESSION, ItemClass.USEFUL: Item.ARCHIPELAGO_USEFUL,
                 ItemClass.FILLER: Item.ARCHIPELAGO_FILLER}
FOREIGN_CODES = frozenset(item.value for item in FOREIGN_ITEMS.values())

Assignment = Mapping[str, Item | Foreign]

# The finish stream's key: the generation seed, and this label.
FINISH_STREAM = b"zora finish"
SEED_BYTES = 8


class AssignmentUnbeatable(ValueError):
    """The sanity check (R4) failed where it is a hard error: the walk with the received items
    granted (any game), or the strict walk in a solo game."""

    def __init__(self, sanity: Sanity) -> None:
        self.sanity = sanity
        super().__init__(f"assignment fails ZORA's acceptance walk: {sanity}")


class AssignmentRefused(ValueError):
    """An assignment FINISH cannot write, with every reason."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("assignment refused: " + "; ".join(reasons))


def finish_rng(generation_seed: int) -> Rng:
    """FINISH's own stream, keyed by the generation seed and "finish": the player's machine can
    repeat FINISH exactly, and BUILD's stream is never touched."""
    key = hashlib.blake2b(generation_seed.to_bytes(SEED_BYTES, "little"), digest_size=SEED_BYTES,
                          person=FINISH_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def written_item(value: Item | Foreign) -> Item:
    """The item code the ROM gets for an assigned value: another player's item's by its class."""
    return FOREIGN_ITEMS[value.item_class] if isinstance(value, Foreign) else value


def refusals(places: list[Place], assignment: Assignment, pool: frozenset[Item]) -> list[str]:
    """Why the assignment cannot be written: a name that is no place of this build, an item
    outside the build's pool (places.item_pool; FOREIGN aside), or an item the place forbids (R2): at a compass
    spot (Place.compass_spot), another player's filler too."""
    by_name = {place.name: place for place in places}
    reasons = [f"{name}: no such place in this seed" for name in assignment if name not in by_name]
    for name, value in assignment.items():
        place = by_name.get(name)
        if place is None:
            continue
        if isinstance(value, Foreign):
            if place.compass_spot and value.item_class is ItemClass.FILLER:
                reasons.append(f"{name}: another player's filler is forbidden at a compass spot")
            continue
        if value not in pool:
            reasons.append(f"{name}: {value.name} is not in this seed's item pool")
        elif value in place.forbids:
            reasons.append(f"{name}: {value.name} is forbidden there")
    return reasons


def one_time_places(places: list[Place]) -> tuple[tuple[int, int], ...]:
    """GameConfig.one_time_places: each ware place as (shop number, position)."""
    from ..rom.code_patches import SHOPS_BY_NUMBER
    pairs = []
    for place in places:
        if place.is_shop:
            assert place.destination is not None and place.position is not None
            pairs.append((SHOPS_BY_NUMBER.index(place.destination), place.position))
    return tuple(pairs)


def needs_remap(places: list[Place], assignment: Assignment) -> bool:
    """R2: a magical sword ($03) in a dungeon room or cellar reads as "no item" unless ZORA's
    remap is written, which makes $0E the "no item" code there instead."""
    return any(place.is_dungeon and assignment.get(place.name) == Item.MAGICAL_SWORD for place in places)


# --- the tracked items -----------------------------------------------------------------------

# The item shuffle's special-cave slots, by the place's destination (ItemShuffleResult.caves).
CAVE_SLOTS: dict[Destination, str] = {
    Destination.ARMOS_ITEM: "armos",
    Destination.WHITE_SWORD_CAVE: "white_sword",
    Destination.COAST_ITEM: "coast",
    Destination.MAGICAL_SWORD_CAVE: MAGICAL_SWORD_SLOT,
    Destination.LETTER_CAVE: LETTER_SLOT,
    Destination.WOOD_SWORD_CAVE: WOOD_SWORD_SLOT,      # Shuffle Wood Sword
}


def tracked_place(place: Place, item: Item) -> TrackedPlace:
    """VA-REJ-07's record of an item in a place: its level, or its slot."""
    if place.is_dungeon:
        return TrackedPlace(item, level=place.level)
    assert place.destination is not None
    if place.is_shop:
        assert place.position is not None
        return TrackedPlace(item, slot=shop_ware_slot(place.destination, place.position))
    return TrackedPlace(item, slot=CAVE_SLOTS[place.destination])


@dataclass
class Tracking:
    """The tracked items after an assignment: where each sits in this world (`tracked`: a place, or a
    room that is never one), and the tracked items this world does not hold (`elsewhere`: in another
    player's world)."""
    tracked: list[TrackedPlace]
    elsewhere: list[Item]


def rebuild_tracking(world: GameWorld, built: Built) -> Tracking:
    """The item shuffle's tracked records (and the extras') for the assigned world: each tracked
    item as BUILD tracked them, found again among the places in place order (one place per
    record). With Shuffle Blue Potion, the letter is tracked, wherever it is, when a tracked record
    is the potion shop's ware (potion_shop.shuffle_blue_potion's rule)."""
    from .pipeline import extra_options
    assert built.result.item_shuffle_result is not None
    blue_potion = extra_options(built.plan).shuffle_blue_potion
    records = [record for record in built.result.item_shuffle_result.tracked
               if not (blue_potion and record.item == Item.LETTER)]
    holding = [(place, read_item(world, place)) for place in built.places]
    used: set[str] = set()
    # A room that is never a place keeps what BUILD left in it, whatever the assignment: with Shuffle Minor
    # Dungeon Drops a tracked item dealt to an enemy room stays there when the monster re-deal later moves
    # Zelda in (PS-MONRD-02 never looks at items), and the walk collects it where it lies, as BUILD's did
    fixed = [(level.level_num, room) for level in world.levels for room in level.rooms if is_never_a_place(room)]
    fixed_used: set[int] = set()
    tracking = Tracking([], [])

    def track(item: Item, record: TrackedPlace | None = None) -> None:
        """The item's place: the one BUILD's record names if it still holds the item (so an
        unchanged placement keeps BUILD's records), else the first holding it; else a room that is
        never a place and holds it; else it is elsewhere."""
        candidates = [place for place, held in holding if held == item and place.name not in used]
        place = next((place for place in candidates if tracked_place(place, item) == record), None)
        place = place or next(iter(candidates), None)
        if place is None:
            level_num, room = next(((level_num, room) for level_num, room in fixed
                                    if room.item == item and id(room) not in fixed_used), (None, None))
            if room is None:
                tracking.elsewhere.append(item)
            else:
                fixed_used.add(id(room))
                tracking.tracked.append(TrackedPlace(item, level=level_num))
            return
        used.add(place.name)
        tracking.tracked.append(tracked_place(place, item))

    for record in records:
        track(Item(record.item), replace(record, item=Item(record.item)))
    if extra_options(built.plan).add_triforces_to_pool:
        # each level's piece is an item the closure collects (LogicRules.triforces_as_items; piece 6)
        for level in TRIFORCE_LEVELS:
            track(level_item(LevelItemKind.TRIFORCE, level))
    if blue_potion:
        potion = next(place for place in built.places if place.kind == PlaceKind.POTION_SHOP)
        potion_slot = tracked_place(potion, Item.LETTER).slot
        if any(record.slot == potion_slot for record in tracking.tracked):
            if any(held == Item.LETTER for _place, held in holding):
                track(Item.LETTER)
            elif not extra_options(built.plan).randomize_letter:
                tracking.tracked.append(TrackedPlace(Item.LETTER, slot=LETTER_SLOT))    # in its own cave
            else:
                tracking.elsewhere.append(Item.LETTER)
    return tracking


def with_tracking(state: ItemShuffleResult, tracking: Tracking, world: GameWorld,
                  places: list[Place]) -> ItemShuffleResult:
    """A copy of the item shuffle's result with the rebuilt records and the special caves' items."""
    caves = dict(state.caves)
    for place in places:
        if place.destination in CAVE_SLOTS and CAVE_SLOTS[place.destination] in caves:
            caves[CAVE_SLOTS[place.destination]] = int(read_item(world, place))
    return replace(state, tracked=list(tracking.tracked), caves=caves)


# --- prices (SI-PRICE-01, Shuffle Blue Potion) -------------------------------------------------

def _uniform(rng: IntRng, prices: tuple[int, int]) -> int:
    low, high = prices
    return low + rng.below(high - low + 1)


def reprice_wares(world: GameWorld, built: Built, rng: IntRng, groups_rng: IntRng | None = None) -> None:
    """The joined wares' prices for what they now hold, in join order: SI-PRICE-01's classes under
    the seed's own settings (steps/shop_prices.py); a blue potion in a ware other than its own costs
    25-55 (potion_shop.price_potion_wares); a ware holding its own joined item or an unpriced one
    keeps its price from before SI-PRICE-01. Then the groups (revision 2026-11-27) from `groups_rng`, their own
    stream (default: keyed by the plan's generation seed), overwrite the required and optional wares' draws and
    price every ware holding an optional item."""
    from .pipeline import extra_options
    extras = built.result.extra_pool_items
    if extras is None:
        return
    prices = extra_options(built.plan).price_rules.prices
    for ware, own_item, slot_price in zip(extras.shop_wares, extras.shop_items, extras.slot_prices, strict=True):
        shop = world.overworld.get_cave(ware.shop.destination, Shop)
        assert shop is not None
        held = shop.ware(ware.position)
        if held.item == own_item or (held.item not in prices and held.item != Item.BLUE_POTION):
            held.price = slot_price
        elif held.item == Item.BLUE_POTION:
            held.price = _uniform(rng, BLUE_POTION_PRICES)
        else:
            held.price = _uniform(rng, prices[held.item])
    # SI-PRICE-01's groups (revision 2026-11-27), from their own stream: the class draws above stay in FINISH's
    # stream, so the hint text and the foreign wares draw as before
    rules = extra_options(built.plan).price_rules
    price_groups(grouped_wares(world, extras, rules), rules,
                 groups_rng or price_groups_rng(built.plan.generation_seed, b"finish"))


def price_foreign_wares(world: GameWorld, places: Collection[Place], assignment: Assignment, rng: IntRng) -> None:
    """Piece 1 (docs/design/archipelago-items.md): a shop ware holding another player's item costs
    FOREIGN_WARE_PRICES by its class, not the slot's price. Drawn in place order after every other
    draw of FINISH's stream, so the rest of a seed's prices and hint text stay as they were."""
    for place in places:
        value = assignment.get(place.name)
        if not isinstance(value, Foreign) or place.destination is None or place.position is None:
            continue
        shop = world.overworld.get_cave(place.destination, Shop)
        if shop is not None:
            shop.ware(place.position).price = _uniform(rng, FOREIGN_WARE_PRICES[value.item_class])


# --- the hint text --------------------------------------------------------------------------

def hinted_foreign_places(places: Collection[Any], assignment: Mapping[str, object],
                          owners: dict[str, tuple[str, str]]) -> dict[str, int | str]:
    """The other-player places a hint can name, as place name -> key: the player level for a level
    holding exactly one other player's item, "coast" for the Coast and "white sword" for the White
    Sword Cave. "Exactly one" counts every other-player item in the level, nameable or not; only
    then is a place whose owner or item name has no character the font shows left out (the encoder
    drops those, so the hint would read "'S ... AWAITS"), and one whose item is a level's piece, map or compass
    ("Level 3 Triforce", from another ZORA world: no hint is about one). It keeps the generic wording, and so does
    a level holding two other-player items when one of them cannot be named.
    owners: place name -> (owner name, item name)."""
    from .steps.hint_text import has_shown_character
    def is_foreign(place_name: str) -> bool:
        return isinstance(assignment.get(place_name), Foreign)
    def nameable(place_name: str) -> bool:
        # never a hint about a level's piece, map or compass, another ZORA player's ("Level 3 Triforce") too
        return (is_foreign(place_name) and place_name in owners
                and all(has_shown_character(text) for text in owners[place_name])
                and owners[place_name][1] not in ALL_LEVEL_ITEM_NAMES)
    by_level: dict[int, list[str]] = {}
    for place in places:
        if place.level is not None and is_foreign(place.name):
            by_level.setdefault(place.level, []).append(place.name)
    hinted: dict[str, int | str] = {found[0]: level for level, found in by_level.items()
                                    if len(found) == 1 and nameable(found[0])}
    hinted.update({place_name: key for place_name, key in (("Coast", "coast"), ("White Sword Cave", "white sword"))
                   if nameable(place_name)})
    return hinted


def foreign_level_labels(world: GameWorld, places: Collection[Place], assignment: Mapping[str, object],
                         owners: dict[str, tuple[str, str]]) -> tuple[tuple[int | str, str, str], ...]:
    """(level, owner, item) for each place hinted_foreign_places names: a level is given as the
    ROM's level number, the Coast and the White Sword Cave by key."""
    labels: list[tuple[int | str, str, str]] = []
    for place_name, key in hinted_foreign_places(places, assignment, owners).items():
        label: int | str = key
        if isinstance(key, int):
            level = next((lvl for lvl in world.levels if lvl.level_num == key), None)
            if level is None:
                continue
            label = level.rom_level_num
        owner, item = owners[place_name]
        labels.append((label, owner, item.upper()))
    return tuple(labels)


def recompose_hint_text(world: GameWorld, built: Built, item_shuffle_result: ItemShuffleResult, rng: Rng,
                        foreign: bool = False,
                        foreign_labels: tuple[tuple[int | str, str, str], ...] = ()) -> None:
    """The hint text again on the assigned world: the hint text step (compose_hint_text), B19's
    pointer exchange when it ran, and ship_hint_text. foreign: the assignment holds another
    player's item; a hint naming a place that holds one says it is an item for another player
    (owner decision, 2026-10-08), never what the ROM shows there, and never which item it is
    (FOREIGN_CODES are the codes it is written as)."""
    from .generation_pass import compose_hint_text
    from .pipeline import extra_options
    from .ship import ship_hint_text
    from .steps.shuffle_dungeon_text import shuffle_dungeon_text
    result = built.result
    if result.hint_assignment is None:          # no hint text step ran (the shape stage only)
        return
    chosen = built.plan
    hint_text = compose_hint_text(world, item_shuffle_result, result.hint_assignment, rng, extra_options(chosen),
                                  chosen.alternatives, result.maze_offers, FOREIGN_CODES if foreign else frozenset(),
                                  foreign_labels)
    if chosen.steps.shuffle_dungeon_text:
        hint_text = shuffle_dungeon_text(hint_text, rng)
    ship_hint_text(world, hint_text)


# --- the sanity check (R4) --------------------------------------------------------------------

@dataclass(frozen=True)
class Sanity:
    """ZORA's acceptance check (E1, E3, E4, E5) on the assigned world, two ways (owner decision
    2026-10-08). Places holding FOREIGN give this player nothing.
      strict:  this player's items placed in other worlds are unavailable; a hard error only in a
               solo game (no FOREIGN place, nothing received), a diagnostic otherwise, since a
               multiworld player's own world is often meant to be unbeatable alone;
      granted: the items this player receives from other worlds are held from the start; a hard
               error in every game: a failure means ZORA's walk and the logic disagree, or an
               own-world item sits behind something it unlocks.
    Each is the first failing check's label (E1, E3, E4, E5), or None when it passes."""
    solo: bool
    strict: str | None
    granted: str | None

    @property
    def hard_failure(self) -> bool:
        return self.granted is not None or (self.solo and self.strict is not None)


def assigned_extras(world: GameWorld, extras: ExtraPoolItems | None) -> ExtraPoolItems | None:
    """BUILD's extras (ExtraPoolItems: the ZORA extras' caves and joined shop wares) as the assigned world holds
    them. BUILD's own record is staged: its caves' items and its wares' shops are the ones BUILD dealt, which
    FINISH's assignment has since replaced. Offense Item Pacing's heart count reads them."""
    from .steps.extra_pool_items import ShopWarePlace, extra_cave
    if extras is None:
        return None
    wares = []
    for ware in extras.shop_wares:
        shop = world.overworld.get_cave(ware.shop.destination, Shop)
        assert shop is not None
        wares.append(ShopWarePlace(shop, ware.position))
    return replace(extras, caves={slot: extra_cave(world.overworld, slot).item for slot in extras.caves},
                   shop_wares=wares)


def sanity_check(world: GameWorld, built: Built, tracking: Tracking, solo: bool,
                 received: Collection[Item]) -> Sanity:
    """R4's two walks on the assigned world (Sanity), on the logic walk, as Archipelago's rules
    are (docs/archipelago.md "The two walks"): a place the rules let Archipelago fill is one
    these walks collect."""
    from .acceptance_check import acceptance_check, logic_walk_rules
    from .pipeline import extra_options, shipped_logic_rules
    state = built.result.item_shuffle_result
    caves = built.result.overworld
    assert state is not None and caves is not None
    rules = logic_walk_rules(shipped_logic_rules(built.plan, world))
    if extra_options(built.plan).add_triforces_to_pool:
        rules = replace(rules, triforces_as_items=True)   # the pieces are items (archipelago-items piece 6)
    if extra_options(built.plan).per_level_items:
        rules = replace(rules, per_level_codes=True)      # each piece written as its level's own code
    # The walks read the assigned world: its records, its special caves' items (with_tracking) and its extras'
    # caves and wares, which Offense Item Pacing's heart count reads (a heart container FINISH moved there counts)
    assigned = with_tracking(state, tracking, world, built.places)
    extras = assigned_extras(world, built.result.extra_pool_items)
    # strict: an item elsewhere is still to be collected, and no place holds it
    strict_state = replace(assigned, tracked=[*tracking.tracked, *(TrackedPlace(item) for item in tracking.elsewhere)])
    strict = acceptance_check(world.levels, strict_state, world.overworld, caves, rules, extras=extras)
    granted = acceptance_check(world.levels, assigned, world.overworld, caves, rules,
                               granted=frozenset(int(item) for item in received), extras=extras,
                               granted_heart_containers=sum(item == Item.HEART_CONTAINER for item in received))
    return Sanity(solo, strict, granted)


# --- applying an assignment -------------------------------------------------------------------

@dataclass
class Finished:
    """What apply_assignment hands to serialization: the configuration (the remap); and the
    tracked items as the assigned world holds them, and the sanity check's result (R4), for the
    caller."""
    config: GameConfig
    tracking: Tracking
    sanity: Sanity | None = None


GENERIC_LEVEL_ITEMS = frozenset({Item.TRIFORCE, Item.MAP, Item.COMPASS})


def freeze_compass_targets(world: GameWorld) -> None:
    """Per-level mode (docs/design/archipelago-items.md piece 6): the compass marks the level's original Triforce
    room. The serializer finds it by the generic piece (derive_triforce_room_ptr), which write_level_codes rewrites
    as levels 1-7's own codes and the assignment may move, so each level's room is fixed here, from BUILD's world,
    first. Left to the serializer, levels 1-7's compasses pointed at room $00, off the status bar's map."""
    from ..rom.serialize.levels import derive_triforce_room_ptr
    for level in world.levels:
        if level.triforce_room_ptr is None:
            level.triforce_room_ptr = derive_triforce_room_ptr(level)


MARKED_LEVELS = range(1, 9)             # level 9's compass marks Zelda's room, which holds no item


def compass_item_rooms(world: GameWorld) -> tuple[int, ...]:
    """Per-level mode's compass marker (asm/flags2/level-compass), from BUILD's world: for each data level 1-8 the
    room whose item-taken flag the marker follows, so it blinks until the item at the piece's original spot is
    taken, whatever that spot holds after the assignment. The spot is the marked room (freeze_compass_targets:
    derive_triforce_room_ptr), or, where the piece stood in an item cellar, that cellar, under the marked room."""
    from ..rom.serialize.levels import derive_triforce_room_ptr
    rooms = []
    for level_num in MARKED_LEVELS:
        level = next(level for level in world.levels if level.level_num == level_num)
        marked = level.triforce_room_ptr if level.triforce_room_ptr is not None else derive_triforce_room_ptr(level)
        room = next((room for room in level.rooms if room.item == Item.TRIFORCE), None)
        if room is not None:
            assert room.room_num == marked, (level_num, room.room_num, marked)
            rooms.append(room.room_num)
            continue
        cellar = next(stair for stair in level.staircase_rooms        # as derive_triforce_room_ptr finds it
                      if stair.room_type == RoomType.ITEM_STAIRCASE and stair.item == Item.TRIFORCE)
        assert cellar.exit_bytes()[0] == marked, (level_num, cellar.room_num, marked)
        rooms.append(cellar.room_num)
    return tuple(rooms)


def write_level_codes(world: GameWorld, swaps: LevelSwaps = NO_SWAPS) -> None:
    """Per-level mode (docs/design/archipelago-items.md piece 6): the ROM reads the generic piece, map and
    compass as level 8's and level 9's, so each one BUILD left in a level's room or item cellar is written as
    its own level's code, or with Between levels as the code of the level `swaps` drew for that spot
    (level_swaps.py). Run before the assignment is written, so it reaches the rooms that are no place, and a
    generic code the assignment puts in another level stays level 8's or level 9's."""
    def code(item: Item, level_num: int) -> Item:
        found = level_of(item)
        assert found is not None
        return level_item(found[0], swaps.code_in(found[0], level_num))

    for level in world.levels:
        for room in level.rooms:
            if room.item in GENERIC_LEVEL_ITEMS:
                room.item = code(room.item, level.level_num)
        for stair in level.block.staircases:
            if stair.return_dest in level.room_nums and stair.item in GENERIC_LEVEL_ITEMS:
                stair.item = code(stair.item, level.level_num)


def apply_assignment(world: GameWorld, built: Built, assignment: Assignment, rng: Rng, recompute: bool = True,
                     received: Collection[Item] = (), check: bool = True,
                     foreign_owners: dict[str, tuple[str, str]] | None = None,
                     groups_rng: IntRng | None = None) -> Finished:
    """Write the assignment into `world` (a copy of the built world), refusing it whole if any
    part breaks a rule (AssignmentRefused); then redo every output that depends on which item
    sits where (docs/archipelago.md, R3): the tracked items, the joined wares' prices and the hint
    text, drawing from `rng` in that order. The one-time wares and the seed's code follow at
    serialization. recompute=False writes the items and the remap only (tests 2 and 3).

    received: this player's items that other worlds hold (Archipelago gives them). check: run
    the sanity check (R4, Sanity), raising AssignmentUnbeatable on a hard failure; off for tests
    that write arbitrary permutations. Another player's item is written as its class's code
    (FOREIGN_ITEMS). Last, with recompute, the wares holding another player's item are priced by its
    class (price_foreign_wares), after every other draw."""
    from .pipeline import extra_options
    places = built.places
    reasons = refusals(places, assignment, item_pool(extra_options(built.plan)))
    if reasons:
        raise AssignmentRefused(reasons)
    if extra_options(built.plan).per_level_items:
        # first, before the assignment: an assigned generic code is level 8's piece or level 9's map or compass
        # wherever it goes, and must not be rewritten as the level it lands in
        freeze_compass_targets(world)
        write_level_codes(world, extra_options(built.plan).level_swaps)
    for place in places:
        if place.name in assignment:
            write_item(world, place, written_item(assignment[place.name]))
    # every ware place is sold once, whatever it holds, so that buying it is a location check
    config = replace(built.plan.config, one_time_places=one_time_places(places))
    if needs_remap(places, assignment):
        config = replace(config, dungeon_nothing_code=DungeonNothingCode.ZORA_REMAP)
        world.dungeon_nothing_code = DungeonNothingCode.ZORA_REMAP
    tracking = rebuild_tracking(world, built)
    if recompute:
        assert built.result.item_shuffle_result is not None
        item_shuffle_result = with_tracking(built.result.item_shuffle_result, tracking, world, places)
        reprice_wares(world, built, rng, groups_rng)
        recompose_hint_text(world, built, item_shuffle_result, rng,
                            foreign=any(isinstance(value, Foreign) for value in assignment.values()),
                            foreign_labels=foreign_level_labels(world, places, assignment, foreign_owners or {}))
    if recompute:
        price_foreign_wares(world, places, assignment, rng)
    finished = Finished(config, tracking)
    if check:
        solo = not received and not any(isinstance(value, Foreign) for value in assignment.values())
        finished.sanity = sanity_check(world, built, tracking, solo, received)
        if finished.sanity.hard_failure:
            raise AssignmentUnbeatable(finished.sanity)
    return finished
