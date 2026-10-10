"""The overworld's figures (overworld-behavior.md) and the start screen's."""

import statistics
from collections import Counter
from typing import Any, TypeVar

from zora.model.enums import Destination, Item, QuestVisibility
from zora.model.game_world import GameWorld
from zora.model.overworld import DoorRepairCave, ItemCave, SecretCave, Shop, TakeAnyCave
from zora_measure.checkpoints.groups_and_palettes import _vanilla
from zora_measure.checkpoints.overworld_monsters_and_hp import _ow_pair
from zora_measure.checkpoints.summaries import Component, Summary

# --- the registry --------------------------------------------------------------------

# --- Overworld (overworld-behavior.md) ----------------------------------------------

SPEC_OW = "overworld-behavior.md @ c2d0322"
DOOR_COUNTS = (1, 1, 1, 1, 2, 2, 2, 2, 2)              # OW-ENTR-02, dungeons 1-9
ARMOS_FIRST_SCREENS = (36, 28, 52, 61, 78)              # OW-CAVE-05 step 2
SHOP_DESTINATIONS = (Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3,
                     Destination.SHOP_4)
SECRET_DESTINATIONS = (Destination.MEDIUM_SECRET, Destination.LARGE_SECRET,
                       Destination.SMALL_SECRET)


def _codes(gw: GameWorld) -> list[int]:
    return [int(screen.destination) for screen in gw.overworld.screens]


def _screens_with(gw: GameWorld, code: int) -> list[int]:
    return [s for s, c in enumerate(_codes(gw)) if c == code]


def _armos_screen(gw: GameWorld) -> int:
    return gw.overworld.armos_screen_ids[0]


def _list_order(gw: GameWorld) -> list[int]:
    """OW-APP-A1's screens, the armos screen re-pointed to 36 (OW-CAVE-05)."""
    from zora.generate.steps.cave_entries import ENROLLED_SCREENS
    from zora.generate.steps.shuffle_armos import ARMOS_SCREEN
    armos = _armos_screen(gw)
    return [ARMOS_SCREEN if s == armos else s for s in ENROLLED_SCREENS]


def _entry_door(gw: GameWorld, dungeon: int) -> int | None:
    from zora.generate.steps.cave_entries import FIXED_DUNGEON_DOORS
    doors = [s for s in _screens_with(gw, dungeon) if s != FIXED_DUNGEON_DOORS.get(dungeon)]
    return doors[0] if len(doors) == 1 else None


def door_counts_match(gw: GameWorld) -> bool:
    return tuple(len(_screens_with(gw, d)) for d in range(1, 10)) == DOOR_COUNTS


def sword_and_any_road_counts(gw: GameWorld) -> bool:
    return (len(_screens_with(gw, Destination.WOOD_SWORD_CAVE)) == 1
            and len(_screens_with(gw, Destination.ANY_ROAD)) == 4)


def any_road_array(gw: GameWorld) -> dict[str, bool]:
    """OW-CAVE-04: the shortcut array holds the code-20 screens in list
    order; and whether that order happens to be ascending."""
    screens = _screens_with(gw, Destination.ANY_ROAD)
    order = _list_order(gw)
    in_list_order = sorted(screens, key=lambda s: order.index(s) if s in order else len(order))
    array = list(gw.overworld.any_road_screens)
    return {"list order": array == in_list_order, "ascending": array == sorted(array)}


def any_road_position_index(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """OW-CAVE-04: non-bracelet code-20 screens carry V; bracelet-set ones
    keep PRG0's LevelBlockAttrsF fields."""
    from zora.generate.steps.cave_entries import BRACELET_SCREENS, SHORTCUT_POSITION_INDEX
    base = _vanilla().overworld.screens
    screens = gw.overworld.screens
    plain = [s for s in _screens_with(gw, Destination.ANY_ROAD) if s not in BRACELET_SCREENS]
    bracelet = [s for s in _screens_with(gw, Destination.ANY_ROAD) if s in BRACELET_SCREENS]

    def f_fields(screen: Any) -> tuple[Any, ...]:
        return (screen.quest_visibility, screen.stairs_position_code, screen.enemies_from_sides,
                screen.exit_y_position)
    return {"V": (sum(screens[s].stairs_position_code == SHORTCUT_POSITION_INDEX[s] for s in plain),
                  len(plain)),
            "bracelet kept": (sum(f_fields(screens[s]) == f_fields(base[s]) for s in bracelet),
                              len(bracelet))}


def unenrolled_screens_kept(gw: GameWorld) -> bool:
    """OW-CAVE-02: every screen outside OW-APP-A1, other than 36, keeps its
    PRG0 cave byte (code and inner palette)."""
    from zora.generate.steps.cave_entries import ENROLLED_SCREENS
    from zora.generate.steps.shuffle_armos import ARMOS_SCREEN
    base = _vanilla().overworld.screens
    return all((screen.destination, screen.inner_palette) == (base[s].destination, base[s].inner_palette)
               for s, screen in enumerate(gw.overworld.screens)
               if s not in ENROLLED_SCREENS and s != ARMOS_SCREEN)


def destinations_changed(gw: GameWorld) -> int:
    base = _codes(_vanilla())
    return sum(a != b for a, b in zip(_codes(gw), base, strict=True))


def entries_keeping_code(gw: GameWorld) -> int:
    """Entries whose final code is the PRG0 code they started with."""
    from zora.generate.steps.cave_entries import ENROLLED_SCREENS
    base, codes = _codes(_vanilla()), _codes(gw)
    return sum(codes[final] == base[start] for start, final in zip(ENROLLED_SCREENS, _list_order(gw), strict=True))


def start_room_ban(gw: GameWorld) -> tuple[int, int]:
    """OW-CAVE-03: dungeons with no door on S(d)."""
    codes = _codes(gw)
    return sum(codes[level.entrance_room] != level.level_num for level in gw.levels), len(gw.levels)


def dungeons_on_prg0_door(gw: GameWorld) -> dict[str, bool]:
    base, codes = _codes(_vanilla()), _codes(gw)
    return {f"D{d}": codes[base.index(d)] == d for d in range(1, 5)}


def wood_sword_screen(gw: GameWorld) -> dict[str, bool]:
    from zora.generate.steps.cave_entries import WOOD_SWORD_SCREENS
    screens = _screens_with(gw, Destination.WOOD_SWORD_CAVE)
    return {"on OW-APP-A3": all(s in WOOD_SWORD_SCREENS for s in screens), "on 119": screens == [119]}


def armos_first_screen(gw: GameWorld) -> int:
    return _armos_screen(gw)


def armos_tables(gw: GameWorld) -> dict[str, bool]:
    from zora.generate.steps.shuffle_armos import ARMOS_FORMATION
    lists = dict(ARMOS_FORMATION)
    ow = gw.overworld
    screen36 = ow.screens[36]
    return {"permutation, Xs listed": sorted(ow.armos_screen_ids) == sorted(lists)
            and all(x in lists[s] for s, x in zip(ow.armos_screen_ids, ow.armos_positions, strict=True)),
            "A[36] = $43": (screen36.exit_x_position, screen36.has_zola, screen36.has_ocean_sound,
                            screen36.outer_palette) == (4, False, False, 3)}


def neither_quest_bytes(gw: GameWorld) -> dict[str, bool]:
    """OW-CAVE-05 step 4: one F byte with both high bits, at A; none when A = 36."""
    flagged = [s for s, screen in enumerate(gw.overworld.screens)
               if screen.quest_visibility == QuestVisibility.NEITHER_QUEST]
    return {"one, at A": flagged == [_armos_screen(gw)], "none": not flagged}


def vacated_screen_kept(gw: GameWorld) -> tuple[int, int]:
    armos = _armos_screen(gw)
    if armos == 36:
        return 0, 0
    base = _vanilla().overworld.screens[armos]
    screen = gw.overworld.screens[armos]
    return int((screen.destination, screen.inner_palette) == (base.destination, base.inner_palette)), 1


def code_screen_counts(gw: GameWorld) -> dict[str, bool]:
    count = Counter(_codes(gw))
    return {"code 0: 35": count[0] == 35, "code 0: 36": count[0] == 36, "21: 2": count[21] == 2,
            "32: 2": count[32] == 2, "33: 9": count[33] == 9, "35: 7": count[35] == 7}


def screen36_f(gw: GameWorld) -> dict[str, bool]:
    screen = gw.overworld.screens[36]
    fields = (screen.quest_visibility, screen.stairs_position_code, screen.enemies_from_sides,
              screen.exit_y_position)
    return {"$03": fields == (QuestVisibility.BOTH_QUESTS, 0, False, 3),
            "$23": fields == (QuestVisibility.BOTH_QUESTS, 2, False, 3)}


def recorder_follows_doors(gw: GameWorld) -> bool:
    from zora.generate.steps.recorder_to_new_dungeons import recorder_bytes
    ow = gw.overworld
    for d in range(1, 9):
        door = _entry_door(gw, d)
        if door is None or recorder_bytes(door) != (ow.recorder_warp_destinations[d - 1],
                                                    ow.recorder_warp_y_coordinates[d - 1]):
            return False
    return True


def recorder_distinct_screens(gw: GameWorld) -> int:
    return len(set(gw.overworld.recorder_warp_destinations))


CaveT = TypeVar("CaveT")


def _cave(gw: GameWorld, destination: Destination, kind: type[CaveT]) -> CaveT:
    """The cave at a destination, as the class that holds what is read from it."""
    cave = gw.overworld.get_cave(destination, kind)
    assert cave is not None, f"{destination.name}: no {kind.__name__}"
    return cave


def _shop_wares(gw: GameWorld) -> list[list[Any]]:
    return [list(_cave(gw, d, Shop).items) for d in SHOP_DESTINATIONS]


def shop_stock(gw: GameWorld) -> dict[str, bool]:
    def multiset(world: GameWorld) -> list[int]:
        return sorted(int(w.item) for wares in _shop_wares(world) for w in wares)
    shops = _shop_wares(gw)
    return {"multiset": multiset(gw) == multiset(_vanilla()),
            "distinct": all(len({w.item for w in wares}) == len(wares) for wares in shops)}


def shop_prices(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """OW-SHOP-03: prices within 20 of a PRG0 price of the item, in 1-254;
    the ring kept at 250 and the heart at 10 (the undo)."""
    base: dict[Item, set[int]] = {}
    for wares in _shop_wares(_vanilla()):
        for ware in wares:
            base.setdefault(ware.item, set()).add(ware.price)
    wares = [w for shop in _shop_wares(gw) for w in shop]
    rings = [w for w in wares if w.item == Item.BLUE_RING]
    hearts = [w for w in wares if w.item == Item.SINGLE_HEART]
    return {"in range": (sum(1 <= w.price <= 254 and any(abs(w.price - p) <= 20 for p in base[w.item])
                             for w in wares), len(wares)),
            "ring 250": (sum(w.price == 250 for w in rings), len(rings)),
            "heart 10": (sum(w.price == 10 for w in hearts), len(hearts))}


def extra_prices(gw: GameWorld) -> dict[str, float]:
    """OW-SHOP-04's six bytes, in the spec's order."""
    potion = _cave(gw, Destination.POTION_SHOP, Shop).items
    values = [potion[0].price, potion[1].price]
    values += [_cave(gw, d, SecretCave).rupee_value for d in SECRET_DESTINATIONS]
    values.append(_cave(gw, Destination.DOOR_REPAIR, DoorRepairCave).cost)
    names = ("0x1866A", "0x1866C", "0x18680", "0x18683", "0x18686", "0x048A0")
    return {name: float(value) for name, value in zip(names, values, strict=True)}


EXTRA_PRICE_RANGES = ((25, 55), (48, 88), (25, 40), (50, 150), (1, 20), (15, 25))


def extra_prices_in_range(gw: GameWorld) -> bool:
    return all(low <= value <= high for value, (low, high)
               in zip(extra_prices(gw).values(), EXTRA_PRICE_RANGES, strict=True))


EXTRA_PRICE_SUMMARY = Summary(
    lambda values: " ".join(f"{statistics.mean(v[k] for v in values):.1f}" for k in values[0]),
    dict
)


def extra_candles(gw: GameWorld) -> bool:
    return bool(_cave(gw, Destination.WOOD_SWORD_CAVE, ItemCave).maybe_extra_candle == Item.BLUE_CANDLE
                and _cave(gw, Destination.TAKE_ANY, TakeAnyCave).items[1] == Item.BLUE_CANDLE)


def shop_front_doors(gw: GameWorld) -> dict[str, bool]:
    """OW-SHOP-06 on the finished ROM: the guarantees, with movable
    entrances taken as the shop codes' screens in the enrolled list (the
    vacated armos screen and the fixed screens excluded)."""
    from zora.generate.steps.shuffle_shop_items import ARROW_DOOR_BARRED, CANDLE_DOOR_BARRED
    order = set(_list_order(gw))
    codes = _codes(gw)
    ok = True
    for item, barred in ((Item.BLUE_CANDLE, CANDLE_DOOR_BARRED), (Item.WOOD_ARROWS, ARROW_DOOR_BARRED)):
        seller = next(d for d, wares in zip(SHOP_DESTINATIONS, _shop_wares(gw), strict=True)
                      if any(w.item == item for w in wares))
        doors = [s for s in order if codes[s] == seller]
        ok = ok and any(s not in barred for s in doors)
    count = Counter(codes)
    return {"guarantees": ok, "29-31: 4 each": all(count[c] == 4 for c in (29, 30, 31)),
            "32: 2": count[32] == 2}


# --- OW-START-01: the start screen ---------------------------------------------

START_Y_VALUES = (0x8D, 0x7D, 0x5D, 0xAD)       # w(S) = 8, 7, 5, 10
NEVER_START_MONSTER_BYTES = frozenset({0x21, 0x2F})   # PS-OWM-03: no S had these in PRG0


def start_screen_rules(gw: GameWorld) -> dict[str, bool]:
    """OW-START-01: S in the list; S = 119; S carries a cave, a dungeon
    door, code 16; S's PRG0 monster byte was $21 or $2F (never, per
    PS-OWM-03)."""
    from zora.generate.steps.cave_entries import DUNGEONS
    from zora.generate.steps.shuffle_start_screen import PRG0_START_SCREEN, START_SCREENS
    overworld = gw.overworld
    start = overworld.start_screen
    destination = overworld.screens[start].destination
    return {"in list": start in START_SCREENS,
            "S = 119": start == PRG0_START_SCREEN,
            "cave": destination != Destination.NONE,
            "dungeon door": destination.value in DUNGEONS,
            "code 16": destination == Destination.WOOD_SWORD_CAVE,
            "PRG0 $21/$2F": _ow_pair(_vanilla(), start)[0] in NEVER_START_MONSTER_BYTES}


def start_y_value(gw: GameWorld) -> int:
    """OW-START-01 step 2: Link's start Y as the formula gives it from S.
    Finished corpus ROMs keep PRG0's $8D in LevelInfo_StartY, so that byte
    is not a measure of the formula; ZORA's byte is checked against the
    formula in tests/test_overworld.py."""
    from zora.generate.steps.shuffle_start_screen import start_y
    return start_y(gw.overworld.start_screen)


def start_screen(gw: GameWorld) -> int:
    return gw.overworld.start_screen


def _start_screen_spread(values: list[int]) -> str:
    """Least and most frequent of the 51 screens, and chi-square against uniform."""
    from zora.generate.steps.shuffle_start_screen import START_SCREENS
    counts = Counter(values)
    expected = len(values) / len(START_SCREENS)
    chi_square = sum((counts[s] - expected) ** 2 / expected for s in START_SCREENS)
    return (f"{min(counts[s] for s in START_SCREENS)}-{max(counts[s] for s in START_SCREENS)} each; "
            f"119 in {counts[119]}; chi-square {chi_square:.1f} on {len(START_SCREENS) - 1} df")


def _start_screen_shares(value: int) -> dict[str, Component]:
    from zora.generate.steps.shuffle_start_screen import START_SCREENS
    return {str(s): float(value == s) for s in sorted(START_SCREENS)}


START_SCREEN_SPREAD = Summary(_start_screen_spread, _start_screen_shares)
