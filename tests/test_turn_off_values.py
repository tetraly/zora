"""The turn-off values (flags-behavior.md FL-OFF-01 to FL-OFF-07): each value's Check,
run on finished ROMs generated from the CP-5 string (the MVP baseline, level encoding
off) with that one value changed, and the all-values string.

The spec's Checks run 40 seeds per value (60 for the all-values string); these tests
run SEEDS_PER_VALUE seeds each (ZORA_TURN_OFF_SEEDS overrides it, e.g. 40 under
pytest -n auto for the full run). Marked slow: python3 -m pytest -m slow -n auto.
"""
import os
from collections.abc import Callable
from dataclasses import replace
from functools import cache
from typing import TypeVar

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import TURN_OFF_OPTIONS, TURN_OFF_TOGGLES
from zora.generate.flag_steps import FlagSteps
from zora.generate.generation_pass import generate_shapes
from zora.generate.pipeline import GenerationPlan, generate_world, plan
from zora.generate.rng import Rng
from zora.generate.steps.shuffle_dungeon_text import SHUFFLED_SLOTS
from zora.generate.steps.shuffle_bosses import BOSSES_BEATEN_BY, bosses_beaten_by_planted_items
from zora.generate.steps.change_enemy_hp import BOSS_HP_TYPES, BOSS_MIRRORS, ENEMY_HP_TYPES
from zora.generate.steps.item_shuffle_result import TrackedPlace
from zora.generate.steps.shuffle_shop_items import SECRET_AMOUNTS, SHOPS, TAKE_ANY_CANDLE_SLOT
from zora_measure.checkpoints.groups_and_palettes import goriya_tile
from zora.model.enums import Destination, Enemy, Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.levels import MERCHANT_LIST
from zora.model.overworld import (
    DoorRepairCave, ItemCave, MoneyMakingGameCave, OverworldItem, SecretCave, Shop, TakeAnyCave,
)
from zora.rom.base_rom import piece_length, verify_base_rom
from zora.rom.code_patch_data import PATCHES
from zora.rom.code_patches import BOOK_IS_AN_ATLAS, overworld_start_y
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = pytest.mark.slow
CaveT = TypeVar("CaveT")

SEEDS_PER_VALUE = int(os.environ.get("ZORA_TURN_OFF_SEEDS", "3"))
SEEDS = range(1, SEEDS_PER_VALUE + 1)
ARMOS_SCREEN = 36
TRIFORCE = Item.TRIFORCE
SLOT_ORDER = sorted(SHUFFLED_SLOTS)
# FL-OFF-04, B42: the goriya tile that ships without the group pass
GORIYA_TILES_WITHOUT_GROUPS = {0xA0, 0xA4, 0xA8, 0xAC, 0xB0, 0xB4}
PRE_SHAPE_TILES = {0xA0, 0xA8, 0xAC, 0xB0}       # PS-GRUM-03's draw before the shape stage
# B27: the colour set is the palette transfer buffer without its last byte, which
# FP-ENTR-02 replaces with the level's exit-room count (bit 7 still ends the buffer)
PALETTE_BUFFER_END = -1
CHAMBER_LAYOUT = 0x28                            # FL-OFF-06, C14: the low seven bits checked


@cache
def base_rom() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def prg0() -> GameWorld:
    return parse_rom(base_rom())


def cp5_with(toggles: dict[str, ThreeState] | None = None, options: dict[str, int] | None = None) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options=options or {}, toggles=toggles or {}))


def all_values_string() -> str:
    """FL-OFF-01's Check string: every field of FL-OFF-07 at a turn-off value (C17 at 0; B22
    and B23 both off)."""
    return cp5_with(toggles=dict.fromkeys(TURN_OFF_TOGGLES, ThreeState.OFF),
                    options={field_id: min(values) for field_id, values in TURN_OFF_OPTIONS.items()})


@cache
def generated(flag_string: str, seed: int) -> tuple[GameWorld, bytes, GameWorld]:
    """The generated GameWorld, the finished ROM and that ROM parsed again."""
    chosen = plan(flag_string, seed)
    world, _ = generate_world(chosen, base_rom())
    rom = serialize_to_rom(world, base_rom(), config=chosen.config)
    return world, rom, parse_rom(rom)


def finished(flag_string: str, seed: int) -> GameWorld:
    return generated(flag_string, seed)[2]


def _cave(gw: GameWorld, destination: Destination, kind: type[CaveT]) -> CaveT:
    cave = gw.overworld.get_cave(destination, kind)
    assert isinstance(cave, kind), destination
    return cave


# --- the per-value Checks (FL-OFF-02 to FL-OFF-06) -------------------------------------

def recorder_bytes_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B01: the sixteen recorder-destination bytes equal PRG0."""
    for name in ("recorder_warp_destinations", "recorder_warp_y_coordinates"):
        assert getattr(gw.overworld, name) == getattr(prg0().overworld, name)


def shop_wares_and_prices_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B08: the twelve wares, twelve prices and the six extra price bytes equal PRG0."""
    for destination in SHOPS:
        assert _cave(gw, destination, Shop) == _cave(prg0(), destination, Shop)
    potion = _cave(gw, Destination.POTION_SHOP, Shop)
    assert [w.price for w in potion.items] == [w.price for w in _cave(prg0(), Destination.POTION_SHOP, Shop).items]
    for destination, _ in SECRET_AMOUNTS:
        assert _cave(gw, destination, SecretCave) == _cave(prg0(), destination, SecretCave)
    assert _cave(gw, Destination.DOOR_REPAIR, DoorRepairCave) == _cave(prg0(), Destination.DOOR_REPAIR, DoorRepairCave)


def candle_wares_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B09: both ware bytes keep PRG0's value."""
    wood_sword = _cave(gw, Destination.WOOD_SWORD_CAVE, ItemCave)
    take_any = _cave(gw, Destination.TAKE_ANY, TakeAnyCave)
    assert wood_sword.maybe_extra_candle == _cave(prg0(), Destination.WOOD_SWORD_CAVE, ItemCave).maybe_extra_candle
    assert take_any.items[TAKE_ANY_CANDLE_SLOT] == \
        _cave(prg0(), Destination.TAKE_ANY, TakeAnyCave).items[TAKE_ANY_CANDLE_SLOT]


def armos_tables_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B13: the 14 formation bytes and screen 36's attribute byte A equal PRG0."""
    ours, theirs = gw.overworld, prg0().overworld
    assert (ours.armos_screen_ids, ours.armos_positions) == (theirs.armos_screen_ids, theirs.armos_positions)
    screen, vanilla = ours.screens[ARMOS_SCREEN], theirs.screens[ARMOS_SCREEN]
    for name in ("outer_palette", "exit_x_position", "has_zola", "has_ocean_sound"):
        assert getattr(screen, name) == getattr(vanilla, name), name


def sword_hearts_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B10: the white-sword cave asks for 5 hearts and the magical-sword cave for 12."""
    for destination in (Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE):
        assert _cave(gw, destination, ItemCave).heart_requirement == \
            _cave(prg0(), destination, ItemCave).heart_requirement
    assert _cave(gw, Destination.WHITE_SWORD_CAVE, ItemCave).heart_requirement == 5


def money_game_is_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B11: loss 10 and 40, win 20 and 50 (and the fixed amount) as PRG0."""
    ours = _cave(gw, Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
    assert ours == _cave(prg0(), Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)


def bomb_upgrade_is_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B12: price 100, +4 capacity (the price tiles follow the price)."""
    assert gw.overworld.bomb_upgrade == prg0().overworld.bomb_upgrade


def triforce_pointers_name_triforce_rooms(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B15: each Triforce-room pointer of levels 1-8 names a room holding the Triforce."""
    for level in gw.levels[:8]:
        assert level.triforce_room_ptr is not None
        room = level.block.room(level.triforce_room_ptr)
        assert room.item_info.item == TRIFORCE, level.level_num


def hint_pointers_ascend(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B19: the eleven pointers lie in ascending address order (each slot its own text)."""
    assert world.hint_pointers is not None
    pointers = [world.hint_pointers[slot] for slot in SLOT_ORDER]
    assert pointers == sorted(pointers)


def no_merchants(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B22 with B23: no room has the monster byte $11 with the person flag."""
    assert not [room for level in gw.levels for room in level.rooms
                if room.monster_byte == MERCHANT_LIST and room.is_person]


def colour_sets_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B27: the nine levels' two colour sets equal PRG0."""
    for ours, theirs in zip(gw.levels, prg0().levels, strict=True):
        assert ours.palette_raw[:PALETTE_BUFFER_END] == theirs.palette_raw[:PALETTE_BUFFER_END]
        assert ours.fade_palette_raw == theirs.fade_palette_raw


def one_grumble_room(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B28: exactly one grumble room per ROM."""
    assert sum(room.enemy == Enemy.HUNGRY_GORIYA for level in gw.levels for room in level.rooms) == 1


def boss_banks_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B34: the nine high bytes of the boss pattern-block pointer table equal PRG0."""
    assert [level.boss_sprite_set for level in gw.levels] == [level.boss_sprite_set for level in prg0().levels]


def enemy_banks_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B36: the eighteen bank-pointer bytes equal PRG0."""
    assert [level.enemy_sprite_set for level in gw.levels] == [level.enemy_sprite_set for level in prg0().levels]


def accepted(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B40, B14, B16 and the all-values string: generated and accepted (generation raises
    otherwise)."""


def goriya_tile_without_groups(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B42: the goriya's tile byte is one of $A0, $A4, $A8, $AC, $B0 and $B4."""
    assert set(goriya_tile(gw)) <= GORIYA_TILES_WITHOUT_GROUPS


def book_sites_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B49: the sites of FP-BOOK-01 equal PRG0."""
    for offset, piece in PATCHES[BOOK_IS_AN_ATLAS]:
        assert rom[offset:offset + piece_length(piece)] == base_rom()[offset:offset + piece_length(piece)]


def text_speed_is_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """B54: the person-text delay operand equals PRG0 (6 frames)."""
    assert gw.text_speed_value == prg0().text_speed_value


def start_screen_is_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """C04 at 0: the start screen byte and the start Y equal PRG0's (FP-ENTR-01 reads the Y from
    its own byte, which holds PRG0's value)."""
    assert gw.overworld.start_screen == prg0().overworld.start_screen
    assert gw.overworld.start_position_y == prg0().overworld.start_position_y
    assert overworld_start_y(rom) == prg0().overworld.start_position_y


def enemy_hit_points_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """C09 at 0: the 25 enemy table bytes and the two rope operands equal PRG0."""
    for object_type in ENEMY_HP_TYPES:
        assert gw.enemies.hp[Enemy(object_type)] == prg0().enemies.hp[Enemy(object_type)]
    assert gw.enemies.rope_hp == prg0().enemies.rope_hp


def boss_hit_points_are_prg0(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """C10 at 0: the 12 boss table bytes and the five mirrored operands equal PRG0."""
    for object_type in BOSS_HP_TYPES:
        assert gw.enemies.hp[Enemy(object_type)] == prg0().enemies.hp[Enemy(object_type)]
    for name in (*BOSS_MIRRORS.values(), "gleeok_head_hp"):
        assert getattr(gw.enemies, name) == getattr(prg0().enemies, name), name


def no_chamber_layout_in_levels_1_to_8(world: GameWorld, rom: bytes, gw: GameWorld) -> None:
    """C14 at 1: no cell of levels 1-8 has a layout byte whose low seven bits are $28."""
    assert not [room for level in gw.levels[:8] for room in level.rooms
                if room.room_type == RoomType(CHAMBER_LAYOUT) and not room.movable_block]


# field change -> its Check
TURN_OFF_CHECKS: dict[str, tuple[dict[str, ThreeState], dict[str, int], Callable[..., None]]] = {
    "B01": ({"B01": ThreeState.OFF}, {}, recorder_bytes_are_prg0),
    "B08": ({"B08": ThreeState.OFF}, {}, shop_wares_and_prices_are_prg0),
    "B09": ({"B09": ThreeState.OFF}, {}, candle_wares_are_prg0),
    "B13": ({"B13": ThreeState.OFF}, {}, armos_tables_are_prg0),
    "B10": ({"B10": ThreeState.OFF}, {}, sword_hearts_are_prg0),
    "B11": ({"B11": ThreeState.OFF}, {}, money_game_is_prg0),
    "B12": ({"B12": ThreeState.OFF}, {}, bomb_upgrade_is_prg0),
    "B15": ({"B15": ThreeState.OFF}, {}, triforce_pointers_name_triforce_rooms),
    "B19": ({"B19": ThreeState.OFF}, {}, hint_pointers_ascend),
    "B22+B23": ({"B22": ThreeState.OFF, "B23": ThreeState.OFF}, {}, no_merchants),
    "B27": ({"B27": ThreeState.OFF}, {}, colour_sets_are_prg0),
    "B28": ({"B28": ThreeState.OFF}, {}, one_grumble_room),
    "B34": ({"B34": ThreeState.OFF}, {}, boss_banks_are_prg0),
    "B36": ({"B36": ThreeState.OFF}, {}, enemy_banks_are_prg0),
    "B40": ({"B40": ThreeState.OFF}, {}, accepted),
    "B42": ({"B42": ThreeState.OFF}, {}, goriya_tile_without_groups),
    "B42+B36": ({"B42": ThreeState.OFF, "B36": ThreeState.OFF}, {}, goriya_tile_without_groups),
    "B42+B28": ({"B42": ThreeState.OFF, "B28": ThreeState.OFF}, {}, goriya_tile_without_groups),
    "B49": ({"B49": ThreeState.OFF}, {}, book_sites_are_prg0),
    "B54": ({"B54": ThreeState.OFF}, {}, text_speed_is_prg0),
    "C04": ({}, {"C04": 0}, start_screen_is_prg0),
    "C09": ({}, {"C09": 0}, enemy_hit_points_are_prg0),
    "C10": ({}, {"C10": 0}, boss_hit_points_are_prg0),
    "C14": ({}, {"C14": 1}, no_chamber_layout_in_levels_1_to_8),
}
# Checked on the all-values string as well (FL-OFF-01's Check: every site comparison holds
# there too). B31 needs the group pass off and has its own run; B22's merchant count is the
# pair's.
ALL_VALUES_CHECKS = [check for name, (_, _, check) in TURN_OFF_CHECKS.items()
                     if "+" not in name or name == "B22+B23"]


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("value", list(TURN_OFF_CHECKS))
def test_turn_off_value_check(value: str, seed: int) -> None:
    toggles, options, check = TURN_OFF_CHECKS[value]
    check(*generated(cp5_with(toggles, options), seed))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("change", [{"B14": ThreeState.OFF}, {"B16": ThreeState.OFF},
                                    {"B14": ThreeState.OFF, "B16": ThreeState.OFF}, {"C17": 0}, {"C17": 2},
                                    {"C17": 22}], ids=["B14", "B16", "B14+B16", "C17=0", "C17=2", "C17=22"])
def test_values_without_an_effect_give_the_cp5_rom(change: dict[str, int], seed: int) -> None:
    """FL-OFF-03 (B14, B16) and FL-OFF-06 (C17): nothing changes. With level encoding off the
    flag string reaches no byte, so the finished ROM is CP-5's."""
    toggles = {k: ThreeState(v) for k, v in change.items() if k.startswith("B")}
    options = {k: v for k, v in change.items() if k.startswith("C")}
    flag_string = cp5_with(toggles, options)
    assert flag_string != MVP_BASELINE_LEVEL_ENCODING_OFF
    assert generated(flag_string, seed)[1] == generated(cp5_with(), seed)[1]


@pytest.mark.parametrize("seed", SEEDS)
def test_all_values_string_generates_and_every_site_check_holds(seed: int) -> None:
    """FL-OFF-01's Check (the spec: 60 of 60)."""
    result = generated(all_values_string(), seed)
    for check in ALL_VALUES_CHECKS:
        check(*result)
    # B28, B36 and B42 all off: the pre-shape draw ships
    assert set(goriya_tile(result[2])) <= PRE_SHAPE_TILES


@pytest.mark.parametrize("seed", SEEDS)
def test_b31_off_with_the_group_pass_and_start_shuffle_off_keeps_prg0_monsters(seed: int) -> None:
    """FL-OFF-04, B31's Check: with B31, B42 and B43 off and the start screen
    normal, the monster tables of all 128 screens equal PRG0. B43 off is not a supported value,
    so this runs the steps directly (B43 is part of the group pass here)."""
    world = parse_rom(base_rom())
    steps = FlagSteps(shuffle_overworld_monsters=False, shuffle_enemy_groups=False, shuffle_start_screen=False)
    chosen: GenerationPlan = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed)
    generate_shapes(world, Rng(seed), chosen.shape_options, feature_data=True, seed=seed, steps=steps)
    gw = parse_rom(serialize_to_rom(world, base_rom(), config=chosen.config))
    for ours, theirs in zip(gw.overworld.screens, prg0().overworld.screens, strict=True):
        assert (ours.enemy_spec, ours.enemy_quantity) == (theirs.enemy_spec, theirs.enemy_quantity), \
            ours.screen_num


def test_ps_boss_05_bars_the_bosses_beaten_by_the_first_and_last_planted_items() -> None:
    """PS-BOSS-05: only the FIRST and the LAST record lying in the level count."""
    planted = [TrackedPlace(Item.BOW, level=1), TrackedPlace(Item.WAND, level=1),
               TrackedPlace(Item.RAFT, level=2), TrackedPlace(Item.RECORDER, level=1),
               TrackedPlace(Item.LADDER, level=3)]
    barred = bosses_beaten_by_planted_items(planted)
    assert barred[1] == {*BOSSES_BEATEN_BY[Item.BOW], *BOSSES_BEATEN_BY[Item.RECORDER]}   # the wand is between
    assert barred[2] == frozenset()                                                      # one record, the raft
    assert set(barred) == {1, 2}


def test_ps_boss_05_records_are_the_fifteen_items_in_their_fixed_order() -> None:
    """PS-BOSS-05 (owner ruling, 2026-10-04): one record per ITEM, in the fixed order recorder,
    raft, wood boomerang, magical boomerang, ladder, wand, bow, red ring, magical key, red candle,
    silver arrow, book, then the bracelet, white-sword and coast caves' items before the shuffle;
    each in the level its item ended up in; added heart containers have none."""
    from zora.generate.pipeline import generate_world
    from zora.generate.steps.shuffle_items import POOL_ORDER
    order = [Item.RECORDER, Item.RAFT, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG, Item.LADDER, Item.WAND,
             Item.BOW, Item.RED_RING, Item.MAGICAL_KEY, Item.RED_CANDLE, Item.SILVER_ARROWS, Item.BOOK]
    assert list(POOL_ORDER) == order
    base = prg0()
    caves_before = [_cave(base, Destination.ARMOS_ITEM, OverworldItem).item,
                    _cave(base, Destination.WHITE_SWORD_CAVE, ItemCave).item,
                    _cave(base, Destination.COAST_ITEM, OverworldItem).item]
    for seed in SEEDS:
        world, result = generate_world(plan(cp5_with({"B40": ThreeState.OFF}), seed), base_rom())
        assert result.item_shuffle_result is not None
        records = result.item_shuffle_result.tracked
        assert [record.item for record in records] == [*order, *caves_before]
        for record in records:
            if record.level is not None:
                level = world.levels[record.level - 1]
                held = {room.item for room in level.rooms} | {stair.item for stair in level.block.staircases
                                                              if stair.return_dest in level.room_nums}
                assert record.item in held, (seed, record)


def test_ps_boss_05_applies_only_with_b40_off() -> None:
    """FL-OFF-04: PS-BOSS-05 is omitted (a MAY) while B40 is on and applied when it is off; the
    flag only decides whether the rule's input reaches the boss shuffle."""
    on = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1).steps
    off = plan(cp5_with({"B40": ThreeState.OFF}), 1).steps
    assert on.randomize_boss_groups and not off.randomize_boss_groups
    assert replace(off, randomize_boss_groups=True) == on


@pytest.mark.parametrize("seed", SEEDS)
def test_ps_boss_05_bars_the_picks_with_b40_off(seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """With B40 off, no boss the shuffle picks in levels 1 and 2 is beaten by an item at an end
    of the level's planted records; with B40 on the shuffle gets no bar (the MAY)."""
    from zora.generate.steps.monster_lists import MonsterShuffleResult, RoomLists, _boss_code
    from zora.generate.steps.shuffle_bosses import BOSS_TIERS, VANILLA_BOSS_TIER, shuffle_bosses
    from zora.generate.rng import IntRng
    from zora.model.levels import LevelBlock
    seen: list[tuple[int, frozenset[int], set[int]]] = []

    def watched(blocks: list[LevelBlock], lists: RoomLists, state: MonsterShuffleResult, rng: IntRng,
                beaten: dict[int, frozenset[int]] | None = None) -> None:
        rebossed = {level: [place for place in lists.rooms.get(level, [])
                            if _boss_code(lists.values[place]) in BOSS_TIERS[VANILLA_BOSS_TIER[level]]]
                    for level in (1, 2)}
        shuffle_bosses(blocks, lists, state, rng, beaten)
        for level, places in rebossed.items():
            seen.append((level, (beaten or {}).get(level, frozenset()),
                         {_boss_code(lists.values[place]) for place in places}))

    monkeypatch.setattr("zora.generate.generation_pass.shuffle_bosses", watched)
    generated.cache_clear()
    generated(cp5_with({"B40": ThreeState.OFF}), seed)
    assert seen and all(not (barred & picked) for _, barred, picked in seen)
    seen.clear()
    generated(cp5_with(), seed)
    generated.cache_clear()
    assert seen and all(not barred for _, barred, _ in seen)
