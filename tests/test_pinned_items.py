"""The item pins at their values (C11, C13, C26, C27; post-shapes-b1.md PS-ITEM-12): an item forced
to the Armos slot, the white-sword cave, or level 9's first and second pool places, or Non-Heart (16,
a heart container redrawn); level 9's pins not at the long items or the Wand; two pins naming one
item refused (FL-DEP-01 rule 2); pins act only inside a deal (none under C06 = 0); the ZORA extras'
later exchanges leave a pinned place alone. Pick 5's pins: the Book at the Armos slot, a heart
container in the white-sword cave and no heart container in level 9."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec, zora_flags
from zora.flags.dependencies import refusals
from zora.flags.fields import ItemShuffleScope, OptionField, ThreeState
from zora.flags.form import metadata
from zora.flags.support import LEVEL_9_PINS, Support, support
from zora.generate.steps.extra_pool_items import item_cellars
from zora.generate.pipeline import Built, FlagsRefused, build, plan
from zora.generate.steps.shuffle_items import FORCED_ITEM_OPTIONS
from zora.model.enums import Item
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5
SEEDS = range(1, 9)
BOOK, HEART, MAGICAL_KEY, WOOD_BOOMERANG, NON_HEART = 1, 4, 7, 2, 16
LONG_ITEMS_AND_WAND = {3, 5, 8, 9, 10, 14}
# Without the extras' exclusion, seed 26's magical-sword join took the pinned Book out of level 9
# (one of seeds 1-40)
SEED_WHOSE_EXTRA_TOOK_THE_PIN = 26
PICK_5_PINS = {"C11": BOOK, "C13": HEART, "C26": NON_HEART, "C27": NON_HEART}


def flags(**options: int) -> str:
    return codec.encode(DEFAULT_SETTINGS.updated(options=options))


@pytest.mark.parametrize("field_id", ["C11", "C13", "C26", "C27"])
def test_the_supported_values(field_id: str) -> None:
    supported = {index for index in range(17)
                 if support(DEFAULT_SETTINGS.updated(options={field_id: index}))[field_id] is Support.SUPPORTED}
    assert supported == set(range(17))
    if field_id in ("C26", "C27"):
        # the beta 9 export (faabdd4): level 9's places at the long items and the Wand too, refused
        # with Allow Important Items in 9 off (FL-DEP-01)
        assert supported == {0} | LEVEL_9_PINS and LONG_ITEMS_AND_WAND <= supported


def test_the_coast_pin_at_every_item_but_the_ladder() -> None:
    """Beta 8 export (PS-ITEM-12): C12 = 1 to 4 and 6 to 15 are produced, and since the beta 9 export
    (faabdd4) Non-Heart (C12 = 16) too; the Ladder is refused (FL-DEP-01 rule 1)."""
    assert support(DEFAULT_SETTINGS.updated(options={"C12": BOOK}))["C12"] is Support.SUPPORTED
    assert support(DEFAULT_SETTINGS.updated(options={"C12": NON_HEART}))["C12"] is Support.SUPPORTED


def test_two_pins_of_one_item_are_refused() -> None:
    rules = [refusal.rule for refusal in refusals(DEFAULT_SETTINGS.updated(options={"C11": BOOK, "C26": BOOK}))]
    assert rules == ["FL-DEP-01 rule 2"]
    assert not refusals(DEFAULT_SETTINGS.updated(options={"C11": NON_HEART, "C26": NON_HEART}))


@cache
def _built(flag_string: str, seed: int, zora: str = "") -> Built:
    return build(plan(flag_string, seed, zora), remember_repo_base_rom())


def _level_9_items(built: Built) -> list[Item]:
    level_9: Level = built.world.levels[8]
    rooms = [level_9.block.room(room_num).item_info.item for room_num in level_9.room_nums]
    return [item for item in rooms if item is not None] + [cellar.item for cellar in item_cellars(level_9)
                                                           if cellar.item is not None]


def _cave_item(built: Built, slot: str) -> int:
    state = built.result.item_shuffle_result
    assert state is not None
    return state.caves[slot] & 0x3F


@needs_base_rom
def test_pick_5s_pins_in_seeds() -> None:
    for seed in SEEDS:
        built = _built(flags(**PICK_5_PINS), seed)
        assert _cave_item(built, "armos") == Item.BOOK
        assert _cave_item(built, "white_sword") == Item.HEART_CONTAINER
        assert Item.HEART_CONTAINER not in _level_9_items(built), seed


@needs_base_rom
def test_two_items_pinned_in_level_9() -> None:
    for seed in SEEDS:
        items = _level_9_items(_built(flags(C26=MAGICAL_KEY, C27=WOOD_BOOMERANG), seed))
        assert Item.MAGICAL_KEY in items and Item.WOOD_BOOMERANG in items, seed


@needs_base_rom
def test_non_heart_cave_pins() -> None:
    for seed in SEEDS:
        built = _built(flags(C11=NON_HEART, C13=NON_HEART), seed)
        assert Item.HEART_CONTAINER not in (_cave_item(built, "armos"), _cave_item(built, "white_sword"))


@needs_base_rom
def test_no_deal_no_pins() -> None:
    """PS-ITEM-10: under C06 = 0 the Armos slot keeps PRG0's Power Bracelet."""
    for seed in SEEDS[:3]:
        built = _built(flags(C11=BOOK, C06=ItemShuffleScope.NONE), seed)
        assert _cave_item(built, "armos") == Item.POWER_BRACELET


@needs_base_rom
def test_the_extras_leave_a_pinned_place_alone() -> None:
    """Randomize Magical Sword joins the pool after the deal; level 9's pinned Book stays there (its
    magical-sword cave capped at 12 hearts, C23 = 2, as that extra needs)."""
    zora = zora_flags.encode(zora_flags.ZoraFlags(randomize_magical_sword=True))
    for seed in (*SEEDS, SEED_WHOSE_EXTRA_TOOK_THE_PIN):
        built = _built(flags(C26=BOOK, C23=2), seed, zora)
        assert Item.BOOK in _level_9_items(built), seed


# --- level 9's own key pinned inside it (the 2026-10-18 Archipelago scan) ------------------------

# Seeds that never generated, every rejection E1's: Level 9 Item 2 = Book with Book to Understand
# NPCs and Randomize Lost Hills on (level 5's door past the maze); Level 9 Item 1 = White Sword
# with Level 9 Entrance = Level 4 sword
BOOK_SCAN = ("XXPBzNL!0G46t3GisCmosaeoufP65EEkaeDNK", "5.hLEb3", 20)
WHITE_SWORD_SCAN = ("7vrMEHCzv!gKQUDho9oNydrgMTXCgsX24nOntBaW", "5.3ebVGG", 22)
MAZES = ("randomize_lost_hills", "randomize_dead_woods")


def test_the_pin_values_and_names_are_the_tables() -> None:
    from zora.flags.form import field_label
    assert (FORCED_ITEM_OPTIONS[zora_flags.BOOK_PIN], FORCED_ITEM_OPTIONS[zora_flags.WHITE_SWORD_PIN]) == (
        Item.BOOK, Item.WHITE_SWORD)
    assert {pin: field_label(pin) for pin in zora_flags.LEVEL_9_PIN_NAMES} == zora_flags.LEVEL_9_PIN_NAMES


@pytest.mark.parametrize(("strings", "message"), [
    (BOOK_SCAN, "Level 9 Item 2 = Book cannot be used with Book to Understand NPCs"),
    (WHITE_SWORD_SCAN, "Level 9 Item 1 = White Sword cannot be used with Level 9 Entrance = Level 4 sword"),
], ids=["book", "white-sword"])
def test_the_scans_strings_are_refused_before_generation(strings: tuple[str, str, int], message: str) -> None:
    flags, zora, seed = strings
    with pytest.raises(FlagsRefused, match=message):
        plan(flags, seed, zora)


@pytest.mark.parametrize("pin", list(zora_flags.LEVEL_9_PIN_NAMES))
@pytest.mark.parametrize("book", list(ThreeState))
@pytest.mark.parametrize(("lost_hills", "dead_woods"), [(a, b) for a in ThreeState for b in ThreeState])
def test_the_book_pin_is_refused_exactly_while_a_maze_may_need_the_book(
        pin: OptionField, book: ThreeState, lost_hills: ThreeState, dead_woods: ThreeState) -> None:
    z1r = DEFAULT_SETTINGS.updated(options={pin.id: zora_flags.BOOK_PIN}, toggles={"B48": book})
    flags = zora_flags.ZoraFlags(randomize_lost_hills=lost_hills, randomize_dead_woods=dead_woods)
    may_hide = book is not ThreeState.OFF and not (lost_hills is dead_woods is ThreeState.OFF)
    assert [names for _message, names in zora_flags.level_9_pin_conflicts(flags, z1r)] == (
        [(pin.id, "B48", *MAZES)] if may_hide else [])


@pytest.mark.parametrize("pin", list(zora_flags.LEVEL_9_PIN_NAMES))
def test_the_white_sword_pin_is_refused_only_with_the_sword_entrance(pin: OptionField) -> None:
    z1r = DEFAULT_SETTINGS.updated(options={pin.id: zora_flags.WHITE_SWORD_PIN})
    for entrance in (False, True):
        flags = zora_flags.ZoraFlags(level_9_entrance_sword=entrance)
        assert [names for _message, names in zora_flags.level_9_pin_conflicts(flags, z1r)] == (
            [(pin.id, "level_9_entrance_sword")] if entrance else [])
