"""Archipelago's value keys (zora/archipelago.py option_value_keys, PlayerSettingSpec.value_keys;
docs/archipelago.md "Value keys (stable from beta 3 on)"): each value's name in a player's YAML.
VALUE_KEYS pins every option's, offered or not, in value order (a value released later keeps its
key); PLAYER_KEYS every player setting's. A key is lowercase words joined by underscores, a valid
identifier, unique within its option and never "random" (Archipelago's own "pick one"); ZORA's
per-seed Random is random_per_seed. Labels may change; renaming a key needs the owner. The old
forms keep working: numbers, the page's player-setting names and values, released flag strings."""
import pytest

from tests.test_archipelago_option_keys import KEYS
from zora import archipelago
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.player_settings import (
    PAGE_BOSS_SOUND_WORD,
    RANDOM_BOSS_SOUND_WORD,
    PlayerSettingError,
    PlayerSettings,
    player_settings_from_page,
)

THREE_STATE = ("off", "on", "random_per_seed")
SWITCH = ("off", "on")
ITEMS = ("random_per_seed", "book", "boomerang", "bow", "heart_container", "ladder", "magical_boomerang",
         "magical_key", "power_bracelet", "raft", "recorder", "red_candle", "red_ring", "silver_arrow", "wand",
         "white_sword", "non_heart")
# option key -> each value's key, in value order (beta 3)
VALUE_KEYS = {
    "overworld_quest": ("first_quest", "second_quest", "mixed_quest_first", "mixed_quest_second", "random_per_seed"),
    "dungeon_quest": ("first_quest", "second_quest", "mixed_quest", "shapes", "mixed_plus_shapes",
        "random_per_seed_no_shapes", "random_per_seed"),
    "hint_type": ("normal", "helpful", "community", "deception", "mixed", "blank", "random_per_seed"),
    "start_screen": ("normal", "easy_start_shuffle", "full_start_shuffle", "wood_sword_screen"),
    "cave_shuffle": ("vanilla", "dungeons_only", "non_dungeons_only", "all_caves", "random_per_seed"),
    "swords": ("normal", "wood_sword_only", "no_wood_sword", "swordless", "random_per_seed"),
    "level_9_entry": ("triforces_8", "triforces_7", "triforces_6", "triforces_5", "triforces_4", "triforces_3",
        "triforces_2", "triforces_1", "open_level_9", "triforce_range", "specific_triforces", "other_item",
        "random_per_seed"),
    "most_enemy_hp": ("normal", "plus_minus_2", "plus_minus_4", "hp_0", "random_per_seed"),
    "boss_hp": ("normal", "plus_minus_2", "plus_minus_4", "hp_0", "random_per_seed"),
    "armos_item": ITEMS,
    "coast_item": ITEMS,
    "white_sword_item": ITEMS,
    "dungeon_room_shuffle": ("vanilla", "in_dungeon_shuffle", "full_shuffle", "random_per_seed"),
    "item_sprites": ("normal", "fun_percent", "sprite_shuffle", "random_per_seed"),
    "starting_hearts": ("hearts_1", "hearts_2", "hearts_3", "hearts_4", "hearts_5", "hearts_6", "hearts_7",
        "hearts_8", "hearts_9", "hearts_10", "hearts_11", "hearts_12", "hearts_13", "hearts_14", "hearts_15",
        "hearts_16", "hearts_1_to_5"),
    "max_start_items": ("all", "items_0", "items_1", "items_2", "items_3", "items_4", "items_5", "items_6",
        "items_7", "items_8", "items_9", "items_10", "items_11", "items_12", "items_13", "items_14", "items_15",
        "items_16", "items_17", "items_18", "items_19", "items_20", "random_per_seed"),
    "triforce_pieces": ("pieces_0", "pieces_1", "pieces_2", "pieces_3", "pieces_4", "pieces_5", "pieces_6",
        "pieces_7", "pieces_8", "random_per_seed"),
    "red_bubble_curse": ("swordless", "inverted_control", "slow_speed", "random_per_seed"),
    "white_sword_hearts_min": ("hearts_4", "hearts_5", "hearts_6"),
    "white_sword_hearts_max": ("hearts_6", "hearts_5", "hearts_4"),
    "magical_sword_hearts_min": ("hearts_10", "hearts_11", "hearts_12", "hearts_13", "hearts_14"),
    "magical_sword_hearts_max": ("hearts_14", "hearts_13", "hearts_12", "hearts_11", "hearts_10"),
    "triforce_range_min": ("triforces_0", "triforces_1", "triforces_2", "triforces_3", "triforces_4", "triforces_5",
        "triforces_6", "triforces_7", "triforces_8"),
    "triforce_range_max": ("triforces_8", "triforces_7", "triforces_6", "triforces_5", "triforces_4", "triforces_3",
        "triforces_2", "triforces_1", "triforces_0"),
    "level_9_item_1": ITEMS,
    "level_9_item_2": ITEMS,
    "recorder_to_new_dungeons": THREE_STATE,
    "shuffle_wood_sword_cave": THREE_STATE,
    "allow_ow_blocks_of_wood_sword": THREE_STATE,
    "shuffle_take_any_road_caves": THREE_STATE,
    "change_secret_spots": THREE_STATE,
    "mirror_overworld": THREE_STATE,
    "recorder_to_unbeaten_dungeons": THREE_STATE,
    "shuffle_shop_items": THREE_STATE,
    "extra_candles": THREE_STATE,
    "change_sword_hearts": THREE_STATE,
    "change_mmg": THREE_STATE,
    "change_bomb_upgrades": THREE_STATE,
    "shuffle_armos": THREE_STATE,
    "shuffle_dungeon_items": THREE_STATE,
    "shuffle_dungeon_drops": THREE_STATE,
    "shuffle_dungeon_hearts": THREE_STATE,
    "shuffle_minor_dungeon_drops": THREE_STATE,
    "force_ganon_fight": THREE_STATE,
    "shuffle_dungeon_text": THREE_STATE,
    "add_2nd_quest_rooms": THREE_STATE,
    "add_2nd_quest_doors": THREE_STATE,
    "add_money_or_life_rooms": THREE_STATE,
    "change_leave_your_rooms": THREE_STATE,
    "hide_dungeon_numbers": THREE_STATE,
    "allow_important_items_in_9": THREE_STATE,
    "shuffle_dungeon_start_room": THREE_STATE,
    "shuffle_dungeon_palettes": THREE_STATE,
    "shuffle_hungry_goriya": THREE_STATE,
    "shuffle_bomb_upgrade_men": THREE_STATE,
    "remove_most_open_stairs": THREE_STATE,
    "shuffle_overworld_monsters": THREE_STATE,
    "shuffle_dungeon_monsters": THREE_STATE,
    "shuffle_ganon_and_zelda": THREE_STATE,
    "shuffle_bosses": THREE_STATE,
    "shuffle_level_9_monsters": THREE_STATE,
    "shuffle_monsters_between_levels": THREE_STATE,
    "add_2nd_quest_monsters": THREE_STATE,
    "shuffle_enemy_drop_groups": THREE_STATE,
    "make_important_items_drops": THREE_STATE,
    "randomize_boss_groups": THREE_STATE,
    "set_ganon_hp_to_0": THREE_STATE,
    "shuffle_enemy_groups": THREE_STATE,
    "shuffle_overworld_group": THREE_STATE,
    "randomize_item_drop_rate": THREE_STATE,
    "maximum_enemy_health": THREE_STATE,
    "maximum_boss_health": THREE_STATE,
    "replace_book_fire_with_explosion": THREE_STATE,
    "book_to_understand_old_men": THREE_STATE,
    "book_is_an_atlas": THREE_STATE,
    "blackout": THREE_STATE,
    "print_quest_info": THREE_STATE,
    "permanent_sword_beam": THREE_STATE,
    "ohko": THREE_STATE,
    "speed_up_text": THREE_STATE,
    "hidden_health": THREE_STATE,
    "killable_drop_items": THREE_STATE,
    "start_raft": THREE_STATE,
    "start_bow": THREE_STATE,
    "start_8_bombs": THREE_STATE,
    "start_recorder": THREE_STATE,
    "start_bait": THREE_STATE,
    "start_magical_key": THREE_STATE,
    "start_letter": THREE_STATE,
    "start_power_bracelet": THREE_STATE,
    "start_ladder": THREE_STATE,
    "start_wand": THREE_STATE,
    "start_book": THREE_STATE,
    "start_wood_sword": THREE_STATE,
    "start_white_sword": THREE_STATE,
    "start_magical_sword": THREE_STATE,
    "start_wood_arrow": THREE_STATE,
    "start_silver_arrow": THREE_STATE,
    "start_blue_candle": THREE_STATE,
    "start_red_candle": THREE_STATE,
    "start_blue_ring": THREE_STATE,
    "start_red_ring": THREE_STATE,
    "start_wood_boomerang": THREE_STATE,
    "start_magical_boomerang": THREE_STATE,
    "add_extra_bosses": THREE_STATE,
    "rupees_affect_speed": THREE_STATE,
    "force_overworld_block": THREE_STATE,
    "hidden_numbers": THREE_STATE,
    "prevent_clipping": THREE_STATE,
    "start_magical_shield": THREE_STATE,
    "do_not_sort_shapes": THREE_STATE,
    "add_bridges_to_the_river": THREE_STATE,
    "add_lost_woods_shortcut": THREE_STATE,
    "change_hidden_ow_tiles": THREE_STATE,
    "increase_bomb_capacity_upgrade": THREE_STATE,
    "allow_universal_drops_in_shapes": THREE_STATE,
    "randomize_magical_sword": SWITCH,
    "randomize_letter": SWITCH,
    "magical_sword_hearts_highest": ("follow_the_z1r_flags", "at_most_10_hearts", "at_most_11_hearts",
        "at_most_12_hearts", "at_most_13_hearts", "at_most_14_hearts"),
    "progressive_items": SWITCH,
    "shop_items_in_pool": SWITCH,
    "shuffle_blue_potion": THREE_STATE,
    "add_l4_sword": ("off", "level_2", "level_9"),
    "level_9_entrance_sword": ("triforce_pieces", "level_4_sword"),
    "extra_raft_blocks": THREE_STATE,
    "extra_power_bracelet_blocks": THREE_STATE,
    "speed_up_dungeon_transitions": THREE_STATE,
    "speed_up_heart_fill": THREE_STATE,
    "recorder_kills_pols_voice": THREE_STATE,
    "four_potion_inventory": THREE_STATE,
    "auto_show_letter": THREE_STATE,
    "like_like_eats_rupees": THREE_STATE,
    "magical_boomerang_damage": THREE_STATE,
    "randomize_lost_hills": THREE_STATE,
    "randomize_dead_woods": THREE_STATE,
    "oops_all_enemies": ("off", "wizzrobes", "keese", "bouncers"),
    "oops_all_bosses": ("off", "dodongos"),
}
COLORS = tuple(f"0x{value:02X}" for value in range(0x40) if value != 0x0D)   # every NES palette value but $0D
# page key -> (YAML key, each listed value's key in the page's order; a color's are COLORS)
PLAYER_KEYS = {
    "selectButton": ("select_button", ("off", "swap", "toggle")),
    "lowHealthBeep": ("low_health_beep", ("removed", "kept")),
    "deathWarp": ("death_warp", ("p2_up_a", "p1_up_a", "p1_up_select")),
    "reduceFlashing": ("reduce_flashing", ("off", "on")),
    "music": ("music", ("on", "off")),
    "statisticsScreen": ("statistics_screen", ("on", "off")),
    "greenTunic": ("green_tunic", COLORS),
    "blueRingTunic": ("blue_ring_tunic", COLORS),
    "redRingTunic": ("red_ring_tunic", COLORS),
    "heart": ("hearts", COLORS),
    "levelWord": ("level_word", (
        "level", "board", "abode", "lair", "sector", "area", "palace", "vault", "crypt", "tomb", "keep", "maze",
        "tower", "temple", "shrine", "castle", "fort", "hall", "den", "nest", "hold", "stage", "world", "zone",
        "floor", "ruin", "pit", "cave")),
    "bossSoundWord": ("boss_sound_word", (
        "roar", "random_word", "rawr", "meow", "woof", "awoo", "oink", "weef", "honk", "aaaa", "goal", "ohai",
        "waah", "howl", "hiss", "purr", "bark", "hoot", "baaa", "grrr", "bonk", "eeek", "oops", "yaay")),
}
SPECS = archipelago.option_fields()
PLAYER_SPECS = {spec.key: spec for spec in archipelago.player_setting_fields()}


def test_every_value_key_is_pinned() -> None:
    keys = archipelago.option_value_keys()
    assert {KEYS[option]: tuple(values.values()) for option, values in keys.items()} == VALUE_KEYS
    assert all(list(values) == list(range(len(values))) for values in keys.values())


def test_the_value_key_rules() -> None:
    """Lowercase words joined by underscores, a valid identifier, unique within the option, never
    "random"; ZORA's Random is random_per_seed wherever it has one."""
    for option, keys in VALUE_KEYS.items():
        assert len(set(keys)) == len(keys), option
        for key in keys:
            assert key.isidentifier() and key == key.lower() and "__" not in key, (option, key)
            assert key != "random", option
    assert archipelago.RANDOM_PER_SEED == "random_per_seed"


def test_each_offered_value_carries_its_key() -> None:
    for spec in SPECS:
        assert spec.value_keys == tuple((value, VALUE_KEYS[spec.key][value]) for value in spec.values), spec.key


@pytest.mark.parametrize("spec", SPECS, ids=[spec.key for spec in SPECS])
def test_a_value_key_chooses_what_its_number_does(spec: archipelago.OptionSpec) -> None:
    """flag_strings takes a value by its key, for the option by its key or its id."""
    for value, key in spec.value_keys:
        try:
            by_number = archipelago.flag_strings({spec.key: value})
        except archipelago.OptionsConflict:
            with pytest.raises(archipelago.OptionsConflict):
                archipelago.flag_strings({spec.id: key})
            continue
        assert archipelago.flag_strings({spec.key: key}) == archipelago.flag_strings({spec.id: key}) == by_number


def test_old_forms_and_refusals() -> None:
    """Numbers and booleans keep working; a key of a value not offered (Dungeon Quest: Mixed
    Quest), a label or Archipelago's "random" is refused, naming the offered keys."""
    assert archipelago.flag_strings({"randomize_letter": True}) == archipelago.flag_strings({"randomize_letter": 1})
    assert archipelago.flag_strings({"overworld_quest": "mixed_quest_first", "B03": "random_per_seed"}) == \
        archipelago.flag_strings({"C01": 2, "allow_ow_blocks_of_wood_sword": 2})
    for option, wrong in (("dungeon_quest", "mixed_quest"), ("overworld_quest", "Mixed Quest - 1st"),
                          ("start_raft", "random"), ("starting_hearts", "3")):
        with pytest.raises(archipelago.OptionsConflict, match="not one of"):
            archipelago.flag_strings({option: wrong})


# --- player settings ------------------------------------------------------------------------------

def test_every_player_setting_key_is_pinned() -> None:
    assert {key: (spec.yaml_key, tuple(value_key for _value, value_key in spec.value_keys))
            for key, spec in PLAYER_SPECS.items()} == PLAYER_KEYS


def test_the_player_key_rules() -> None:
    """YAML keys and choice and word keys are identifiers; colors are hex; RANDOM is random_word."""
    yaml_keys = [spec.yaml_key for spec in PLAYER_SPECS.values()]
    assert len(set(yaml_keys)) == len(yaml_keys) and all(key.isidentifier() for key in yaml_keys)
    for spec in PLAYER_SPECS.values():
        keys = [key for _value, key in spec.value_keys]
        assert len(set(keys)) == len(keys) and "random" not in keys, spec.key
        if spec.kind != archipelago.COLOR:
            assert all(key.isidentifier() and key == key.lower() for key in keys), spec.key
        else:
            assert spec.value_keys == tuple((color, f"0x{color:02X}") for color in spec.colors)
    assert dict(PLAYER_SPECS[PAGE_BOSS_SOUND_WORD].value_keys)[RANDOM_BOSS_SOUND_WORD] == "random_word"


YAML_FORM = {"select_button": "swap", "death_warp": "p1_up_select", "low_health_beep": "kept",
             "green_tunic": "0x2A", "red_ring_tunic": "0x0f", "hearts": "0x16", "level_word": "palace",
             "boss_sound_word": "random_word", "statistics_screen": "off"}
PAGE_FORM = {"selectButton": "swap", "deathWarp": "p1-up-select", "lowHealthBeep": "kept", "greenTunic": 0x2A,
             "redRingTunic": 0x0F, "heart": 0x16, "levelWord": "palace", "bossSoundWord": RANDOM_BOSS_SOUND_WORD,
             "statisticsScreen": "off"}


def test_the_yaml_form_is_the_page_form() -> None:
    assert archipelago.page_player_settings(YAML_FORM) == PAGE_FORM
    assert archipelago.page_player_settings(PAGE_FORM) == PAGE_FORM          # an older recipe reads as it did
    assert player_settings_from_page(archipelago.page_player_settings(YAML_FORM)) == \
        player_settings_from_page(PAGE_FORM) != PlayerSettings()
    mixed = {"select_button": "toggle", "deathWarp": "p2_up_a", "bossSoundWord": "random_word", "heart": 22}
    assert archipelago.page_player_settings(mixed) == {"selectButton": "toggle", "deathWarp": "p2-up-a",
                                                       "bossSoundWord": RANDOM_BOSS_SOUND_WORD, "heart": 22}


def test_a_setting_by_both_keys_or_a_wrong_value_is_refused() -> None:
    with pytest.raises(PlayerSettingError, match="by YAML key and by page key"):
        archipelago.page_player_settings({"select_button": "off", "selectButton": "off"})
    for wrong in ({"death_warp": "p3_up_a"}, {"hearts": "0x0D"}, {"green_tunic": "0x40"}):
        with pytest.raises(PlayerSettingError):
            player_settings_from_page(archipelago.page_player_settings(wrong))


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")
def test_finish_and_the_recipe_take_the_yaml_form() -> None:
    """The same ROM from either form; the recipe keeps the page form (RANDOM as RANDOM), so older
    copies of ZORA and older recipes read it unchanged."""
    result = archipelago.build_from_strings(archipelago.DEFAULT_FLAGS, "", 1, remember_repo_base_rom())
    assignment = {place.name: item for place, item in zip(result.places, result.pool, strict=True)}
    assert archipelago.finish(result, assignment, player_settings=YAML_FORM) == \
        archipelago.finish(result, assignment, player_settings=PAGE_FORM)
    assert archipelago.recipe(result, assignment, player_settings=YAML_FORM)["playerSettings"] == PAGE_FORM
    assert archipelago.recipe(result, assignment, player_settings=PAGE_FORM)["playerSettings"] == PAGE_FORM
