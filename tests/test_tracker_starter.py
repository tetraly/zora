"""The starter tracker file (zora_export/tracker_file.py starter_file): what a seed made with Spoiler Log Detail
Level None gives from "Download tracker file", built only from the flags spec's tracker hints
(zora_export/tracker_hints.py, the rules docs/flags-api/zora-flags.json publishes): pinned items in their places,
start items, the modifiers applied (Swap Swords and Rings, Pegasus Boots, Progressive Items, the bomb upgrade),
and nothing that depends on the seed. Also Swordlish's effect on the sword hints (docs/flags-api.md "Swords").
tests/tracker_load/ loads a starter file in ZoraTracker itself."""
from __future__ import annotations

import json
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec, zora_flags
from zora.flags.fields import ItemShuffleScope, ThreeState, WoodenSwordState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import Swordlish, ZoraFlags
from zora.version import ZORA_VERSION
from zora_export.tracker_file import ITEM_IDS, LEVEL_9, starter_file
from zora_export.tracker_hints import Status, flag_digits, start_knowledge, status, tracker_hints

DEALING = int(ItemShuffleScope.FULL)
NO_LIMIT = 0                      # Max Start Items (C17) value 0: every chosen start item
ON, OFF, RANDOM = int(ThreeState.ON), int(ThreeState.OFF), int(ThreeState.POSSIBLE)
# Pin values (FORCED_ITEM_OPTIONS' order, the spec's pins.values): Book, Boomerang, White Sword, Non-Heart
BOOK, BOOMERANG, WHITE_SWORD, NON_HEART = 1, 2, 15, 16


def z1r(**changes: int) -> str:
    """The page's starting Z1R string with these fields changed (Item Shuffle dealing unless given)."""
    changes = {"C06": DEALING, "C17": NO_LIMIT, **changes}
    settings = codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    options = {key: value for key, value in changes.items() if key.startswith("C")}
    toggles = {key: ThreeState(value) for key, value in changes.items() if key.startswith("B")}
    return codec.encode(settings.updated(options=options, toggles=toggles))


def zora(**fields: Any) -> str:
    return zora_flags.encode(ZoraFlags(**fields))


def box(save: dict[str, Any], name: str) -> int:
    return int(save["Items"][name]["CellCurrent"])


def starts(save: dict[str, Any]) -> set[str]:
    blocks = (save["StartingItemsAndExtras"], save["PlayerProgressAndTakeAnyHearts"])
    return {name for block in blocks for name, value in block.items() if value is True}


def test_two_seeds_give_the_same_file_but_the_seed() -> None:
    flags, extras = z1r(C11=BOOK, C13=WHITE_SWORD, B58=ON, B70=ON), zora(pegasus_boots=ThreeState.ON)
    first, second = starter_file(flags, extras, 1), starter_file(flags, extras, 2)
    assert (first["Seed"], second["Seed"]) == ("1", "2")
    assert {**first, "Seed": None} == {**second, "Seed": None}
    assert (first["Flags"], first["ZoraFlags"], first["ZoraVersion"]) == (flags, extras, ZORA_VERSION)
    assert first["Notes"] == "" and first["TimeInSeconds"] == 0
    json.dumps(first)                                    # a JSON file as the full one is


def test_a_start_magical_sword_is_set_wherever_the_tracker_reads_it() -> None:
    """ZoraTracker reads a starting Magical Sword from StartingItemsAndExtras; the run-progress block holds it too."""
    save = starter_file(z1r(B70=ON), "", 7)
    assert save["StartingItemsAndExtras"]["PlayerHasMagicalSword"] is True
    assert save["PlayerProgressAndTakeAnyHearts"]["PlayerHasMagicalSword"] is True
    blank = starter_file(z1r(), "", 7)
    assert not blank["StartingItemsAndExtras"]["PlayerHasMagicalSword"]
    assert not blank["PlayerProgressAndTakeAnyHearts"]["PlayerHasMagicalSword"]


def test_every_start_item_is_set_wherever_the_tracker_reads_it() -> None:
    """Each start item alone sets exactly its fields: the Magical Sword two, every other one."""
    from zora_export.tracker_file import START_ITEM_FIELDS
    for entry in tracker_hints()["start_items"]["fields"]:
        save = starter_file(z1r(**{entry["field"]: ON}), "", 7)
        found = {(block, name) for block in ("StartingItemsAndExtras", "PlayerProgressAndTakeAnyHearts")
                 for name, value in save[block].items() if value is True}
        assert found == set(START_ITEM_FIELDS.get(entry["item"], ())), entry


def test_zora_version_is_the_release_version() -> None:
    extras = zora(pegasus_boots=ThreeState.ON)
    save = starter_file(z1r(), extras, 7)
    assert save["ZoraVersion"] == ZORA_VERSION and save["ZoraFlags"] == extras
    assert save["ZoraVersion"] != extras.split(".")[0]


def test_a_pinned_item_is_in_its_place() -> None:
    save = starter_file(z1r(C11=BOOK, C12=BOOMERANG, C26=BOOK), "", 7)
    assert box(save, "ArmosBox") == ITEM_IDS["Book"]
    assert box(save, "LadderBox") == ITEM_IDS["Boomerang"]
    assert box(save, "WhiteSwordBox") == -1                       # not pinned
    assert save["Items"]["Dungeons"][LEVEL_9 - 1]["Boxes"][0]["CellCurrent"] == ITEM_IDS["Book"]
    assert box(starter_file(z1r(C11=NON_HEART), "", 7), "ArmosBox") == -1     # any item but a Heart Container


def test_random_per_seed_stays_blank() -> None:
    """Item Shuffle: Random (without No Vanilla) decides per seed whether the pins act; Item Shuffle: None does
    nothing; a start item at Random or under a limit that may drop it is unknown."""
    assert box(starter_file(z1r(C06=int(ItemShuffleScope.RANDOM), C11=BOOK), "", 7), "ArmosBox") == -1
    assert box(starter_file(z1r(C06=int(ItemShuffleScope.NONE), C02=0, C11=BOOK), "", 7), "ArmosBox") == -1
    assert starts(starter_file(z1r(B58=RANDOM, B57=ON), "", 7)) == {"PlayerHasRaft"}
    assert starts(starter_file(z1r(C17=2, B58=ON, B57=ON), "", 7)) == set()      # limit 1, two chosen
    assert starts(starter_file(z1r(C17=3, B58=ON, B57=ON), "", 7)) == {"PlayerHasBow", "PlayerHasRaft"}


def test_swap_swords_and_rings_trades_a_pinned_sword() -> None:
    swap = zora(swap_swords_and_rings=ThreeState.ON)
    assert box(starter_file(z1r(C13=WHITE_SWORD), swap, 7), "WhiteSwordBox") == ITEM_IDS["Blue Ring"]
    # a pair with a start item is not swapped; one whose start item the seed draws is unknown
    assert box(starter_file(z1r(C13=WHITE_SWORD, B75=ON), swap, 7), "WhiteSwordBox") == ITEM_IDS["White Sword"]
    assert box(starter_file(z1r(C13=WHITE_SWORD, B75=RANDOM), swap, 7), "WhiteSwordBox") == -1
    assert box(starter_file(z1r(C13=WHITE_SWORD), zora(swap_swords_and_rings=ThreeState.POSSIBLE), 7),
               "WhiteSwordBox") == -1


@pytest.mark.parametrize(("boots", "written"), [(ThreeState.OFF, 0), (ThreeState.ON, 1), (ThreeState.POSSIBLE, 2)])
def test_pegasus_boots_is_boots_replace_boomerangs(boots: ThreeState, written: int) -> None:
    """Pegasus Boots Off, On and Random give ZoraTracker's BootsReplaceBoomerangs 0, 1 and 2 (the spec's
    pegasus_boots modifier: off, applies, unknown)."""
    save = starter_file(z1r(), zora(pegasus_boots=boots), 7)
    assert save["Overworld"]["BootsReplaceBoomerangs"] == written


def test_pegasus_boots_renames_the_boomerangs() -> None:
    """With Pegasus Boots On the boots take the boomerangs' boxes and start items (BootsReplaceBoomerangs 1 draws
    them as boots); with Random the seed decides what they are, so they stay blank."""
    boots = starter_file(z1r(C11=BOOMERANG, B77=ON), zora(pegasus_boots=ThreeState.ON), 7)
    assert box(boots, "ArmosBox") == ITEM_IDS["Pegasus Boots"] == ITEM_IDS["Boomerang"]
    assert "PlayerHasBoomerang" in starts(boots)
    unknown = starter_file(z1r(C11=BOOMERANG, B77=ON), zora(pegasus_boots=ThreeState.POSSIBLE), 7)
    assert box(unknown, "ArmosBox") == -1 and "PlayerHasBoomerang" not in starts(unknown)
    plain = starter_file(z1r(C11=BOOMERANG, B77=ON), "", 7)
    assert box(plain, "ArmosBox") == ITEM_IDS["Boomerang"] and "PlayerHasBoomerang" in starts(plain)


def test_progressive_items_leaves_start_items_as_they_are() -> None:
    """A start item is the item itself with Progressive Items on, as the ROM's starting table holds it."""
    progressive = zora(progressive_items=True)
    sword = {"PlayerHasMagicalSword"}
    assert starts(starter_file(z1r(B70=ON), progressive, 7)) == sword == starts(starter_file(z1r(B70=ON), "", 7))
    assert starts(starter_file(z1r(B69=ON, B70=ON, B74=ON), progressive, 7)) == {
        "PlayerHasWhiteSword", "PlayerHasMagicalSword", "PlayerHasRedCandle"}


def test_the_bomb_upgrade_follows_the_sword_state() -> None:
    def bomb_upgrade(state: WoodenSwordState) -> bool:
        return bool(starter_file(z1r(C07=int(state)), "", 7)["IsWSMSReplacedByBUSeed"])
    assert bomb_upgrade(WoodenSwordState.WOODEN_SWORD_ONLY) and bomb_upgrade(WoodenSwordState.SWORDLESS)
    assert not bomb_upgrade(WoodenSwordState.NORMAL) and not bomb_upgrade(WoodenSwordState.RANDOM)


@pytest.mark.parametrize(("swordlish", "known"), [(Swordlish.OFF, True), (Swordlish.ON, True),
                                                   (Swordlish.RANDOM, False)])
def test_swordlish_random_leaves_the_sword_hints_unknown(swordlish: Swordlish, known: bool) -> None:
    """Swordlish: Random can land on Wood Sword Only, No Wood Sword or Swordless, so the swap and the bomb upgrade
    are unknown; Swordlish: On needs Swords: Normal (SWORDLISH_NEEDS_NORMAL), so both stay known."""
    digits = flag_digits(z1r(), zora(swordlish=swordlish, swap_swords_and_rings=ThreeState.ON))
    rules = {modifier["id"]: status(modifier, digits) for modifier in tracker_hints()["modifiers"]}
    assert rules["swap_swords_and_rings"] is (Status.APPLIES if known else Status.UNKNOWN)
    assert rules["bomb_upgrade"] is (Status.OFF if known else Status.UNKNOWN)
    assert start_knowledge(z1r(C13=WHITE_SWORD), zora(swordlish=swordlish)).bomb_upgrade is (False if known else None)


def test_the_spec_publishes_the_same_rules() -> None:
    """The starter file reads the rules the spec publishes: the committed spec's hints are tracker_hints()."""
    from pathlib import Path
    spec = Path(__file__).resolve().parent.parent / "docs" / "flags-api" / "zora-flags.json"
    if not spec.exists():
        pytest.skip("the flags spec is not part of this tree")
    assert json.loads(spec.read_text())["tracker_hints"] == json.loads(json.dumps(tracker_hints()))


# The cross-check against the ROM: start fields (no Max Start Items limit, so every one is certain), each with
# Progressive Items, Swap Swords and Rings and Pegasus Boots on and off
START_FIELD_SETS = {
    "every upgrade line": ("B68", "B69", "B70", "B71", "B72", "B73", "B74", "B75", "B76", "B77", "B78"),
    "the best sword and ring": ("B70", "B76"),
    "the swapped pairs' lower items": ("B69", "B75"),
    "items of no line": ("B57", "B58", "B59", "B62", "B65", "B66", "B67"),
}


@needs_base_rom
@pytest.mark.parametrize("fields", START_FIELD_SETS.values(), ids=START_FIELD_SETS.keys())
def test_the_spec_predicts_the_roms_starting_table(fields: tuple[str, ...]) -> None:
    """The start items the spec's rule predicts (zora_export.tracker_hints.start_knowledge, certain here) are the
    items the ROM's starting table holds, under every mix of the three modifiers that touch start items."""
    from zora.generate.pipeline import generate_rom
    from zora.model.item_names import ITEM_NAMES, PEGASUS_BOOTS_NAMES
    from zora.rom.base_rom import remember_repo_base_rom
    from zora.rom.parse.rom_file import parse_rom
    from zora.rom.start_items import items_in_table, start_table
    by_name = {name: item for names in (ITEM_NAMES, PEGASUS_BOOTS_NAMES) for item, name in names.items()}
    flags = z1r(**dict.fromkeys(fields, ON))
    base = remember_repo_base_rom()
    for progressive in (False, True):
        for swap in (ThreeState.OFF, ThreeState.ON):
            for boots in (ThreeState.OFF, ThreeState.ON):
                extras = zora(progressive_items=progressive, swap_swords_and_rings=swap, pegasus_boots=boots)
                predicted = start_knowledge(flags, extras).start_items
                assert len(predicted) == len(fields), (extras, predicted)
                rom = generate_rom(flags, 1, base, zora_flag_string=extras).rom
                table = start_table([by_name[name] for name in predicted], 3, 3)
                assert parse_rom(rom).start_items == items_in_table(table), (extras, predicted)
