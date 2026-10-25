"""Archipelago's options (zora/archipelago.py option_fields and flag_strings; docs/archipelago.md
"Interface"), Archipelago Phase 4a test 2 and the owner's additions 1 and 2:
  - every offered value round-trips through flag_strings and the decoders; B82 is never offered
    and always off; the defaults are the page's default preset; a new field appears by itself;
  - only values ZORA generates are offered (the support matrix's, "?" only where it allows one):
    each value of each field alone generates, or is refused at flag_strings with a named
    dependency conflict, never refused later as not produced;
  - each dependency rule is named when it refuses, and B23 is kept as given while B22 is off
    (FL-DEP-06)."""
import pytest

from zora import archipelago
from zora.archipelago import OptionsConflict, OptionSpec, flag_strings, option_corrections, option_fields
from zora.flags import form as flag_form
from zora.flags import zora_flags, zora_form
from zora.flags.codec import canonicalize, decode
from zora.flags.fields import (ENCODE_LEVEL_DATA, HitPointChange, OptionField, PinnedItem, ThreeState, ToggleField,
                               WoodenSwordState)
from zora.flags.support import LEVEL_9_PINS
from zora.flags.zora_flags import GatekeeperBosses
from zora.generate.pipeline import build, plan
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SPECS = option_fields()
SINGLE_VALUES = [(spec.id, value) for spec in SPECS for value in spec.values if value != spec.default]
# The single changes from the page's preset that a dependency rule refuses, and the rule's words.
EXPECTED_CONFLICTS = {
    ("randomize_magical_sword", 1): "Randomize Magical Sword",     # the heart cap, B10 on in the preset
    # Add L4 Sword's three-way control (Off 0, Level 2 1, Level 9 2) needs Progressive Items; Level 9
    # Entrance = Level 4 sword needs Add L4 Sword = Level 2 (docs/design/asnb.md section 2)
    ("add_l4_sword", 1): "Add L4 Sword needs Progressive Items",
    ("add_l4_sword", 2): "Add L4 Sword needs Progressive Items",
    ("level_9_entrance_sword", 1): "needs Add L4 Sword = Level 2",
    ("extra_power_bracelet_blocks", int(ThreeState.ON)): "Extra Power Bracelet Blocks",   # B04 on
}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def value_in(strings: tuple[str, str], spec: OptionSpec) -> int:
    """The option's value as the flag strings hold it."""
    flags, zora = strings
    if spec.id in flag_form.FIELDS_BY_ID:
        field = flag_form.FIELDS_BY_ID[spec.id]
        settings = decode(flags)
        return settings.option(field) if isinstance(field, OptionField) else int(settings.toggle(field))
    return zora_form.control_value(zora_flags.decode(zora), spec.id)


def test_the_defaults_are_the_pages_preset() -> None:
    page = flag_form.metadata()
    assert flag_strings({}) == (canonicalize(page["defaultFlags"]), "")
    assert all(spec.default in spec.values for spec in SPECS)


def test_encode_level_data_is_never_offered_and_always_off() -> None:
    assert ENCODE_LEVEL_DATA.id not in {spec.id for spec in SPECS}
    for option, value in SINGLE_VALUES:
        try:
            flags, _zora = flag_strings({option: value})
        except OptionsConflict:
            continue
        assert decode(flags).toggle(ENCODE_LEVEL_DATA) is ThreeState.OFF


def test_only_supported_values_are_offered() -> None:
    for spec in SPECS:
        if spec.id in flag_form.FIELDS_BY_ID:
            held = archipelago.HELD_BACK.get(spec.id, frozenset())
            assert spec.values == tuple(int(v) for v in flag_form.supported_values(flag_form.FIELDS_BY_ID[spec.id])
                                        if v not in held)
    assert {spec.id for spec in SPECS} == ({field.id for field in flag_form.ALL_FIELDS} | set(zora_form.FIELD_NAMES)
                                           ) - archipelago.NOT_OFFERED
    assert archipelago.NOT_OFFERED == {ENCODE_LEVEL_DATA.id, "C06", "shuffle_wood_sword", "disable_custom_music"}


def test_shuffle_wood_sword_is_never_offered_and_always_off() -> None:
    """Owner ruling (2026-10-17): it pools the wooden sword, and the logic assumes the wooden sword,
    so bombs, from the start (owner decision 1), so it is never offered rather than held back."""
    assert "shuffle_wood_sword" not in archipelago.HELD_BACK
    assert "sword" in archipelago.ZORA_FORCED_OFF["shuffle_wood_sword"]
    assert zora_flags.decode(flag_strings({})[1]).shuffle_wood_sword is ThreeState.OFF
    for value in ("on", ThreeState.ON, ThreeState.OFF):
        with pytest.raises(OptionsConflict, match="shuffle_wood_sword is never offered: Always off in Archipelago"):
            flag_strings({"shuffle_wood_sword": value})


def test_a_yaml_naming_shuffle_wood_sword_gets_zoras_reason() -> None:
    """The world keeps Shuffle Wood Sword as a hidden option (archipelago/options.py), so a YAML that
    names it is not met with Archipelago's "not a valid option name" warning and a silent Off: off
    passes, any other value is refused with the reason."""
    [spec] = [spec for spec in archipelago.never_offered_fields() if spec.key == "shuffle_wood_sword"]
    assert (spec.key, spec.kind, spec.default) == ("shuffle_wood_sword", "three_state", ThreeState.OFF)
    assert spec.description == archipelago.ZORA_FORCED_OFF["shuffle_wood_sword"]
    assert [key for _value, key in spec.value_keys] == ["off", "on", "random_per_seed"]
    for off in ("off", "OFF", False, 0, int(ThreeState.OFF)):
        assert archipelago.never_offered_refusal("shuffle_wood_sword", off) is None
    for other in ("on", "random_per_seed", "random", True, 1, 2):
        refusal = archipelago.never_offered_refusal("shuffle_wood_sword", other)
        assert refusal is not None
        assert refusal.startswith(f"Shuffle Wood Sword (shuffle_wood_sword): {other!r} is not offered. Always off")
        assert refusal.endswith("Remove shuffle_wood_sword from the YAML (or set it to off).")


def test_item_shuffle_is_never_offered_and_always_full() -> None:
    """Owner ruling (2026-10-10): Archipelago places the items itself."""
    assert decode(flag_strings({})[0]).option("C06") == 3
    with pytest.raises(OptionsConflict, match="C06"):
        flag_strings({"C06": 2})


# Beta 8's value still held (archipelago.HELD_BACK's comment): Replace Book Fire with Explosion, not
# compatible with Archipelago (owner ruling, 2026-10-22)
BETA_8_HELD_BACK = {"B47": {ThreeState.ON, ThreeState.POSSIBLE}}
# The beta 9 export's pins, held for their scan (archipelago.HELD_BACK's comment): the coast's Non-Heart
# and level 9's places at the five-item rule's items and the Wand
BETA_9_HELD_LEVEL_9_PINS = {PinnedItem.BOW, PinnedItem.LADDER, PinnedItem.POWER_BRACELET, PinnedItem.RAFT,
                            PinnedItem.RECORDER, PinnedItem.WAND}
BETA_9_HELD_BACK = {"C12": {PinnedItem.ANY_ITEM_EXCEPT_HEART_CONTAINER},
                    **dict.fromkeys(("C26", "C27"), BETA_9_HELD_LEVEL_9_PINS),
                    # Gatekeeper Bosses, held for its scan (owner, 2026-10-24): only Off is offered
                    "gatekeeper_bosses": {GatekeeperBosses.ANYWHERE, GatekeeperBosses.LATE,
                                          GatekeeperBosses.EARLY}}
# Released on 2026-10-22 once their scan passed (archipelago.HELD_BACK's comment)
BETA_8_RELEASED_TOGGLES = ("B18", "B20", "B32", "B33", "B35", "B07", "B39", "B21", "B37")


def test_values_wait_for_the_logic_scan() -> None:
    """Owner ruling (2026-10-10): a value is offered once it passes C2's logic scan. C01 = 1 to 4,
    C04 = 2 and 3, B81 and B03 (on and Random), Helpful hints (C03 = 1), and on 2026-10-11 Dungeon
    Quest 1st Quest (C02 = 0), the nine start items, Allow Important Items in 9 (B25, on and
    Random), Dungeon Quest 2nd Quest (C02 = 1), Shuffle Dungeon Start Room (B26, on and Random)
    and on 2026-10-12 Remove Most Open Stairs (B30) and Book to Understand NPCs (B48), on and
    Random, and Dungeon Quest Mixed + Shapes (C02 = 4) have, and on 2026-10-13 (beta 5) Shuffle
    Bomb Upgraders Off (B29 = 0), Oops All Enemies' Wizzrobes, Keese and Bouncers and Oops All
    Bosses' Dodongos, and on 2026-10-15 (beta 6) Shuffle Wood Sword Cave Off (B02 = 0) and Cave
    Shuffle's Non-dungeons Only (C05 = 2), then its Vanilla, Dungeons Only and Random (C05 = 0, 1, 4)
    once the Dead Woods Hint event stayed reachable with Randomize Dead Woods (3f35c57), and on
    2026-10-16 Dungeon Quest's Mixed Quest, Random No Shapes and Random (C02 = 2, 5, 6) and Allow
    Universal Drops In Shapes (B91) on and Random, and on 2026-10-17 Shop Items in the Item Pool's on
    with ZORA 1.0's bait, and on 2026-10-18 (one scan of everything still held, then the released values
    together) the other start items but the wooden sword's, Set Ganon HP to 0, OHKO and Do Not Sort
    Shapes (B41, B53, B86), Pegasus Boots and Highlight No-Drop Rooms, on and Random, and "Most" Enemy
    HP and Boss HP, the sword-heart ranges, the Triforce pieces, Starting Hearts, the pins and Swords:
    Wood Sword Only at the values that passed, and once acceptance E10 and the sword-heart and level 9
    pin refusals landed Start Wood Sword and Permanent Sword Beam (B68, B52) on and Random, Starting
    Hearts 7, 9 and 15, Armos Item: Recorder, Magical Sword Hearts (min) 13 and 14 and Level 9 Items
    Book and White Sword, once redesigned Allow Triforces in Stairways on and Random, and once
    acceptance E11 landed Expanded Dungeon Locations on and Random, and on 2026-10-19 once the logic
    reached the river's west side by them Add Bridges to the River and Add Lost Woods Shortcut (B87,
    B88), on and Random, and on 2026-10-22 beta 8's Level 9 Entry values (C08 = 1 to 12), the Uphill
    Battle set's off values and "?" (B18, B20, B32, B33, B35), Dungeon Room Shuffle Vanilla and Random
    (C14 = 0, 3) and B07, B39, B21 and B37 on and Random, and on 2026-10-23 Do Not Segment Dungeons on
    and Random (100 of 100 seeds each way at e8e5c66). Still held (archipelago.HELD_BACK's comment):
    Swords' No Wood Sword, Swordless and Random, which take away the sword Archipelago's player starts
    with; Replace Book Fire with Explosion on and Random (B47), not compatible. Shuffle Overworld Group (B43) off and "?" are offered. A held value is refused by
    name. Item Shuffle's values and Shuffle Wood Sword are never held: neither is offered at all
    (NOT_OFFERED)."""
    start_items = ("B57", "B59", "B60", "B61", "B63", "B64", "B73", "B77", "B78", "B58", "B62", "B65", "B66",
                   "B67", "B69", "B70", "B71", "B72", "B74", "B75", "B76", "B85")
    released_toggles = ("B41", "B53", "B86", "pegasus_boots", "highlight_no_drop_rooms", "B52", "B68",
                        "allow_triforces_in_stairways", "expanded_dungeon_locations", "B87", "B88",
                        "do_not_segment_dungeons")
    assert archipelago.HELD_BACK == {"C07": {WoodenSwordState.NO_WOODEN_SWORD, WoodenSwordState.SWORDLESS,
                                             WoodenSwordState.RANDOM}, **BETA_8_HELD_BACK, **BETA_9_HELD_BACK}
    assert offered_values("C08") == tuple(range(13))
    assert offered_values("C14") == (0, 1, 2, 3)
    assert all(offered_values(field_id) == tuple(int(state) for state in ThreeState)
               for field_id in BETA_8_RELEASED_TOGGLES)
    assert offered_values("B47") == (ThreeState.OFF,)
    assert offered_values("B43") == tuple(int(state) for state in ThreeState)      # no rule reads it
    assert all(offered_values(field_id) == tuple(int(state) for state in ThreeState) for field_id in released_toggles)
    assert offered_values("C09") == offered_values("C10") == tuple(int(change) for change in HitPointChange)
    assert (offered_values("C20"), offered_values("C21"), offered_values("C22"), offered_values("C23")) == (
        (0, 1, 2), (0, 1, 2), (0, 1, 2, 3, 4), (0, 1, 2, 3, 4))
    assert offered_values("C18") == tuple(range(10))
    assert offered_values("C24") == offered_values("C25") == tuple(range(9))
    assert offered_values("C16") == tuple(range(17))
    assert offered_values("C11") == tuple(PinnedItem)
    assert offered_values("C13") == tuple(PinnedItem)
    assert offered_values("C12") == tuple(item for item in PinnedItem
                                          if item not in (PinnedItem.LADDER, PinnedItem.ANY_ITEM_EXCEPT_HEART_CONTAINER))
    assert offered_values("C26") == offered_values("C27") == tuple(sorted({0, *LEVEL_9_PINS} - BETA_9_HELD_LEVEL_9_PINS))
    assert offered_values("C07") == (WoodenSwordState.NORMAL, WoodenSwordState.WOODEN_SWORD_ONLY)
    assert offered_values("B91") == tuple(int(state) for state in ThreeState)
    assert offered_values("B02") == tuple(int(state) for state in ThreeState)     # "?": beta 8, OW-CAVE-12
    assert offered_values("C05") == (0, 1, 2, 3, 4)
    offered = {spec.id: spec.values for spec in SPECS}
    assert (offered["oops_all_enemies"], offered["oops_all_bosses"]) == ((0, 1, 2, 3), (0, 1))
    assert offered["gatekeeper_bosses"] == (GatekeeperBosses.OFF,)
    assert offered["B29"] == tuple(ThreeState)                 # "?" since beta 9 (FL-DEP-02 rule 4 after its coin)
    assert offered["B23"] == (ThreeState.ON, ThreeState.POSSIBLE)   # "?" beside merchants resolves on (FL-DEP-04)
    # Shop Items in the Item Pool's on, with the bait, passed its scan (2026-10-17)
    assert offered["shop_items_in_pool"] == (ThreeState.OFF, ThreeState.ON)
    assert offered["C01"] == (0, 1, 2, 3, 4)
    assert offered["C04"] == (0, 1, 2, 3)
    assert offered["C02"] == (0, 1, 2, 3, 4, 5, 6)
    assert 1 in offered["C03"]
    assert all(offered[field_id] == tuple(int(state) for state in ThreeState)
               for field_id in ("B81", "B03", "B25", "B26", "B30", "B48", *start_items))
    for option, values in archipelago.HELD_BACK.items():
        for value in values:
            with pytest.raises(OptionsConflict, match=option):
                flag_strings({option: value})


def offered_values(field_id: str) -> tuple[int, ...]:
    return next(spec.values for spec in SPECS if spec.id == field_id)


@pytest.mark.parametrize(("option", "value"), SINGLE_VALUES)
def test_each_value_alone_round_trips_or_is_a_named_conflict(option: str, value: int) -> None:
    spec = next(spec for spec in SPECS if spec.id == option)
    try:
        strings = flag_strings({option: value})
    except OptionsConflict as conflict:
        assert EXPECTED_CONFLICTS.get((option, value), "\x00") in str(conflict), conflict
        return
    assert (option, value) not in EXPECTED_CONFLICTS
    assert value_in(strings, spec) == value
    plan(strings[0], 1, strings[1])                                # no "not produced" refusal


@pytest.mark.slow
@pytest.mark.parametrize(("option", "value"), [pair for pair in SINGLE_VALUES if pair not in EXPECTED_CONFLICTS])
def test_each_value_alone_generates(base: bytes, option: str, value: int) -> None:
    flags, zora = flag_strings({option: value})
    build(plan(flags, 1, zora), base)


def test_each_conflict_resolves_with_its_counterpart() -> None:
    off, on = int(ThreeState.OFF), int(ThreeState.ON)
    flag_strings({"progressive_items": 1, "B09": off})
    flag_strings({"randomize_magical_sword": 1, "B10": off})
    flag_strings({"randomize_magical_sword": 1, "magical_sword_hearts_highest": 3})     # at most 12 hearts
    flag_strings({"add_l4_sword": on, "progressive_items": 1, "B09": off})
    flag_strings({"extra_power_bracelet_blocks": on, "B04": off})


def test_merchant_toll_is_kept_as_given() -> None:
    """FL-DEP-06: B22 off leaves B23 on (the one value offered for it), with no note."""
    flags, _zora = flag_strings({"B22": int(ThreeState.OFF)})
    assert decode(flags).toggle("B23") is ThreeState.ON
    assert option_corrections({"B22": int(ThreeState.OFF)}) == option_corrections({}) == []


def test_values_must_be_offered() -> None:
    with pytest.raises(OptionsConflict, match="Enemy Drop Groups"):
        flag_strings({"B38": 1})                 # Shuffle Enemy Drop Groups: not produced
    with pytest.raises(OptionsConflict, match="unknown options"):
        flag_strings({"B82": 1})


def test_a_new_flag_field_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    """option_fields reads zora/flags' tables when called: a field added there is offered, at its
    first supported value until the default preset holds it."""
    new_toggle = ToggleField("B99", "A new switch")
    supported = flag_form.supported_values
    monkeypatch.setattr(flag_form, "ALL_FIELDS", (*flag_form.ALL_FIELDS, new_toggle))
    monkeypatch.setattr(flag_form, "supported_values",
                        lambda field: (ThreeState.OFF, ThreeState.ON) if field == new_toggle else supported(field))
    monkeypatch.setattr(flag_form, "value_label", lambda field, value: str(value))
    new_extra = {"name": "a_new_extra", "kind": "toggle", "label": "A New Extra", "help": "New."}
    monkeypatch.setattr(zora_form, "FIELDS", (*zora_form.FIELDS, new_extra))
    specs = {spec.id: spec for spec in option_fields()}
    assert specs["B99"].values == (0, 1) and specs["B99"].default == 0
    assert specs["a_new_extra"].kind == "switch" and specs["a_new_extra"].default == 0


def test_disable_custom_music_is_never_offered() -> None:
    """Disable Custom Music (a race setting for randomized music, which Archipelago's games do not have)
    is a hidden option: off passes, on is refused with the reason."""
    [spec] = [spec for spec in archipelago.never_offered_fields() if spec.key == "disable_custom_music"]
    assert spec.description == archipelago.ZORA_FORCED_OFF["disable_custom_music"]
    assert archipelago.never_offered_refusal("disable_custom_music", "off") is None
    refusal = archipelago.never_offered_refusal("disable_custom_music", "on")
    assert refusal is not None and "randomized music" in refusal
