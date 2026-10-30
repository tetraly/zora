"""BogieSmalls' additions as ZORA extras (features-behavior.md FP-SWAP-01 to FP-SWAP-05 and FP-SWL-01
to FP-SWL-05, acceptance.md VA-REJ-23; docs/zora-extras.md section 23): the flag string, the refusals, the swap
on the same placement (same seed and plan, the swap's switch alone turned off: the swap draws nothing), the
starting-item pairs, the pins, Random, the walk's piece count (each level once) and the ROM bytes, and
existing settings' ROMs unchanged by the additions."""
from collections import Counter
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_coop_reserved import z1r_with
from zora.flags import zora_flags
from zora.flags.fields import ThreeState, WoodenSwordState
from zora.flags.zora_flags import Swordlish, ZoraFlags
from zora.generate import generation_pass, pipeline
from zora.generate.acceptance_check import TRIFORCE_LEVEL_SET, AcceptanceCheck, LogicRules
from zora.generate.pipeline import Built, FlagsRefused, build, extra_options, plan
from zora.generate.steps.extra_pool_items import dungeon_places
from zora.generate.steps.swap_swords_and_rings import SWAPPED_PAIRS
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, OverworldItem, Shop
from zora.rom import swordlish
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize import game_world as serialize_game_world
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = needs_base_rom

SWAP = zora_flags.encode(ZoraFlags(swap_swords_and_rings=ThreeState.ON))
SWAP_RANDOM = zora_flags.encode(ZoraFlags(swap_swords_and_rings=ThreeState.POSSIBLE))
NO_CANDLES = z1r_with(toggles={"B09": ThreeState.OFF})     # Swordlish is refused with Extra Candles for now
SWORDS = "C07"
SEEDS = range(1, 7)
SEED_CODE_LENGTH = 4                 # four icons
WOOD_CAVE_WARE_0, TAKE_ANY_WARE_1 = 0x18610, 0x18614      # OW-SHOP-05's two extra-candle wares
NO_WARE = 0x3F
BANK_1_FILE, BANK_1_CPU = 0x4010, 0x8000
ALL_START_ITEMS = 0                  # Max Start Items: All (C17)
OTHER = {first: second for pair in SWAPPED_PAIRS for first, second in (pair, pair[::-1])}


def swordlish_flags(lowest: int = 1, highest: int = 8, state: Swordlish = Swordlish.ON) -> str:
    return zora_flags.encode(ZoraFlags(swordlish=state, swordlish_lowest=lowest, swordlish_highest=highest))


@cache
def built(flags: str, seed: int, zora: str, swap: bool = True) -> Built:
    """The seed built; with `swap` False, the same plan with only the swap's switch turned off."""
    chosen = plan(flags, seed, zora)
    if not swap:
        chosen = replace(chosen, zora_resolved=replace(chosen.zora_resolved, swap_swords_and_rings=ThreeState.OFF))
    return build(chosen, remember_repo_base_rom())


def same_placement(flags: str, seed: int, zora: str = SWAP) -> tuple[Built, Built] | None:
    """The seed with the swap and without, when both shipped the same attempt (the walk may judge an attempt
    differently once the items moved; then the two are no longer the same placement)."""
    on, off = built(flags, seed, zora), built(flags, seed, zora, swap=False)
    return (on, off) if on.result.attempts == off.result.attempts else None


def placements(flags: str, zora: str = SWAP) -> list[tuple[Built, Built]]:
    pairs = [pair for seed in SEEDS if (pair := same_placement(flags, seed, zora)) is not None]
    assert len(pairs) >= 3, "too few seeds shipped the same attempt both ways"
    return pairs


def dungeon_items(world: GameWorld) -> list[tuple[Item, int, int]]:
    """Each room's and cellar's item with the room's dark and sound bits."""
    return [(place.get(), *((place.room.is_dark, int(place.room.boss_sound)) if hasattr(place, "room")
                             else (0, 0))) for place in dungeon_places(world.levels)]


def overworld_items(world: GameWorld) -> list[tuple[Destination, Item, int]]:
    """Each one-item cave's item and heart requirement, each shop ware's item and price."""
    found: list[tuple[Destination, Item, int]] = []
    for cave in world.overworld.caves:
        if isinstance(cave, ItemCave):
            found.append((cave.destination, cave.item, cave.heart_requirement))
        elif isinstance(cave, Shop):
            found += [(cave.destination, ware.item, ware.price) for ware in cave.items]
        elif isinstance(cave, OverworldItem):
            found.append((cave.destination, cave.item, 0))
    return found


def swapped(item: Item) -> Item:
    return OTHER.get(item, item)


# --- the flag string -------------------------------------------------------------------------

def test_the_fields_are_version_16_and_off_by_default() -> None:
    names = {"swap_swords_and_rings", "swordlish", "swordlish_lowest", "swordlish_highest"}
    assert {field.version for field in zora_flags.FIELDS if field.name in names} == {16}
    default = zora_flags.decode("")
    assert (default.swap_swords_and_rings, default.swordlish) == (ThreeState.OFF, Swordlish.OFF)
    assert default.swordlish_range == range(1, 9)
    assert zora_flags.encode(ZoraFlags(swordlish_lowest=1, swordlish_highest=8)) == ""


@pytest.mark.parametrize(("lowest", "highest"), [(1, 8), (3, 5), (6, 2), (4, 4)])
def test_swordlish_s_range_round_trips_and_is_put_in_order(lowest: int, highest: int) -> None:
    flags = zora_flags.decode(swordlish_flags(lowest, highest))
    assert (flags.swordlish_lowest, flags.swordlish_highest) == (lowest, highest)
    assert flags.swordlish_range == range(min(lowest, highest), max(lowest, highest) + 1)


# --- refusals ----------------------------------------------------------------------------------

@pytest.mark.parametrize("swords", [WoodenSwordState.WOODEN_SWORD_ONLY, WoodenSwordState.SWORDLESS])
@pytest.mark.parametrize("zora", [SWAP, SWAP_RANDOM], ids=["on", "random"])
def test_the_swap_is_refused_without_swords(swords: WoodenSwordState, zora: str) -> None:
    """FP-SWAP-03: on or Random, with Swords: Wood Sword Only or Swordless."""
    with pytest.raises(FlagsRefused, match="Swap Swords and Rings"):
        plan(z1r_with(options={SWORDS: int(swords)}), 1, zora)


@pytest.mark.parametrize("swords", [WoodenSwordState.NORMAL, WoodenSwordState.NO_WOODEN_SWORD,
                                    WoodenSwordState.RANDOM])
def test_the_swap_is_accepted_with_the_other_sword_states(swords: WoodenSwordState) -> None:
    plan(z1r_with(options={SWORDS: int(swords)}), 1, SWAP)


@pytest.mark.parametrize("state", [Swordlish.ON, Swordlish.RANDOM])
def test_swordlish_is_refused_with_swords_other_than_normal(state: Swordlish) -> None:
    zora = swordlish_flags(state=state)
    for swords in (WoodenSwordState.WOODEN_SWORD_ONLY, WoodenSwordState.NO_WOODEN_SWORD,
                   WoodenSwordState.SWORDLESS, WoodenSwordState.RANDOM):
        with pytest.raises(FlagsRefused, match="needs Swords: Normal"):
            plan(z1r_with(NO_CANDLES, options={SWORDS: int(swords)}), 1, zora)
    plan(NO_CANDLES, 1, zora)


# --- Swordlish and Extra Candles (FP-SWL-03, owner ruling 2026-10-29: Swordlish removes the cave's candle) ----

@pytest.mark.parametrize("state", [Swordlish.ON, Swordlish.RANDOM])
@pytest.mark.parametrize("candles", [ThreeState.ON, ThreeState.POSSIBLE], ids=["on", "random"])
def test_the_default_preset_with_swordlish_is_accepted(state: Swordlish, candles: ThreeState) -> None:
    """The default preset (Extra Candles on) and Extra Candles Random both take Swordlish."""
    plan(z1r_with(), 1, swordlish_flags(state=state))
    plan(z1r_with(toggles={"B09": candles}), 1, swordlish_flags(state=state))


def wood_sword_cave(world: GameWorld) -> ItemCave:
    cave = world.overworld.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
    assert cave is not None
    return cave


def test_under_swordlish_with_extra_candles_the_wood_sword_cave_holds_no_candle() -> None:
    """Ware 0 empty ($3F at 0x18610), the sword in the middle; the take-any cave's candle (0x18614) as usual."""
    for seed in SEEDS[:4]:
        on = built(z1r_with(), seed, swordlish_flags())
        assert on.plan.zora_resolved.swordlish_pieces and on.plan.settings.is_on("B09")
        cave = wood_sword_cave(on.world)
        assert (cave.maybe_extra_candle, cave.item) == (Item.OVERWORLD_NO_ITEM, Item.WOOD_SWORD)
        rom = pipeline.finish(on, remember_repo_base_rom())
        assert (rom[WOOD_CAVE_WARE_0], rom[TAKE_ANY_WARE_1]) == (NO_WARE, Item.BLUE_CANDLE)


def test_without_swordlish_extra_candles_keeps_the_wood_sword_cave_s_candle() -> None:
    assert wood_sword_cave(built(z1r_with(), 1, "").world).maybe_extra_candle == Item.BLUE_CANDLE
    assert wood_sword_cave(built(z1r_with(), 1, SWAP).world).maybe_extra_candle == Item.BLUE_CANDLE


@pytest.mark.parametrize("extra", [ZoraFlags(shuffle_wood_sword=ThreeState.ON), ZoraFlags(progressive_items=True),
                                   ZoraFlags(randomize_magical_sword=True),
                                   ZoraFlags(offense_pacing=zora_flags.Pacing.NORMAL)],
                         ids=["shuffle wood sword", "progressive items", "randomize magical sword", "offense pacing"])
def test_swordlish_is_refused_with_the_sword_flags(extra: ZoraFlags) -> None:
    zora = zora_flags.encode(replace(extra, swordlish=Swordlish.ON))
    with pytest.raises(FlagsRefused, match="cannot be used with Swordlish"):
        plan(NO_CANDLES, 1, zora)


# --- the swap ------------------------------------------------------------------------------------

def test_the_swap_exchanges_every_place_s_item_and_keeps_everything_else() -> None:
    """FP-SWAP-01, -02 and -05 on the same placement: every item of the pairs exchanged, in rooms, cellars,
    caves and shops; the rooms' dark and sound bits, the wares' prices and the caves' hearts kept."""
    for on, off in placements(z1r_with()):
        assert dungeon_items(on.world) == [(swapped(item), dark, sound) for item, dark, sound in
                                           dungeon_items(off.world)]
        assert overworld_items(on.world) == [(where, swapped(item), number) for where, item, number in
                                             overworld_items(off.world)]
        for first, second in SWAPPED_PAIRS:
            assert count(on.world, first) == count(off.world, second)
            assert count(on.world, second) == count(off.world, first)


def count(world: GameWorld, item: Item) -> int:
    return sum(holder.get() == item for holder in shipped_holders(world))


def shipped_holders(world: GameWorld) -> list:
    """Every place of a shipped world (its special caves are in the overworld by then)."""
    places: list = list(dungeon_places(world.levels))
    for cave in world.overworld.caves:
        if isinstance(cave, ItemCave):
            places.append(_Get(cave.item))
        elif isinstance(cave, Shop):
            places += [_Get(ware.item) for ware in cave.items]
        elif isinstance(cave, OverworldItem):
            places.append(_Get(cave.item))
    return places


class _Get:
    def __init__(self, item: Item) -> None:
        self.item = item

    def get(self) -> Item:
        return self.item


def test_with_prg0_s_stock_the_white_sword_is_sold_and_the_magical_sword_cave_offers_the_red_ring() -> None:
    """FP-SWAP-01's Check: no shop ware holds the Blue Ring; the magical-sword cave's ware holds $13."""
    for seed in SEEDS:
        world = built(z1r_with(), seed, SWAP).world
        wares = [ware.item for cave in world.overworld.caves if isinstance(cave, Shop) for ware in cave.items]
        assert Item.BLUE_RING not in wares and Item.WHITE_SWORD in wares
        assert magical_sword_cave(world).item == Item.RED_RING


def magical_sword_cave(world: GameWorld) -> ItemCave:
    cave = world.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert cave is not None
    return cave


def test_the_tracked_records_follow_the_items() -> None:
    """The walk and the hints read the records: each record of a pair item names the place now holding it."""
    for seed in SEEDS:
        state = built(z1r_with(), seed, SWAP).result.item_shuffle_result
        assert state is not None
        records = {Item(record.item): record for record in state.tracked if record.item in OTHER}
        assert str(records[Item.WHITE_SWORD].slot).startswith("shop ")
        assert records[Item.RED_RING].slot == "magical_sword"


@pytest.mark.parametrize(("start", "kept"), [("B69", (Item.WHITE_SWORD, Item.BLUE_RING)),
                                             ("B70", (Item.MAGICAL_SWORD, Item.RED_RING))],
                         ids=["start white sword", "start magical sword"])
def test_a_pair_with_a_starting_item_is_not_swapped(start: str, kept: tuple[Item, Item]) -> None:
    """FP-SWAP-01: that pair keeps its places; the other pair is still swapped."""
    flags = z1r_with(toggles={start: ThreeState.ON}, options={"C17": ALL_START_ITEMS})
    for on, off in placements(flags):
        assert kept[0] in on.plan.alternatives.start_items
        assert count(on.world, kept[0]) == count(off.world, kept[0])
        moved = next(pair for pair in SWAPPED_PAIRS if pair != kept)
        assert count(on.world, moved[0]) == count(off.world, moved[1])
        assert dungeon_items(on.world) == [(item if item in kept else swapped(item), dark, sound)
                                           for item, dark, sound in dungeon_items(off.world)]


def test_pins_are_placed_before_the_swap_and_never_rewritten() -> None:
    """FP-SWAP-04: the white-sword cave pinned to the White Sword (C13 = 15) holds the Blue Ring, the Armos
    pinned to the Red Ring (C11 = 12) the Magical Sword; the flag string keeps both pins."""
    flags = z1r_with(options={"C13": 15, "C11": 12})
    for seed in SEEDS[:3]:
        chosen = plan(flags, seed, SWAP)
        assert (chosen.settings.option("C13"), chosen.settings.option("C11")) == (15, 12)
        world = built(flags, seed, SWAP).world
        white_sword_cave = world.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
        assert white_sword_cave is not None and white_sword_cave.item == Item.BLUE_RING
        armos = world.overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
        assert armos is not None and armos.item == Item.MAGICAL_SWORD


def test_random_swords_skip_the_swap_when_they_resolve_without_swords() -> None:
    """FP-SWAP-03: under Swords: Random a seed resolving to Wood Sword Only or Swordless has no swap (the
    magical-sword cave offers item $02, FP-WOOD-02); one resolving to Normal or No Wood Sword has it."""
    flags = z1r_with(options={SWORDS: int(WoodenSwordState.RANDOM)})
    seen = set()
    for seed in range(1, 40):
        chosen = plan(flags, seed, SWAP)
        state = chosen.alternatives.wooden_sword_state
        seen.add(state)
        assert extra_options(chosen).swap_swords_and_rings == (state in (WoodenSwordState.NORMAL,
                                                                         WoodenSwordState.NO_WOODEN_SWORD))
    assert WoodenSwordState.SWORDLESS in seen and WoodenSwordState.NORMAL in seen


def test_the_swap_works_under_no_wood_sword() -> None:
    world = built(z1r_with(options={SWORDS: int(WoodenSwordState.NO_WOODEN_SWORD)}), 1, SWAP).world
    assert magical_sword_cave(world).item == Item.RED_RING


# --- Swordlish ---------------------------------------------------------------------------------------

def test_n_is_drawn_from_the_range() -> None:
    drawn = {plan(NO_CANDLES, seed, swordlish_flags(6, 3)).zora_resolved.swordlish_pieces for seed in range(1, 60)}
    assert drawn == {3, 4, 5, 6}
    assert {plan(NO_CANDLES, seed, swordlish_flags(5, 5)).zora_resolved.swordlish_pieces
            for seed in range(1, 10)} == {5}


def test_swordlish_random_picks_each_of_five_states_about_a_fifth_of_the_time() -> None:
    """FP-SWL-04, over 500 plans: each state 100 expected, within about four standard deviations."""
    picks: Counter[str] = Counter()
    zora = swordlish_flags(state=Swordlish.RANDOM)
    for seed in range(500):
        chosen = plan(NO_CANDLES, seed, zora)
        picks["swordlish" if chosen.zora_resolved.swordlish_pieces else
              chosen.alternatives.wooden_sword_state.name] += 1
    assert len(picks) == 5 and all(64 <= number <= 136 for number in picks.values()), picks


def test_swordlish_random_swaps_only_with_normal_no_wood_sword_and_swordlish() -> None:
    zora = zora_flags.encode(ZoraFlags(swordlish=Swordlish.RANDOM, swap_swords_and_rings=ThreeState.ON))
    for seed in range(60):
        chosen = plan(NO_CANDLES, seed, zora)
        state = chosen.alternatives.wooden_sword_state
        assert extra_options(chosen).swap_swords_and_rings == (
            state in (WoodenSwordState.NORMAL, WoodenSwordState.NO_WOODEN_SWORD))


def rules(pieces: int, start_levels: frozenset[int] = frozenset()) -> LogicRules:
    return LogicRules(swordlish_pieces=pieces, start_triforce_pieces=sum(1 << (level - 1) for level in start_levels))


def test_the_pieces_count_each_level_once_and_the_starting_pieces() -> None:
    """VA-REJ-23: the levels whose piece is a starting piece or completed, each level once, levels 1 to 8."""
    assert rules(2, frozenset({1})).swordlish_opens({1, 2})
    assert not rules(3, frozenset({1})).swordlish_opens({1, 2})       # level 1 counts once
    assert not rules(2).swordlish_opens({1, 9})                       # level 9 holds no piece
    assert rules(2, frozenset({4, 5})).wood_sword_from_start
    assert not rules(3, frozenset({4, 5})).wood_sword_from_start
    assert not rules(1).wood_sword_from_start and LogicRules().wood_sword_from_start
    assert TRIFORCE_LEVEL_SET == frozenset(range(1, 9))


def test_the_walk_gives_the_wooden_sword_at_n_pieces_or_with_the_white_sword() -> None:
    """VA-REJ-23 on a built Swordlish seed: the closure holds the wooden sword; withheld until N, it is
    first held in a round once N levels are completed or the white sword is held."""
    world_built = built(NO_CANDLES, 1, swordlish_flags(2, 2))
    chosen = world_built.plan
    rules_used = extra_options(chosen).logic_rules
    assert rules_used.swordlish_pieces == 2
    state, caves = world_built.result.item_shuffle_result, world_built.result.overworld
    assert state is not None and caves is not None
    check = AcceptanceCheck(world_built.world.levels, state, world_built.world.overworld, caves, rules_used)
    held, completed = check.closure()
    assert Item.WOOD_SWORD in held
    assert len(completed & TRIFORCE_LEVEL_SET) >= 2 or Item.WHITE_SWORD in held


def test_the_world_holds_n_and_the_rom_reads_it_back() -> None:
    for seed in SEEDS[:3]:
        chosen = plan(NO_CANDLES, seed, swordlish_flags(2, 7))
        world = built(NO_CANDLES, seed, swordlish_flags(2, 7)).world
        assert world.swordlish_pieces == chosen.zora_resolved.swordlish_pieces in range(2, 8)
        rom = pipeline.finish(built(NO_CANDLES, seed, swordlish_flags(2, 7)), remember_repo_base_rom())
        assert parse_rom(rom).swordlish_pieces == world.swordlish_pieces
        assert swordlish.parsed_pieces(rom) == world.swordlish_pieces


def test_swordlish_writes_only_its_own_bytes() -> None:
    """FP-SWL-05: the shipped world with N and with 0 differ only in the two hooks, the two routines and the
    cave's own text; every text slot and pointer is the hint style's."""
    world_built = built(NO_CANDLES, 2, swordlish_flags(3, 3))
    config = world_built.plan.config
    with_n = serialize_to_rom(world_built.world, remember_repo_base_rom(), config=config)
    without = serialize_to_rom(replace(world_built.world, swordlish_pieces=0), remember_repo_base_rom(), config=config)
    allowed = {offset + index for offset, data in swordlish.swordlish_writes(3) for index in range(len(data))}
    # and the seed's code (FP-HASH-01), which names the whole world
    allowed |= set(range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH))
    differ = {offset for offset, (a, b) in enumerate(zip(with_n, without, strict=True)) if a != b}
    assert differ and differ <= allowed
    assert with_n[swordlish.TAKE_HOOK:swordlish.TAKE_HOOK + 5] != without[swordlish.TAKE_HOOK:swordlish.TAKE_HOOK + 5]


def test_each_file_offset_is_its_bank_1_address() -> None:
    def bank_1(offset: int) -> int:
        return BANK_1_CPU + offset - BANK_1_FILE
    assert bank_1(swordlish.TAKE_CHECK) == swordlish.TAKE_CHECK_CPU
    assert bank_1(swordlish.TEXT_ADDRESS) == swordlish.TEXT_ADDRESS_CPU
    assert bank_1(swordlish.TEXT) == swordlish.TEXT_CPU


def test_the_text_names_n() -> None:
    assert swordlish.swordlish_text(1) == "BRING 1 TRIFORCE AND\nYOU CAN HAVE THIS."
    assert swordlish.swordlish_text(6) == "BRING 6 TRIFORCES AND\nYOU CAN HAVE THIS."


# --- existing settings ---------------------------------------------------------------------------------

EXISTING = (
    (z1r_with(), ""),
    (z1r_with(options={SWORDS: int(WoodenSwordState.NO_WOODEN_SWORD)}), ""),
    (z1r_with(options={SWORDS: int(WoodenSwordState.RANDOM)}), ""),
    (z1r_with(toggles={"B69": ThreeState.ON, "B09": ThreeState.OFF}), ""),
    (z1r_with(toggles={"B10": ThreeState.OFF}),
     zora_flags.encode(ZoraFlags(randomize_magical_sword=True, shuffle_wood_sword=ThreeState.ON))),
    (z1r_with(), zora_flags.encode(ZoraFlags(progressive_items=True, shop_items_in_pool=True))),
)


def without_the_additions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every path of the additions stubbed out: the draws, both steps and the ROM writes."""
    monkeypatch.setattr(zora_flags, "resolve_swordlish", lambda resolved, z1r, _below: (resolved, z1r))
    monkeypatch.setattr(zora_flags, "swaps_swords_and_rings", lambda _resolved, _z1r: False)
    monkeypatch.setattr(generation_pass, "swap_swords_and_rings", _never)
    monkeypatch.setattr(generation_pass, "swordlish_step", _never)
    monkeypatch.setattr(serialize_game_world, "swordlish_writes", lambda _pieces: [])


def _never(*_args: object) -> None:
    raise AssertionError("a Swap Swords and Rings or Swordlish step ran for existing settings")


@pytest.mark.parametrize(("flags", "zora"), EXISTING)
def test_existing_settings_give_the_same_rom_with_and_without_the_additions(
        flags: str, zora: str, monkeypatch: pytest.MonkeyPatch) -> None:
    base = remember_repo_base_rom()
    for seed in (1, 2):
        rom = pipeline.generate_rom(flags, seed, base, zora_flag_string=zora).rom
        with monkeypatch.context() as patched:
            without_the_additions(patched)
            assert pipeline.generate_rom(flags, seed, base, zora_flag_string=zora).rom == rom
        assert rom[swordlish.TAKE_HOOK:swordlish.TAKE_HOOK + 5] == swordlish.TAKE_HOOK_PRG0
        assert rom[swordlish.TEXT_HOOK:swordlish.TEXT_HOOK + 5] == swordlish.TEXT_HOOK_PRG0
