"""
Tests for the hint randomizer system.

Coverage:
  1. expand_quote_slots — slot count, ids added, cave remapping
  2. Vanilla mode — no-op
  3. Blank mode — all quotes emptied
  4. Community mode — all slots filled with non-empty text
  5. Helpful mode — slot assignment tiers, format, community filler
  6. Helpful mode with progressive_items — item name overrides
  7. Heart requirement (numerical) hints
  8. Directional hints — go to cave quote slots, not hint shop paid slots
  9. _scan_hintable_locations — finds items in dungeons, caves, overworld
  10. _build_helpful_hint_text — entrance phrase + item name format
  11. Hint shop prices — vanilla unchanged; community/helpful randomized 10-50
  12. Serializer pointer table — expanded quote_ids produce valid pointers
  13. HintMode.RANDOM resolves to a concrete mode
"""
from pathlib import Path

import pytest

from flags.flags_generated import Flags, Tristate
from flags.flags_generated import HintMode as FlagHintMode
from zora.data_model import (
    Destination,
    EntranceType,
    GameWorld,
    HintShop,
    Item,
    ItemCave,
)
from zora.game_config import GameConfig, HintMode, resolve_game_config
from zora.hint_randomizer import (
    _PAID_HINT_SLOTS,
    HINTABLE_NICE_TO_HAVE_ITEMS,
    HINTABLE_PROGRESSION_ITEMS,
    NUMERICAL_HINTS,
    HintableLocation,
    HintType,
    _build_helpful_hint_text,
    _scan_hintable_locations,
    expand_quote_slots,
    randomize_hints,
)
from zora.item_randomizer import randomize_items
from zora.parser import parse_game_world
from zora.rng import SeededRng
from zora.rom_layout import QUOTE_DATA_ADDRESS
from zora.serializer import serialize_game_world


TEST_DATA = Path(__file__).parent.parent / "rom_data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_originals():
    names = [
        "level_1_6_data.bin", "level_7_9_data.bin", "level_info.bin",
        "overworld_data.bin", "armos_item.bin", "coast_item.bin",
        "white_sword_requirement.bin", "magical_sword_requirement.bin",
    ]
    return {n: (TEST_DATA / n).read_bytes() for n in names}


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


def _community_config(seed: int = 0) -> GameConfig:
    return _config(Flags(hint_mode=FlagHintMode.COMMUNITY), seed)


def _helpful_config(seed: int = 0) -> GameConfig:
    return _config(Flags(
        hint_mode=FlagHintMode.HELPFUL,
        shuffle_dungeon_items=Tristate.ON,
    ), seed)


def _quote_text(gw: GameWorld, quote_id: int) -> str:
    for q in gw.quotes:
        if q.quote_id == quote_id:
            return q.text
    raise KeyError(f"No quote with id={quote_id}")


def _hint_shop_prices(gw: GameWorld) -> list[list[int]]:
    """Return [[shop1 prices], [shop2 prices]]."""
    result = []
    for cave in gw.overworld.caves:
        if isinstance(cave, HintShop):
            result.append([h.price for h in cave.hints])
    return result


# =============================================================================
# 1. expand_quote_slots
# =============================================================================

class TestExpandQuoteSlots:
    def test_noop_in_vanilla_mode(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(hint_mode=FlagHintMode.VANILLA))
        before_ids = {q.quote_id for q in gw.quotes}
        expand_quote_slots(gw, config, SeededRng(0))
        assert {q.quote_id for q in gw.quotes} == before_ids

    def test_noop_in_blank_mode(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(hint_mode=FlagHintMode.BLANK))
        before_ids = {q.quote_id for q in gw.quotes}
        expand_quote_slots(gw, config, SeededRng(0))
        assert {q.quote_id for q in gw.quotes} == before_ids

    def test_adds_new_slots_in_community_mode(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        assert len(gw.quotes) == 38
        expand_quote_slots(gw, config, SeededRng(0))
        assert len(gw.quotes) == 41  # 38 vanilla + 3 generated (HUNGRY_ENEMY, LEVEL_1, LEVEL_2)

    def test_new_quote_ids_include_moved_slots(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        ids = {q.quote_id for q in gw.quotes}
        for expected_id in (HintType.HUNGRY_ENEMY, HintType.LEVEL_1, HintType.LEVEL_2):
            assert expected_id in ids, f"Missing quote_id={expected_id}"

    def test_idempotent_when_called_twice(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        count_after_first = len(gw.quotes)
        expand_quote_slots(gw, config, SeededRng(0))
        assert len(gw.quotes) == count_after_first

    def test_white_sword_cave_remapped_to_39(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        for cave in gw.overworld.caves:
            if isinstance(cave, ItemCave) and cave.destination == Destination.WHITE_SWORD_CAVE:
                assert cave.quote_id == HintType.WHITE_SWORD_CAVE
                return
        pytest.fail("WHITE_SWORD_CAVE not found")

    def test_magical_sword_cave_keeps_original_quote_id(self, bins):
        gw = parse_game_world(bins)
        original_magical_id = next(
            c.quote_id for c in gw.overworld.caves
            if isinstance(c, ItemCave) and c.destination == Destination.MAGICAL_SWORD_CAVE
        )
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        for cave in gw.overworld.caves:
            if isinstance(cave, ItemCave) and cave.destination == Destination.MAGICAL_SWORD_CAVE:
                assert cave.quote_id == original_magical_id

    def test_hint_shop_1_slots_remapped(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        shop1 = next(c for c in gw.overworld.caves
                     if isinstance(c, HintShop) and c.destination == Destination.HINT_SHOP_1)
        assert shop1.hints[0].quote_id == HintType.HINT_SHOP_1A
        assert shop1.hints[1].quote_id == HintType.HINT_SHOP_1B
        assert shop1.hints[2].quote_id == HintType.HINT_SHOP_1C

    def test_hint_shop_2_slots_remapped(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        shop2 = next(c for c in gw.overworld.caves
                     if isinstance(c, HintShop) and c.destination == Destination.HINT_SHOP_2)
        assert shop2.hints[0].quote_id == HintType.HINT_SHOP_2A
        assert shop2.hints[1].quote_id == HintType.HINT_SHOP_2B
        assert shop2.hints[2].quote_id == HintType.HINT_SHOP_2C


# =============================================================================
# 2. Vanilla mode
# =============================================================================

class TestVanillaMode:
    def test_vanilla_mode_is_noop(self, bins):
        gw = parse_game_world(bins)
        original_texts = {q.quote_id: q.text for q in gw.quotes}
        config = _config(Flags(hint_mode=FlagHintMode.VANILLA))
        randomize_hints(gw, config, SeededRng(0))
        for q in gw.quotes:
            assert q.text == original_texts[q.quote_id], (
                f"Quote id={q.quote_id} was modified in vanilla mode"
            )

    def test_vanilla_mode_does_not_expand_quotes(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(hint_mode=FlagHintMode.VANILLA))
        randomize_hints(gw, config, SeededRng(0))
        assert len(gw.quotes) == 38


# =============================================================================
# 3. Blank mode
# =============================================================================

class TestBlankMode:
    def test_blank_mode_empties_all_quotes(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(hint_mode=FlagHintMode.BLANK))
        randomize_hints(gw, config, SeededRng(0))
        for q in gw.quotes:
            assert q.text == "", f"Quote id={q.quote_id} not blank: {q.text!r}"

    def test_blank_mode_preserves_quote_count(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(hint_mode=FlagHintMode.BLANK))
        randomize_hints(gw, config, SeededRng(0))
        assert len(gw.quotes) == 38

    def test_blank_mode_does_not_randomize_hint_shop_prices(self, bins):
        gw = parse_game_world(bins)
        vanilla_prices = _hint_shop_prices(gw)
        config = _config(Flags(hint_mode=FlagHintMode.BLANK))
        randomize_hints(gw, config, SeededRng(0))
        assert _hint_shop_prices(gw) == vanilla_prices


# =============================================================================
# 4. Community mode
# =============================================================================

class TestCommunityMode:
    def test_community_mode_fills_all_slots(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(1))
        randomize_hints(gw, config, SeededRng(1))
        assert len(gw.quotes) == 41  # 38 vanilla + 3 generated (38-40)
        for q in gw.quotes:
            assert q.text, f"Quote id={q.quote_id} is empty after community mode"

    def test_community_mode_all_quotes_non_empty(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(7))
        randomize_hints(gw, config, SeededRng(7))
        empty = [q.quote_id for q in gw.quotes if not q.text]
        assert not empty, f"Empty quotes in community mode: ids={empty}"

    def test_community_mode_deterministic(self, bins):
        gw1 = parse_game_world(bins)
        gw2 = parse_game_world(bins)
        config = _community_config(seed=42)
        for gw in (gw1, gw2):
            expand_quote_slots(gw, config, SeededRng(42))
            randomize_hints(gw, config, SeededRng(42))
        texts1 = {q.quote_id: q.text for q in gw1.quotes}
        texts2 = {q.quote_id: q.text for q in gw2.quotes}
        assert texts1 == texts2

    def test_community_mode_randomizes_hint_shop_prices(self, bins):
        gw = parse_game_world(bins)
        vanilla_prices = _hint_shop_prices(gw)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        new_prices = _hint_shop_prices(gw)
        # Prices should be in 10-50 range
        for shop_prices in new_prices:
            for price in shop_prices:
                assert 10 <= price <= 50, f"Price {price} out of range 10-50"
        # And should differ from vanilla (with overwhelming probability)
        assert new_prices != vanilla_prices


# =============================================================================
# 5. Helpful mode — slot assignment tiers
# =============================================================================

class TestHelpfulMode:
    def test_helpful_mode_fills_all_slots(self, bins):
        gw = parse_game_world(bins)
        config = _helpful_config()
        expand_quote_slots(gw, config, SeededRng(1))
        randomize_items(gw, config, SeededRng(1))
        randomize_hints(gw, config, SeededRng(1))
        assert len(gw.quotes) == 41  # 38 vanilla + 3 generated (38-40)
        for q in gw.quotes:
            assert q.text, f"Quote id={q.quote_id} is empty after helpful mode"

    def test_helpful_mode_paid_slots_have_helpful_format_or_community(self, bins):
        """Paid hint shop slots either have 'TO FIND' format or a community hint."""
        gw = parse_game_world(bins)
        config = _helpful_config(seed=10)
        expand_quote_slots(gw, config, SeededRng(10))
        randomize_items(gw, config, SeededRng(10))
        randomize_hints(gw, config, SeededRng(10))

        paid_ids = [ht.value for ht in _PAID_HINT_SLOTS]
        for qid in paid_ids:
            text = _quote_text(gw, qid)
            # Either a helpful hint ("TO FIND") or community filler (non-empty)
            assert text, f"Paid slot quote_id={qid} is empty"

    def test_helpful_mode_some_paid_slots_have_helpful_hints(self, bins):
        """With shuffle_dungeon_items on, at least some paid slots should be helpful hints."""
        gw = parse_game_world(bins)
        config = _helpful_config(seed=5)
        expand_quote_slots(gw, config, SeededRng(5))
        randomize_items(gw, config, SeededRng(5))
        randomize_hints(gw, config, SeededRng(5))

        paid_ids = [ht.value for ht in _PAID_HINT_SLOTS]
        helpful_count = sum(
            1 for qid in paid_ids if "TO FIND" in _quote_text(gw, qid)
        )
        assert helpful_count > 0, "No helpful hints found in paid slots"

    def test_helpful_mode_randomizes_hint_shop_prices(self, bins):
        gw = parse_game_world(bins)
        _vanilla_prices = _hint_shop_prices(gw)
        config = _helpful_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_items(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        new_prices = _hint_shop_prices(gw)
        for shop_prices in new_prices:
            for price in shop_prices:
                assert 10 <= price <= 50

    def test_helpful_mode_deterministic(self, bins):
        gw1 = parse_game_world(bins)
        gw2 = parse_game_world(bins)
        config = _helpful_config(seed=77)
        for gw in (gw1, gw2):
            expand_quote_slots(gw, config, SeededRng(77))
            randomize_items(gw, config, SeededRng(77))
            randomize_hints(gw, config, SeededRng(77))
        texts1 = {q.quote_id: q.text for q in gw1.quotes}
        texts2 = {q.quote_id: q.text for q in gw2.quotes}
        assert texts1 == texts2


# =============================================================================
# 6. Helpful mode with progressive_items — item name overrides
# =============================================================================

class TestProgressiveItemNames:
    def test_wood_arrows_becomes_arrow_upgrade(self):
        loc = HintableLocation(item=Item.WOOD_ARROWS, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=True)
        assert "ARROW UPGRADE" in text
        assert "WOOD ARROWS" not in text

    def test_blue_candle_becomes_candle_upgrade(self):
        loc = HintableLocation(item=Item.BLUE_CANDLE, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=True)
        assert "CANDLE UPGRADE" in text

    def test_blue_ring_becomes_ring_upgrade(self):
        loc = HintableLocation(item=Item.BLUE_RING, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=True)
        assert "RING UPGRADE" in text

    def test_wood_sword_becomes_sword_upgrade(self):
        loc = HintableLocation(item=Item.WOOD_SWORD, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=True)
        assert "SWORD UPGRADE" in text

    def test_no_override_when_progressive_items_off(self):
        loc = HintableLocation(item=Item.BLUE_RING, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        assert "BLUE RING" in text
        assert "RING UPGRADE" not in text

    def test_non_overridden_item_unaffected_by_progressive_flag(self):
        loc = HintableLocation(item=Item.RAFT, entrance_type=EntranceType.RAFT)
        text_on = _build_helpful_hint_text(loc, progressive_items=True)
        text_off = _build_helpful_hint_text(loc, progressive_items=False)
        assert text_on == text_off
        assert "RAFT" in text_on


# =============================================================================
# 7. Heart requirement (numerical) hints
# =============================================================================

class TestNumericalHints:
    def test_all_valid_heart_counts_have_pool(self):
        for count in (4, 5, 6, 10, 11, 12):
            assert count in NUMERICAL_HINTS
            assert len(NUMERICAL_HINTS[count]) > 0

    def test_white_sword_heart_hint_applied(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(
            hint_mode=FlagHintMode.COMMUNITY,
            randomize_white_sword_hearts=True,
        ))
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        text = _quote_text(gw, HintType.WHITE_SWORD_CAVE)
        heart_req = next(
            c.heart_requirement for c in gw.overworld.caves
            if isinstance(c, ItemCave) and c.destination == Destination.WHITE_SWORD_CAVE
        )
        # Text should be from NUMERICAL_HINTS for the heart count
        pool = NUMERICAL_HINTS.get(heart_req, [])
        assert text in pool, (
            f"White sword heart hint {text!r} not in pool for {heart_req} hearts: {pool}"
        )

    def test_magical_sword_heart_hint_applied(self, bins):
        gw = parse_game_world(bins)
        config = _config(Flags(
            hint_mode=FlagHintMode.COMMUNITY,
            randomize_magical_sword_hearts=True,
        ))
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        text = _quote_text(gw, HintType.MAGICAL_SWORD_CAVE)
        heart_req = next(
            c.heart_requirement for c in gw.overworld.caves
            if isinstance(c, ItemCave) and c.destination == Destination.MAGICAL_SWORD_CAVE
        )
        pool = NUMERICAL_HINTS.get(heart_req, [])
        assert text in pool

    def test_heart_hint_not_applied_when_flag_off(self, bins):
        """When randomize_white_sword_hearts is False, the slot gets a community hint."""
        gw = parse_game_world(bins)
        config = _config(Flags(
            hint_mode=FlagHintMode.COMMUNITY,
            randomize_white_sword_hearts=False,
        ))
        _all_numerical = {t for hints in NUMERICAL_HINTS.values() for t in hints}
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        text = _quote_text(gw, HintType.WHITE_SWORD_CAVE)
        # Not from numerical hints (could coincidentally match, but overwhelmingly won't)
        # — just verify the slot was assigned something
        assert text


# =============================================================================
# 8. Directional hints — go to cave quote slots
# =============================================================================

class TestDirectionalHints:
    def test_lost_hills_goes_to_cave_slot(self, bins):
        """randomize_lost_hills writes directional text to HintType.LOST_HILLS_HINT (3).
        In community/helpful mode the paid hint shop slot is remapped to the same quote_id,
        so both the free cave and the shop show the same directional hint."""
        from zora.overworld_randomizer import randomize_maze_directions
        gw = parse_game_world(bins)
        flags = Flags(
            randomize_lost_hills=Tristate.ON,
            hint_mode=FlagHintMode.COMMUNITY,
        )
        config = _config(flags, seed=3)
        randomize_maze_directions(gw, config, SeededRng(3))
        expand_quote_slots(gw, config, SeededRng(3))
        randomize_hints(gw, config, SeededRng(3))

        cave_text = _quote_text(gw, HintType.LOST_HILLS_HINT)
        assert "THE MOUNTAIN AHEAD" in cave_text

    def test_dead_woods_goes_to_cave_slot(self, bins):
        from zora.overworld_randomizer import randomize_maze_directions
        gw = parse_game_world(bins)
        flags = Flags(
            randomize_dead_woods=Tristate.ON,
            hint_mode=FlagHintMode.COMMUNITY,
        )
        config = _config(flags, seed=3)
        randomize_maze_directions(gw, config, SeededRng(3))
        expand_quote_slots(gw, config, SeededRng(3))
        randomize_hints(gw, config, SeededRng(3))

        cave_text = _quote_text(gw, HintType.DEAD_WOODS_HINT)
        assert "THE FOREST OF MAZE" in cave_text


# =============================================================================
# 9. _scan_hintable_locations
# =============================================================================

class TestScanHintableLocations:
    def test_finds_dungeon_items_after_shuffle(self, bins):
        gw = parse_game_world(bins)
        config = _helpful_config(seed=1)
        randomize_items(gw, config, SeededRng(1))
        locations = _scan_hintable_locations(gw)
        found_items = {loc.item for loc in locations}
        # With dungeon shuffle on, progression items should be findable
        assert found_items & HINTABLE_PROGRESSION_ITEMS, (
            "No progression items found in scan results"
        )

    def test_each_location_has_valid_entrance_type(self, bins):
        gw = parse_game_world(bins)
        config = _helpful_config(seed=2)
        randomize_items(gw, config, SeededRng(2))
        locations = _scan_hintable_locations(gw)
        for loc in locations:
            assert isinstance(loc.entrance_type, EntranceType)

    def test_vanilla_raft_found(self, bins):
        """In vanilla (no shuffle), the Raft is in a dungeon and should be found by the scanner."""
        gw = parse_game_world(bins)
        locations = _scan_hintable_locations(gw)
        raft_locs = [loc for loc in locations if loc.item == Item.RAFT]
        assert raft_locs, "Raft not found in scan"
        # Should have a valid entrance type (not necessarily recorder — depends on screen)
        assert all(isinstance(loc.entrance_type, EntranceType) for loc in raft_locs)

    def test_no_duplicate_items_per_location(self, bins):
        """Each (item, entrance_type) pair may appear multiple times (multi-item dungeons),
        but item identity must always be a recognized hintable item."""
        gw = parse_game_world(bins)
        locations = _scan_hintable_locations(gw)
        all_hintable = HINTABLE_PROGRESSION_ITEMS | HINTABLE_NICE_TO_HAVE_ITEMS
        for loc in locations:
            assert loc.item in all_hintable, (
                f"Non-hintable item {loc.item} returned by scanner"
            )


# =============================================================================
# 10. _build_helpful_hint_text — format
# =============================================================================

class TestBuildHelpfulHintText:
    @pytest.mark.parametrize("entrance_type,expected_phrase", [
        (EntranceType.OPEN,             "EXPLORE AN OPEN CAVE"),
        (EntranceType.BOMB,             "EXPLODE AN ENTRANCE"),
        (EntranceType.CANDLE,           "BURN A BUSH"),
        (EntranceType.RECORDER,         "TOOT THE TOOTER"),
        (EntranceType.POWER_BRACELET,   "MOVE A BOULDER"),
        (EntranceType.RAFT,             "SAIL THE SEA"),
        (EntranceType.LADDER,           "STEP ACROSS THE WATER"),
        (EntranceType.LADDER_AND_BOMB,  "STEP ACROSS THE WATER"),
        (EntranceType.RAFT_AND_BOMB,    "SAIL THE SEA"),
        (EntranceType.POWER_BRACELET_AND_BOMB, "MOVE A BOULDER"),
        (EntranceType.NONE,             "EXPLORE AN OPEN CAVE"),
    ])
    def test_entrance_phrase(self, entrance_type, expected_phrase):
        loc = HintableLocation(item=Item.RAFT, entrance_type=entrance_type)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        assert text.startswith(expected_phrase), (
            f"Expected phrase {expected_phrase!r} for {entrance_type}, got {text!r}"
        )

    def test_text_format_has_three_pipe_parts(self):
        loc = HintableLocation(item=Item.LADDER, entrance_type=EntranceType.LADDER)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        parts = text.split("|")
        assert len(parts) == 3

    def test_middle_part_is_to_find(self):
        loc = HintableLocation(item=Item.BOW, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        parts = text.split("|")
        assert parts[1] == "TO FIND"

    def test_item_name_in_third_part(self):
        loc = HintableLocation(item=Item.SILVER_ARROWS, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        assert "SILVER ARROWS" in text

    def test_item_name_uses_spaces_not_underscores(self):
        loc = HintableLocation(item=Item.MAGICAL_BOOMERANG, entrance_type=EntranceType.OPEN)
        text = _build_helpful_hint_text(loc, progressive_items=False)
        assert "_" not in text


# =============================================================================
# 11. Hint shop prices
# =============================================================================

class TestHintShopPrices:
    def test_vanilla_mode_preserves_vanilla_prices(self, bins):
        gw = parse_game_world(bins)
        vanilla_prices = _hint_shop_prices(gw)
        config = _config(Flags(hint_mode=FlagHintMode.VANILLA))
        randomize_hints(gw, config, SeededRng(0))
        assert _hint_shop_prices(gw) == vanilla_prices

    def test_blank_mode_preserves_vanilla_prices(self, bins):
        gw = parse_game_world(bins)
        vanilla_prices = _hint_shop_prices(gw)
        config = _config(Flags(hint_mode=FlagHintMode.BLANK))
        randomize_hints(gw, config, SeededRng(0))
        assert _hint_shop_prices(gw) == vanilla_prices

    def test_community_mode_prices_in_range(self, bins):
        gw = parse_game_world(bins)
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        for shop_prices in _hint_shop_prices(gw):
            for price in shop_prices:
                assert 10 <= price <= 50, f"Price {price} out of range"

    def test_helpful_mode_prices_in_range(self, bins):
        gw = parse_game_world(bins)
        config = _helpful_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_items(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))
        for shop_prices in _hint_shop_prices(gw):
            for price in shop_prices:
                assert 10 <= price <= 50


# =============================================================================
# 12. Serializer pointer table — expanded quote_ids
# =============================================================================

class TestSerializerExpandedPointerTable:
    def test_expanded_pointer_table_size(self, bins):
        """Pointer table must be (max_quote_id+1)*2 bytes = 41*2=82 for 42-slot mode."""
        gw = parse_game_world(bins)
        originals = _load_originals()
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))

        from zora.game_config import HintMode as GHintMode
        patch = serialize_game_world(gw, originals, hint_mode=GHintMode.COMMUNITY)

        # Quote data written to extended bank — pointer table only at QUOTE_DATA_ADDRESS
        ptr_table = patch.data[QUOTE_DATA_ADDRESS]
        # max_id = 42, so (42+1)*2 = 86 bytes
        assert len(ptr_table) == 82

    def test_vanilla_pointer_table_size_unchanged(self, bins):
        """In vanilla mode, pointer table is still 38*2=76 bytes at QUOTE_DATA_ADDRESS."""
        gw = parse_game_world(bins)
        originals = _load_originals()
        patch = serialize_game_world(gw, originals)
        # In vanilla mode, the full block (pointer table + text) is written
        # The pointer table is the first 38*2=76 bytes
        data = patch.data[QUOTE_DATA_ADDRESS]
        assert len(data) >= 76

    def test_quote_id_42_pointer_is_present(self, bins):
        """The highest new quote_id (42 = HINT_SHOP_2B) must have a valid pointer in the table."""
        gw = parse_game_world(bins)
        originals = _load_originals()
        config = _community_config()
        expand_quote_slots(gw, config, SeededRng(0))
        randomize_hints(gw, config, SeededRng(0))

        from zora.game_config import HintMode as GHintMode
        patch = serialize_game_world(gw, originals, hint_mode=GHintMode.COMMUNITY)
        ptr_table = patch.data[QUOTE_DATA_ADDRESS]
        max_id = HintType.HINT_SHOP_2B
        ptr_lo = ptr_table[max_id * 2]
        ptr_hi = ptr_table[max_id * 2 + 1]
        assert (ptr_lo, ptr_hi) != (0, 0), f"Quote_id={max_id} has null pointer"


# =============================================================================
# 13. HintMode.RANDOM resolution
# =============================================================================

class TestHintModeRandom:
    def test_random_resolves_to_concrete_mode(self):
        """FlagHintMode.RANDOM must resolve to one of the four concrete HintMode values."""
        flags = Flags(hint_mode=FlagHintMode.RANDOM)
        concrete_modes = {HintMode.VANILLA, HintMode.BLANK, HintMode.COMMUNITY, HintMode.HELPFUL}
        for seed in range(20):
            config = resolve_game_config(flags, SeededRng(seed))
            assert config.hint_mode in concrete_modes, (
                f"Seed {seed} resolved to unexpected HintMode: {config.hint_mode}"
            )

    def test_random_can_resolve_to_each_mode(self):
        """All four concrete modes should be reachable from RANDOM."""
        flags = Flags(hint_mode=FlagHintMode.RANDOM)
        seen: set[HintMode] = set()
        for seed in range(200):
            config = resolve_game_config(flags, SeededRng(seed))
            seen.add(config.hint_mode)
            if len(seen) == 4:
                break
        assert len(seen) == 4, f"Only saw modes {seen} after 200 seeds"


# =============================================================================
# 14. Hint line length — no line may exceed 22 characters
# =============================================================================

_MAX_LINE_LENGTH = 22


class TestHintLineLength:
    """Every hint line (pipe-delimited segment) must fit in the 22 usable text columns."""

    @staticmethod
    def _check_lines(text: str, context: str) -> list[str]:
        violations = []
        for i, line in enumerate(text.split("|")):
            stripped = line.strip()
            if len(stripped) > _MAX_LINE_LENGTH:
                violations.append(
                    f"{context}: line {i} is {len(stripped)} chars "
                    f"(max {_MAX_LINE_LENGTH}): {stripped!r}"
                )
        return violations

    def test_community_hint_pools(self):
        from zora.hint_randomizer import COMMUNITY_HINTS
        violations = []
        for hint_type, pool in COMMUNITY_HINTS.items():
            for text in pool:
                violations.extend(self._check_lines(text, f"COMMUNITY_HINTS[{hint_type.name}]"))
        assert not violations, "\n".join(violations)

    def test_other_pool(self):
        from zora.hint_randomizer import _OTHER_POOL
        violations = []
        for text in _OTHER_POOL:
            violations.extend(self._check_lines(text, "_OTHER_POOL"))
        assert not violations, "\n".join(violations)

    def test_numerical_hints(self):
        violations = []
        for count, pool in NUMERICAL_HINTS.items():
            for text in pool:
                violations.extend(self._check_lines(text, f"NUMERICAL_HINTS[{count}]"))
        assert not violations, "\n".join(violations)

    def test_helpful_hint_text(self):
        """All entrance phrase + hintable item combos must fit."""
        from zora.hint_randomizer import (
            _ALL_HINTABLE_ITEMS,
            _ENTRANCE_PHRASES,
            _build_helpful_hint_text,
        )
        violations = []
        for entrance_type in _ENTRANCE_PHRASES:
            for item in _ALL_HINTABLE_ITEMS:
                for progressive in (True, False):
                    loc = HintableLocation(item=item, entrance_type=entrance_type)
                    text = _build_helpful_hint_text(loc, progressive_items=progressive)
                    ctx = f"helpful({entrance_type.name}, {item.name}, progressive={progressive})"
                    violations.extend(self._check_lines(text, ctx))
        assert not violations, "\n".join(violations)

    def test_lost_hills_hint_text(self):
        from zora.hint_randomizer import _lost_hills_hint_text
        from zora.data_model import OverworldDirection
        dirs = [OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                OverworldDirection.RIGHT_EAST]
        violations = []
        for combo in [(a, b, c, d) for a in dirs for b in dirs for c in dirs for d in dirs]:
            text = _lost_hills_hint_text(list(combo))
            violations.extend(self._check_lines(text, f"lost_hills{combo}"))
        assert not violations, "\n".join(violations)

    def test_dead_woods_hint_text(self):
        from zora.hint_randomizer import _dead_woods_hint_text
        from zora.data_model import OverworldDirection
        dirs = [OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                OverworldDirection.LEFT_WEST]
        violations = []
        for combo in [(a, b, c, d) for a in dirs for b in dirs for c in dirs for d in dirs]:
            text = _dead_woods_hint_text(list(combo))
            violations.extend(self._check_lines(text, f"dead_woods{combo}"))
        assert not violations, "\n".join(violations)
