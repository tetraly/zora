"""Archipelago's option keys (zora/archipelago.py option_key; docs/archipelago.md "Options"): each
offered option's name in a player's YAML, from the community's flag names (docs/spec/flag-names-
reference.csv, as zora/flags/names.json holds it), a ZORA Extra by its field name. Stable from
beta 3 on: KEYS pins every one, so a renamed flag on the page cannot rename an option. A new
option adds its key here; changing one needs the owner."""
import re

import pytest

from zora import archipelago
from zora.flags import zora_form
from zora.flags.fields import THREE_STATE_LABELS, ThreeState

# id -> key, in option_fields' order (beta 3)
KEYS = {
    "C01": "overworld_quest", "C02": "dungeon_quest", "C03": "hint_type", "C04": "start_screen",
    "C05": "cave_shuffle", "C07": "swords", "C08": "level_9_entry", "C09": "most_enemy_hp", "C10": "boss_hp",
    "C11": "armos_item", "C12": "coast_item", "C13": "white_sword_item", "C14": "dungeon_room_shuffle",
    "C15": "item_sprites", "C16": "starting_hearts", "C17": "max_start_items", "C18": "triforce_pieces",
    "C19": "red_bubble_curse", "C20": "white_sword_hearts_min", "C21": "white_sword_hearts_max",
    "C22": "magical_sword_hearts_min", "C23": "magical_sword_hearts_max", "C24": "triforce_range_min",
    "C25": "triforce_range_max", "C26": "level_9_item_1", "C27": "level_9_item_2",
    "B01": "recorder_to_new_dungeons", "B02": "shuffle_wood_sword_cave", "B03": "allow_ow_blocks_of_wood_sword",
    "B04": "shuffle_take_any_road_caves", "B05": "change_secret_spots", "B06": "mirror_overworld",
    "B07": "recorder_to_unbeaten_dungeons", "B08": "shuffle_shop_items", "B09": "extra_candles",
    "B10": "change_sword_hearts", "B11": "change_mmg", "B12": "change_bomb_upgrades", "B13": "shuffle_armos",
    "B14": "shuffle_dungeon_items", "B15": "shuffle_dungeon_drops", "B16": "shuffle_dungeon_hearts",
    "B17": "shuffle_minor_dungeon_drops", "B18": "force_ganon_fight", "B19": "shuffle_dungeon_text",
    "B20": "add_2nd_quest_rooms", "B21": "add_2nd_quest_doors", "B22": "add_money_or_life_rooms",
    "B23": "change_leave_your_rooms", "B24": "hide_dungeon_numbers", "B25": "allow_important_items_in_9",
    "B26": "shuffle_dungeon_start_room", "B27": "shuffle_dungeon_palettes", "B28": "shuffle_hungry_goriya",
    "B29": "shuffle_bomb_upgrade_men", "B30": "remove_most_open_stairs", "B31": "shuffle_overworld_monsters",
    "B32": "shuffle_dungeon_monsters", "B33": "shuffle_ganon_and_zelda", "B34": "shuffle_bosses",
    "B35": "shuffle_level_9_monsters", "B36": "shuffle_monsters_between_levels", "B37": "add_2nd_quest_monsters",
    "B38": "shuffle_enemy_drop_groups", "B39": "make_important_items_drops", "B40": "randomize_boss_groups",
    "B41": "set_ganon_hp_to_0", "B42": "shuffle_enemy_groups", "B43": "shuffle_overworld_group",
    "B44": "randomize_item_drop_rate", "B45": "maximum_enemy_health", "B46": "maximum_boss_health",
    "B47": "replace_book_fire_with_explosion", "B48": "book_to_understand_old_men", "B49": "book_is_an_atlas",
    "B50": "blackout", "B51": "print_quest_info", "B52": "permanent_sword_beam", "B53": "ohko",
    "B54": "speed_up_text", "B55": "hidden_health", "B56": "killable_drop_items", "B57": "start_raft",
    "B58": "start_bow", "B59": "start_8_bombs", "B60": "start_recorder", "B61": "start_bait",
    "B62": "start_magical_key", "B63": "start_letter", "B64": "start_power_bracelet", "B65": "start_ladder",
    "B66": "start_wand", "B67": "start_book", "B68": "start_wood_sword", "B69": "start_white_sword",
    "B70": "start_magical_sword", "B71": "start_wood_arrow", "B72": "start_silver_arrow",
    "B73": "start_blue_candle", "B74": "start_red_candle", "B75": "start_blue_ring", "B76": "start_red_ring",
    "B77": "start_wood_boomerang", "B78": "start_magical_boomerang", "B79": "add_extra_bosses",
    "B80": "rupees_affect_speed", "B81": "force_overworld_block", "B83": "hidden_numbers",
    "B84": "prevent_clipping", "B85": "start_magical_shield", "B86": "do_not_sort_shapes",
    "B87": "add_bridges_to_the_river", "B88": "add_lost_woods_shortcut", "B89": "change_hidden_ow_tiles",
    "B90": "increase_bomb_capacity_upgrade", "B91": "allow_universal_drops_in_shapes",
    "randomize_magical_sword": "randomize_magical_sword", "randomize_letter": "randomize_letter",
    "magical_sword_hearts_highest": "magical_sword_hearts_highest", "progressive_items": "progressive_items",
    "shop_items_in_pool": "shop_items_in_pool", "shuffle_blue_potion": "shuffle_blue_potion",
    "add_l4_sword": "add_l4_sword", "level_9_entrance_sword": "level_9_entrance_sword",
    "extra_raft_blocks": "extra_raft_blocks", "extra_power_bracelet_blocks": "extra_power_bracelet_blocks",
    "speed_up_dungeon_transitions": "speed_up_dungeon_transitions", "speed_up_heart_fill": "speed_up_heart_fill",
    "recorder_kills_pols_voice": "recorder_kills_pols_voice", "four_potion_inventory": "four_potion_inventory",
    "auto_show_letter": "auto_show_letter", "like_like_eats_rupees": "like_like_eats_rupees",
    "magical_boomerang_damage": "magical_boomerang_damage", "randomize_lost_hills": "randomize_lost_hills",
    "randomize_dead_woods": "randomize_dead_woods",
    "oops_all_enemies": "oops_all_enemies", "oops_all_bosses": "oops_all_bosses",
}
CODE = re.compile(r"(?:^|_)[bc]\d{2}(?:_|$)")


def test_every_key_is_pinned() -> None:
    assert archipelago.option_keys() == KEYS


def test_the_key_rules() -> None:
    """Lowercase words joined by underscores, unique, never a flag's code; a ZORA Extra's key is
    its field name."""
    keys = list(KEYS.values())
    assert len(set(keys)) == len(keys)
    for key in keys:
        assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", key), key
        assert not CODE.search(key), key
    for field in zora_form.FIELDS:
        assert KEYS[field["name"]] == field["name"]


def test_ganon_is_spelled_as_the_game_does_and_the_label_keeps_the_communitys() -> None:
    """Owner, before beta 3: the keys say ganon; the page's labels say what the community says."""
    names = {spec.id: spec.name for spec in archipelago.option_fields()}
    spelled = {"B18": "force_ganon_fight", "B33": "shuffle_ganon_and_zelda", "B41": "set_ganon_hp_to_0"}
    for field_id, key in spelled.items():
        assert KEYS[field_id] == key and "Gannon" in names[field_id]
    assert not any("gannon" in key for key in KEYS.values())


@pytest.mark.parametrize(("name", "key"), [("Level 9 Entry", "level_9_entry"), ('"Most" Enemy HP', "most_enemy_hp"),
                                           ("White Sword Hearts (min)", "white_sword_hearts_min")])
def test_key_of(name: str, key: str) -> None:
    assert archipelago.key_of(name) == key


def test_a_key_and_an_id_choose_the_same() -> None:
    """flag_strings takes each option by its key or by its id; one option by both is refused."""
    by_key = archipelago.flag_strings({"starting_hearts": 3, "extra_candles": 0, "progressive_items": 1})
    by_id = archipelago.flag_strings({"C16": 3, "B09": 0, "progressive_items": 1})
    assert by_key == by_id != archipelago.flag_strings({})
    with pytest.raises(archipelago.OptionsConflict, match="by key and by id"):
        archipelago.flag_strings({"starting_hearts": 3, "C16": 3})
    with pytest.raises(archipelago.OptionsConflict, match="unknown"):
        archipelago.flag_strings({"c16_starting_hearts": 3})


def test_the_switch_labels_are_the_pages() -> None:
    """Off / On / Random, from zora/flags/fields.py."""
    for spec in archipelago.option_fields():
        if spec.kind in (archipelago.THREE_STATE, archipelago.SWITCH):
            assert all(label == THREE_STATE_LABELS[ThreeState(value)] for value, label in spec.choices), spec
