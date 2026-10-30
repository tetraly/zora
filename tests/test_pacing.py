"""Offense and Defense Item Pacing and Recorder Warping (ZORA version 15;
docs/zora-extras.md section 22), from Z1M1 (docs/z1m1/pacing.md): the tables, the rules' effect on a
dungeon's entry and on the walk, the flag fields, and generation under each."""
from dataclasses import replace
from functools import cache

from tests.needs import needs_base_rom
from tests.test_coop_reserved import z1r_with
from zora.flags import zora_flags
from zora.flags.codec import decode
from zora.flags.fields import (
    LEVEL_9_FIRST_PIN,
    LEVEL_9_SECOND_PIN,
    ItemShuffleScope,
    ThreeState,
    WoodenSwordState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import Pacing, ZoraFlags
from zora.generate import acceptance_check as acceptance
from zora.generate.acceptance_check import (
    DEFAULT_RULES,
    RINGS_1,
    RINGS_2,
    SWORDS_1,
    SWORDS_2,
    AcceptanceCheck,
    logic_rules,
    rings_needed,
    swords_needed,
)
from zora.generate.pipeline import generate_world, plan
from zora.model.enums import Item, RoomType
from zora.rom.base_rom import verify_base_rom

# docs/z1m1/pacing.md sections 1 and 2: the swords and rings each level needs, level 1 to 9
Z1M1_SWORDS = {Pacing.EARLIER: (1, 1, 1, 1, 2, 2, 2, 2, 2), Pacing.NORMAL: (0, 0, 1, 1, 1, 1, 2, 2, 2),
               Pacing.LATER: (0, 0, 0, 0, 1, 1, 1, 1, 2)}
Z1M1_RINGS = {Pacing.EARLIER: (0, 0, 0, 0, 1, 1, 1, 1, 2), Pacing.NORMAL: (0, 0, 0, 0, 0, 0, 1, 1, 1),
              Pacing.LATER: (0, 0, 0, 0, 0, 0, 0, 0, 1)}
LEVELS = range(1, 10)


def test_the_tables_are_z1m1s() -> None:
    for pacing in (Pacing.EARLIER, Pacing.NORMAL, Pacing.LATER):
        assert tuple(swords_needed(pacing, level) for level in LEVELS) == Z1M1_SWORDS[pacing], pacing
        assert tuple(rings_needed(pacing, level) for level in LEVELS) == Z1M1_RINGS[pacing], pacing
    assert all(swords_needed(Pacing.OFF, level) == rings_needed(Pacing.OFF, level) == 0 for level in LEVELS)


def test_a_levels_needs_are_count_pseudo_items() -> None:
    rules = logic_rules(False, False, offense_pacing=Pacing.EARLIER, defense_pacing=Pacing.EARLIER)
    assert rules.pacing_needs(1) == {SWORDS_1}
    assert rules.pacing_needs(5) == {SWORDS_1, SWORDS_2, RINGS_1}
    assert rules.pacing_needs(9) == {SWORDS_1, SWORDS_2, RINGS_1, RINGS_2}
    assert logic_rules(False, False).pacing_needs(9) == frozenset() and not DEFAULT_RULES.paces


def test_the_defaults_are_todays_rules() -> None:
    assert logic_rules(False, False, offense_pacing=Pacing.OFF, defense_pacing=Pacing.OFF,
                       recorder_warps=False) == DEFAULT_RULES


@needs_base_rom
def test_a_ladder_moat_room_takes_any_side_as_a_target() -> None:
    """The arrival rule: a T room needs the south side and another; in a ladder_moats layout (with the ladder), any."""
    from zora.generate.dungeon_walk import Walk
    from zora.model.enums import Side
    arrival = Walk(reached={5: {Side.NORTH}}, ladder_moats=frozenset({RoomType.T_ROOM}))

    class Stub:
        def __init__(self, layout: RoomType) -> None:
            self.block = self
            self._layout = layout

        def room(self, _number: int) -> object:
            return type("R", (), {"room_type": self._layout})()

    assert arrival.accepts(Stub(RoomType.T_ROOM), 5)                     # type: ignore[arg-type]
    assert not Walk(reached={5: {Side.NORTH}}).accepts(Stub(RoomType.T_ROOM), 5)     # type: ignore[arg-type]


@cache
def generated() -> tuple:
    world, result = generate_world(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1), verify_base_rom().read_bytes())
    return world, result


def check(rules: acceptance.LogicRules) -> AcceptanceCheck:
    world, result = generated()
    return AcceptanceCheck(world.levels, result.item_shuffle_result, world.overworld, result.overworld, rules)


@needs_base_rom
def test_a_level_needs_the_counts_before_it_is_entered() -> None:
    rules = logic_rules(False, False, offense_pacing=Pacing.EARLIER, defense_pacing=Pacing.EARLIER)
    everything = frozenset({Item.RAFT, Item.RECORDER, Item.LADDER, Item.POWER_BRACELET, Item.BOW, Item.SILVER_ARROWS,
                            Item.WOOD_SWORD, Item.RED_CANDLE, Item.LETTER})
    acceptance_check = check(rules)
    assert not acceptance_check.can_enter(1, everything)                  # a sword count is a held pseudo-item
    assert acceptance_check.can_enter(1, everything | {SWORDS_1})
    assert not acceptance_check.can_enter(5, everything | {SWORDS_1, RINGS_1})
    assert acceptance_check.can_enter(5, everything | {SWORDS_1, SWORDS_2, RINGS_1})
    assert check(DEFAULT_RULES).can_enter(1, everything) and check(DEFAULT_RULES).can_enter(5, everything)


@needs_base_rom
def test_the_closure_counts_the_wooden_sword_and_the_swords_it_collects() -> None:
    rules = logic_rules(False, False, offense_pacing=Pacing.LATER, magical_sword_cave_counts=True)
    held, completed = check(rules).closure()
    assert SWORDS_1 in held                                               # the wooden sword, from the start
    swords = {Item.WHITE_SWORD, Item.MAGICAL_SWORD} & held
    assert SWORDS_2 in held or not swords                                  # the white sword, or the cave's magical one
    assert completed


@needs_base_rom
def test_a_dungeon_door_on_a_raft_screen_is_also_entered_with_the_recorder() -> None:
    door = check(DEFAULT_RULES).caves.entry_door(4)
    raft_only = ((frozenset({door}), Item.RAFT),)
    without = check(replace(DEFAULT_RULES, screen_needs=raft_only))
    with_recorder = check(replace(DEFAULT_RULES, screen_needs=raft_only, recorder_warps=True))
    held = frozenset({Item.WOOD_SWORD, Item.RECORDER})
    assert not without.can_enter(4, held) and with_recorder.can_enter(4, held)
    assert with_recorder.can_enter(4, frozenset({Item.WOOD_SWORD, Item.RAFT}))
    assert not with_recorder.can_enter(4, frozenset({Item.WOOD_SWORD}))
    # only the raft's doors, and never level 9
    ladder_only = ((frozenset({door}), Item.LADDER),)
    assert not check(replace(DEFAULT_RULES, screen_needs=ladder_only, recorder_warps=True)).can_enter(4, held)


def test_the_flag_fields_round_trip_at_version_15() -> None:
    flags = ZoraFlags(offense_pacing=Pacing.LATER, defense_pacing=Pacing.EARLIER, recorder_warping=True)
    text = zora_flags.encode(flags)
    assert text.startswith("15.") and zora_flags.decode(text) == flags
    assert zora_flags.CURRENT_VERSION >= 15
    for name in ("offense_pacing", "defense_pacing", "recorder_warping"):
        assert next(field for field in zora_flags.FIELDS if field.name == name).version == 15
    assert zora_flags.encode(ZoraFlags()) == ""


def test_offense_pacing_is_refused_with_a_changed_sword_state() -> None:
    settings = decode(z1r_with(options={"C07": WoodenSwordState.WOODEN_SWORD_ONLY}))
    assert any("Offense Item Pacing" in reason for reason in zora_flags.validate(
        ZoraFlags(offense_pacing=Pacing.NORMAL), settings))
    assert not zora_flags.validate(ZoraFlags(defense_pacing=Pacing.NORMAL), settings)


def test_defense_pacing_earlier_is_refused_with_the_items_left_in_place() -> None:
    """Earlier asks for both rings before level 9, and Item Shuffle: None (or Random, which may draw it) leaves the
    Red Ring inside level 9: refused (zora_flags.defense_pacing_conflicts; 0 of 3 invariant seeds generated).
    Random (No Vanilla), the other Item Shuffles and the other pacing values are accepted."""
    def refused(item_shuffle: ItemShuffleScope, pacing: Pacing, no_vanilla: bool = False) -> bool:
        settings = decode(z1r_with(options={"C06": item_shuffle}))
        flags = ZoraFlags(defense_pacing=pacing, item_shuffle_no_vanilla=no_vanilla)
        return any("Defense Item Pacing: Earlier" in reason for reason in zora_flags.validate(flags, settings))
    assert refused(ItemShuffleScope.NONE, Pacing.EARLIER) and refused(ItemShuffleScope.RANDOM, Pacing.EARLIER)
    assert not refused(ItemShuffleScope.RANDOM, Pacing.EARLIER, no_vanilla=True)
    assert not any(refused(scope, Pacing.EARLIER) for scope in (
        ItemShuffleScope.FULL, ItemShuffleScope.WITHIN_EACH_DUNGEON, ItemShuffleScope.DUNGEON_ITEMS_ONLY))
    assert not any(refused(ItemShuffleScope.NONE, pacing) for pacing in (Pacing.NORMAL, Pacing.LATER, Pacing.OFF))


def test_recorder_warping_is_unavailable_until_both_recorder_warps_are_on() -> None:
    """The page greys the setting out (zora_state's "unavailable") unless B07 and B01 are on."""
    from zora.flags import zora_form
    on = {"B01": ThreeState.ON, "B07": ThreeState.ON}
    assert zora_form.unavailable_fields(decode(z1r_with(toggles=on))) == []
    for off in ("B01", "B07"):
        unavailable = zora_form.unavailable_fields(decode(z1r_with(toggles={**on, off: ThreeState.OFF})))
        assert [entry["field"] for entry in unavailable] == ["recorder_warping"]
    state = zora_form.zora_state("", decode(z1r_with(toggles={"B07": ThreeState.OFF})))
    assert state["unavailable"][0]["field"] == "recorder_warping" and state["ok"]


@cache
def generated_with_cave_sword() -> tuple:
    """Seed 6: the white sword lies in the white-sword cave itself."""
    return generate_world(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 6), verify_base_rom().read_bytes())


@needs_base_rom
def test_a_sword_cave_counts_only_with_the_hearts_it_asks_for() -> None:
    """Offense Item Pacing's heart model: a sword in the white-sword cave counts for the pace only once the
    starting hearts and the reachable heart containers meet the cave's requirement; the rest of the closure
    (what is collected) is untouched."""
    from zora.generate.acceptance_check import PacingHearts
    world, result = generated_with_cave_sword()
    tracked = result.item_shuffle_result.tracked
    cave_sword = next(index for index, place in enumerate(tracked)
                      if place.slot == "white_sword" and place.item == Item.WHITE_SWORD)
    def pacing_check(white_sword: int) -> AcceptanceCheck:
        rules = replace(logic_rules(False, False, offense_pacing=Pacing.EARLIER),
                        pacing_hearts=PacingHearts(starting=3, white_sword=white_sword, magical_sword=99))
        return AcceptanceCheck(world.levels, result.item_shuffle_result, world.overworld, result.overworld, rules)
    everything = frozenset({Item.RAFT, Item.RECORDER, Item.LADDER, Item.POWER_BRACELET, Item.BOW, Item.WOOD_SWORD,
                            Item.RED_CANDLE, Item.LETTER, Item.WHITE_SWORD})
    assert pacing_check(0).pacing_sword_count({cave_sword}, everything) == 2          # the wooden sword and this one
    assert pacing_check(99).pacing_sword_count({cave_sword}, everything) == 1         # its hearts are out of reach
    assert pacing_check(0).closure()[0] >= {Item.WHITE_SWORD}                         # collected all the same
    assert Item.WHITE_SWORD in pacing_check(99).closure()[0]


@needs_base_rom
def test_hearts_held_counts_the_starting_hearts_and_what_is_reached() -> None:
    from zora.generate.acceptance_check import PacingHearts
    rules = replace(logic_rules(False, False, offense_pacing=Pacing.NORMAL),
                    pacing_hearts=PacingHearts(starting=3, white_sword=5, magical_sword=12))
    acceptance_check = check(rules)
    model = PacingHearts(starting=3, white_sword=5, magical_sword=12)
    nothing = acceptance_check.hearts_held(frozenset(), model)
    held, _ = acceptance_check.closure()
    assert nothing >= 3 and acceptance_check.hearts_held(frozenset(held), model) > nothing


def test_the_default_rules_carry_no_heart_model() -> None:
    assert DEFAULT_RULES.pacing_hearts is None
    assert logic_rules(False, False, offense_pacing=Pacing.OFF).pacing_hearts is None
    from zora.generate.extra_options import NO_EXTRAS
    assert NO_EXTRAS.logic_rules == DEFAULT_RULES


@needs_base_rom
def test_defense_pacing_tracks_the_blue_ring_when_shop_items_join_the_pool() -> None:
    """With Shop Items in the Item Pool the blue ring joins the pool; only the red ring was tracked, so Earlier's
    two rings at level 9 could never be held and every attempt was rejected (E1) until the time limit
    (Shop Items on with Defense Item Pacing: Earlier timed out in 20 of 20 website seeds). It is tracked when
    Defense Item Pacing is on, and builds within a few attempts."""
    base = verify_base_rom().read_bytes()
    for pacing, tracked in ((Pacing.EARLIER, True), (Pacing.OFF, False)):
        flags = ZoraFlags(shop_items_in_pool=True, defense_pacing=pacing)
        _world, result = generate_world(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, zora_flags.encode(flags)), base)
        assert result.item_shuffle_result is not None
        items = {place.item for place in result.item_shuffle_result.tracked}
        assert (Item.BLUE_RING in items) is tracked, pacing
        assert result.attempts < 200, pacing


def test_a_pin_the_pace_can_never_satisfy_is_refused() -> None:
    """Level 9 Item 1 or 2 at the Red Ring with Defense Item Pacing: Earlier (two rings to enter level 9), and at the
    White Sword with Offense Item Pacing at any value (two swords): nearly every attempt was rejected until the
    generation limit; Off stays accepted, with Randomize Magical Sword on or off."""
    for pin in (LEVEL_9_FIRST_PIN, LEVEL_9_SECOND_PIN):
        red_ring = decode(z1r_with(options={pin.id: zora_flags.RED_RING_PIN}))
        white_sword = decode(z1r_with(options={pin.id: zora_flags.WHITE_SWORD_PIN}))
        for pacing in Pacing:
            defense = zora_flags.level_9_pin_conflicts(ZoraFlags(defense_pacing=pacing), red_ring)
            offense = zora_flags.level_9_pin_conflicts(ZoraFlags(offense_pacing=pacing), white_sword)
            assert bool(defense) is (pacing is Pacing.EARLIER), pacing
            assert bool(offense) is (pacing is not Pacing.OFF), pacing
        for pacing in Pacing:       # Randomize Magical Sword on changes nothing
            flags = ZoraFlags(offense_pacing=pacing, randomize_magical_sword=True)
            on = zora_flags.level_9_pin_conflicts(flags, white_sword)
            assert bool(on) is (pacing is not Pacing.OFF), pacing
