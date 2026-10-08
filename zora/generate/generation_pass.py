"""Generation flow (SH-FLOW-01..04) as a list of steps.

Two dungeon sets are built: levels 1-6 (six blobs) and levels 7-9 (three
blobs), each in its own 128-room block. Any step failure restarts the whole
generation (SH-FLOW-02) with the random stream continuing (SH-FLOW-03's
3-attempt cap is port-only and NOT reproduced; SH-FLOW-04's option loss on
restart is a probable bug and NOT reproduced — options are kept).

STEPS lists the generation in order, one Step per pass (context.Step): the
shape stage, built on SetWorld plans, which then become levels and room
blocks (build_levels); the post-shapes passes in pipeline order (B1, the
hints B2.5, the color sets B5, B2, B8's overworld monsters and hit points,
the group passes B4 with B5's sprite repack, the room exchange B3, the
overworld caves and shops), then the late gate, level 9's records
(PS-L9REC-01) and the map move toward the entrance (SH-MAP-03..07). The
ZORA extras (docs/zora-extras.md) join the item pool just before the
acceptance check. An accepted attempt is then written into the GameWorld
(ship), and the hint text and B10's DATA items follow on the shipped world.

Each step is switched by its own flag, named in the Step and tested only by
its enabled predicate (FL-OFF; flag_steps.py); a disabled step does not run,
and the enabled steps' random draws stay where they are. Each attempt runs on
a fresh GenerationContext, so a failed attempt leaves nothing behind.
"""
import copy

from zora.generate.acceptance_check import acceptance_check
from zora.generate.alternative_values import MVP_VALUES, AlternativeValues
from zora.generate.context import GenerationContext, GenerationResult, GenerationSettings, Step
from zora.generate.errors import GenerationFailure
from zora.generate.extra_options import NO_EXTRAS, ExtraOptions
from zora.generate.flag_steps import ALL_STEPS_ON, FlagSteps
from zora.generate.late_gate.gate import GateStats, late_gate
from zora.generate.rng import Rng
from zora.generate.shapes.bosses import place_bosses
from zora.generate.shapes.doors import place_doors
from zora.generate.shapes.enemies import EnemyPools, harvest_pools, place_enemies
from zora.generate.shapes.entrances import place_entrances
from zora.generate.shapes.gridgen import grow_set
from zora.generate.shapes.items import place_progression_items
from zora.generate.shapes.minimap import level9_left_edge
from zora.generate.shapes.numbering import number_with_frees
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.rooms import place_rooms
from zora.generate.shapes.special_rooms import place_special_rooms
from zora.generate.shapes.stairs import place_stairs
from zora.generate.shapes.world import D_WALL, CellPlan, SetWorld
from zora.generate.shapes.writeback import level9_records
from zora.generate.ship import Staged, build_sets, cave_item_bytes, ship, ship_hint_text
from zora.generate.steps.add_l4_sword import add_l4_sword
from zora.generate.steps.add_money_or_life_rooms import add_money_or_life_rooms
from zora.generate.steps.assign_hints_for_hint_type import assign_hints_for_hint_type
from zora.generate.steps.cave_entries import OverworldResult
from zora.generate.steps.change_bomb_upgrades import change_bomb_upgrades
from zora.generate.steps.change_enemy_hp import EnemyHpResult, change_boss_hp, change_most_enemy_hp
from zora.generate.steps.change_money_making_game import change_money_making_game
from zora.generate.steps.change_money_or_life_toll import change_money_or_life_toll
from zora.generate.steps.change_sword_hearts import change_sword_hearts, change_sword_hearts_from_five_hearts
from zora.generate.steps.dungeon_room_shuffle import exchange_rooms, second_drop_shuffle
from zora.generate.steps.extra_pool_items import ExtraPoolItems
from zora.generate.steps.feature_data import write_fixed_feature_data
from zora.generate.steps.hint_text import (
    PROGRESSIVE_NAMES,
    VANILLA_NAMES,
    generate_community_hint_text,
    generate_hint_text,
    magical_sword_cave_text,
)
from zora.generate.steps.item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from zora.generate.steps.monster_lists import MonsterShuffleResult, build_room_lists
from zora.generate.steps.move_last_boss_room_items import move_last_boss_room_items
from zora.generate.steps.move_map_near_entrance import move_map_near_entrance
from zora.generate.steps.person_appearances import draw_person_appearances
from zora.generate.steps.potion_shop import shuffle_blue_potion
from zora.generate.steps.randomize_boss_groups import randomize_boss_groups
from zora.generate.steps.randomize_letter import randomize_letter
from zora.generate.steps.randomize_magical_sword import check_magical_sword_hearts, randomize_magical_sword
from zora.generate.steps.randomize_mazes import randomize_mazes
from zora.generate.steps.recorder_to_new_dungeons import recorder_to_new_dungeons
from zora.generate.steps.shop_items_in_pool import shop_items_in_pool
from zora.generate.steps.shuffle_armos import shuffle_armos
from zora.generate.steps.shuffle_bomb_upgrade_men import shuffle_bomb_upgrade_men
from zora.generate.steps.shuffle_bosses import bosses_beaten_by_planted_items, shuffle_bosses
from zora.generate.steps.shuffle_caves import enrolled_entries, prg0_armos_screen, shuffle_caves
from zora.generate.steps.shuffle_dungeon_drops import shuffle_dungeon_drops, snapshot_shapes
from zora.generate.steps.shuffle_dungeon_monsters import shuffle_dungeon_monsters
from zora.generate.steps.shuffle_dungeon_palettes import shuffle_dungeon_palettes
from zora.generate.steps.shuffle_dungeon_text import shuffle_dungeon_text
from zora.generate.steps.shuffle_enemy_groups import shuffle_enemy_groups
from zora.generate.steps.shuffle_groups import GroupShuffleResult
from zora.generate.steps.shuffle_hungry_goriya import PRE_SHAPES_TILES, shuffle_hungry_goriya
from zora.generate.steps.shuffle_items import shuffle_items
from zora.generate.steps.shuffle_monsters_between_levels import VANILLA_ENEMY_TIER, shuffle_monsters_between_levels
from zora.generate.steps.shuffle_overworld_monsters import shuffle_overworld_monsters
from zora.generate.steps.shuffle_shop_items import extra_candles, shuffle_shop_items
from zora.generate.steps.shuffle_start_screen import shuffle_start_screen
from zora.generate.steps.speed_up_text import speed_up_text
from zora.generate.steps.start_with_four_hearts import start_with_four_hearts
from zora.model.enums import Destination, Enemy
from zora.model.game_world import GameWorld
from zora.model.levels import LEVEL_9, LEVEL_BLOCK_ROOMS, Level
from zora.model.overworld import ItemCave, Overworld

# The attempt cap: SH-FLOW-03 (revised spec) says a rebuild must retry, then
# fail visibly, never ship a half-built dungeon; the cap keeps a
# pathological seed from hanging.
MAX_ATTEMPTS = 2000


def generate_shapes(gw: GameWorld, rng: Rng, opts: ShapeOptions,
                    post_shapes: bool = True, feature_data: bool = False,
                    seed: int = 0, steps: FlagSteps = ALL_STEPS_ON,
                    extras: ExtraOptions = NO_EXTRAS, alternatives: AlternativeValues = MVP_VALUES) -> GenerationResult:
    """Run STEPS until an attempt ships into gw, restarting on failure.

    post_shapes=False skips every post-shapes pass (post-shapes-b1.md to -b3.md)
    and ships the shape stage straight into the late gate — used by tests
    of shape-stage invariants that the post-shapes passes legitimately move
    (hearts, triforces, cave items, person rooms, bosses and monsters).

    Enemy pools are harvested from the vanilla level data in `gw`
    (SH-ENEMY-01) before anything is overwritten.

    steps: the flag-switched steps that run (FL-OFF); extras: the ZORA
    extras; alternatives: the alternative values (FL-ALT). Each is tested by
    its step's enabled predicate or at its function's call site.
    """
    settings = GenerationSettings(opts, post_shapes, feature_data, seed, steps, extras, alternatives)
    level_sources = [gw.levels]
    if opts.second_quest_monsters:
        level_sources.append(gw.levels_2q)
    pools = harvest_pools(level_sources, opts)
    result = GenerationResult(pools=pools)
    # PS-GRUM-03: before the shapes stage, one value of the shapes stage's
    # stream, mod 4, sets the goriya tile ($AC/$A0/$A8/$B0).
    pre_tile = PRE_SHAPES_TILES[rng.below(4)] if post_shapes else None
    for _ in range(MAX_ATTEMPTS):
        result.attempts += 1
        context = GenerationContext(gw, settings, rng, result, pools, pre_tile)
        restart_reason = run_attempt(context)
        if restart_reason is None:
            return result
        result.restart_reasons.append(restart_reason)
    raise RuntimeError(
        f"shapes generation failed after {result.attempts} attempts / "
        f"{result.gate_attempts} late-gate retries (SH-FLOW-03: failing "
        "visibly rather than shipping a half-built dungeon)"
    )


def run_attempt(context: GenerationContext) -> str | None:
    """Run every enabled step in STEPS order on one attempt's context. Returns
    None when the attempt shipped, or the restart reason of the step that
    failed."""
    for step in STEPS:
        if not step.enabled(context.settings):
            continue
        try:
            step.run(context)
        except GenerationFailure as exc:
            if step.restart_label is None:
                raise
            return step.restart_label + str(exc)
    return None


# ---------------------------------------------------------------------------
# The shape stage
# ---------------------------------------------------------------------------

def _build_set(world: SetWorld, rng: Rng, opts: ShapeOptions,
               pools: EnemyPools) -> None:
    six_level = world.blob_count == 6
    grow_set(world, rng, six_level, opts)
    # numbering + SH-GRID-08 freeing must precede doors/entrances so level
    # numbers key the door weights and the parsed sizes stay monotone.
    number_with_frees(world, rng, opts)
    place_doors(world, rng, opts)
    place_entrances(world, rng, opts)
    place_stairs(world, rng, opts)
    place_special_rooms(world, rng, opts)
    place_rooms(world, rng, opts)
    place_bosses(world, rng, opts)
    place_enemies(world, rng, opts, pools)
    place_progression_items(world, rng, opts)


def shape_stage(context: GenerationContext) -> None:
    """Shapes, numbering, doors, entrances, stairs, special rooms, other
    rooms, bosses, enemies, compass/map/boomerangs, for both sets in spec
    order, on SetWorld plans."""
    gw = context.world
    for base, count in ((0, 6), (6, 3)):
        world = SetWorld(base_level=base, blob_count=count)
        world.base_inner_palettes = [
            gw.blocks[len(context.plans)].palette_bits(room_num)[1]
            for room_num in range(LEVEL_BLOCK_ROOMS)
        ]
        world.pos_tables = {level.level_num: list(level.item_position_table)
                            for level in gw.levels}
        _build_set(world, context.rng, context.settings.shape_options, context.pools)
        context.plans.append(world)
    # (the old pre-gate repair is gone, kept only as test scaffolding in
    # tests/test_stairs.py: the spec's wall openings happen inside the late
    # gate's repair)


def build_levels(context: GenerationContext) -> None:
    """The shape stage ends here: its plans become the levels and blocks the
    attempt ships, and every step from here on works on those. B1's staged
    results start from the base's cave bytes and the pre-shapes goriya tile."""
    _blank_unowned_plans(context.plans)
    context.item_shuffle_result = ItemShuffleResult(caves=cave_item_bytes(context.world),
                                                    goriya_tile=context.pre_shapes_goriya_tile)
    context.sets = build_sets(context.world, context.plans)


def _blank_unowned_plans(worlds: list[SetWorld]) -> None:
    """SH-GRID-17: the shapes stage's own blank of every cell no level owns
    and no stair uses — walls on all four sides (monster/layout/item 0 and
    trigger $01 are written at serialization) — BEFORE the gate, so a tail
    write that lands there (A43) is the cell's last write."""
    for world in worlds:
        for room_number in range(len(world.blob_of)):
            if world.blob_of[room_number] < 0 and room_number not in world.stairs:
                world.plans[room_number] = CellPlan(walls=[D_WALL] * 4)


# ---------------------------------------------------------------------------
# Post-shapes batch B1 (post-shapes-b1.md): PS-ITEM, PS-DROP, PS-GRUM,
# PS-BOMB and PS-MERCH, between the shape stage and the late gate, on the
# attempt's staged levels. Everything outside the two room blocks (the three
# special-cave item bytes, the goriya sprite tile, the toll) is staged in the
# ItemShuffleResult and written into the GameWorld only when the attempt
# ships. PS-MERCH-04, the toll draw, runs after the gate.
# ---------------------------------------------------------------------------

def start_post_shapes(context: GenerationContext) -> None:
    """What the post-shapes passes read of the shape stage as it ends: B2's
    room lists (build_room_lists) and PS-DROP's snapshot of the levels. B2's
    staged result starts with PRG0's enemy banks (PS-MONLV off keeps them)."""
    context.room_lists = build_room_lists(context.plans)
    context.shapes_snapshot = snapshot_shapes(context.sets.levels)
    context.monster_shuffle = MonsterShuffleResult(enemy_tiers=dict(VANILLA_ENEMY_TIER))


def shuffle_items_step(context: GenerationContext) -> None:
    """PS-ITEM: the big item shuffle (fifteen fixed places + dungeon hearts)."""
    shuffle_items(context.sets.levels, context.item_shuffle_result, context.rng, ItemShuffleOptions())


def shuffle_dungeon_drops_step(context: GenerationContext) -> None:
    """PS-DROP: the within-level drop shuffle."""
    assert context.shapes_snapshot is not None
    shuffle_dungeon_drops(context.sets.levels, context.shapes_snapshot, context.rng)


def shuffle_hungry_goriya_step(context: GenerationContext) -> None:
    """PS-GRUM: the hungry-goriya move."""
    shuffle_hungry_goriya(context.sets.levels, context.item_shuffle_result, context.rng)


def shuffle_bomb_upgrade_men_step(context: GenerationContext) -> None:
    """PS-BOMB: the bomb-upgrade person move."""
    shuffle_bomb_upgrade_men(context.sets.levels, context.item_shuffle_result, context.rng)


def add_money_or_life_rooms_step(context: GenerationContext) -> None:
    """PS-MERCH-01: adding life-or-money merchants."""
    add_money_or_life_rooms(context.sets.levels, context.item_shuffle_result, context.rng)


def assign_hints_for_hint_type_step(context: GenerationContext) -> None:
    """post-shapes-b25.md (no draws)."""
    context.hint_assignment = assign_hints_for_hint_type(context.sets.levels,
                                                         context.item_shuffle_result.bomb_levels)


def shuffle_dungeon_palettes_step(context: GenerationContext) -> None:
    """post-shapes-b5.md: the color sets, staged."""
    context.palettes = shuffle_dungeon_palettes(context.world, context.rng)


# ---------------------------------------------------------------------------
# Post-shapes batch B2 (post-shapes-b2.md): PS-BOSS, PS-MONLV and PS-MONRD.
# The boss shuffle and the monster moves change only the per-level room
# lists (RoomLists); the re-deal writes the lists into the room data. The
# sprite banks and the goriya's sprite tile are staged in the
# MonsterShuffleResult. A monster *value* is the spec's nine-bit view
# (PS-MONLV-02): the monster byte (list in bits 0-5, count index in bits 6-7)
# plus $100 when the layout byte's monster bit is set.
#
# Steps the spec marks MAY and this rebuild omits (each shifts only the random
# stream, late-gate A24): PS-BOSS-05 (levels 1-2 redraw a boss beaten by an
# item planted there; applied with B40 off, where it is a MUST),
# PS-BOSS-06's walk of the second-quest lists, PS-MONLV-05 (the bubble rule,
# which never fires), PS-MONLV's second-quest redraws, and PS-MONRD-03's
# level-9 Triforce-room pointer (the gate rewrites it). Cave placement and
# the recorder update, which the spec places between the monster moves and the
# re-deal, touch no dungeon room and run with the overworld passes.
# ---------------------------------------------------------------------------

def shuffle_bosses_step(context: GenerationContext) -> None:
    """PS-BOSS. PS-BOSS-05 applies with Randomize Boss Groups off (B40): the
    boss-group pass then does not redraw the bosses picked here, so the rule
    is observable and MUST apply (FL-OFF-04)."""
    assert context.room_lists is not None and context.monster_shuffle is not None
    beaten = (None if context.settings.steps.randomize_boss_groups
              else bosses_beaten_by_planted_items(context.item_shuffle_result.tracked))
    shuffle_bosses(context.sets.blocks, context.room_lists, context.monster_shuffle, context.rng, beaten)


def shuffle_monsters_between_levels_step(context: GenerationContext) -> None:
    """PS-MONLV: enemy banks and monster redraws."""
    assert context.room_lists is not None and context.monster_shuffle is not None
    shuffle_monsters_between_levels(context.sets.blocks, context.sets.levels, context.room_lists,
                                    context.monster_shuffle, context.rng)


def shuffle_dungeon_monsters_step(context: GenerationContext) -> None:
    """PS-MONRD: the per-level monster re-deal, which writes the lists into the rooms."""
    assert context.room_lists is not None and context.monster_shuffle is not None
    shuffle_dungeon_monsters(context.sets.blocks, context.sets.levels, context.room_lists,
                             context.monster_shuffle, context.rng)


# ---------------------------------------------------------------------------
# B8 (post-shapes-b8.md), B4 (post-shapes-b4.md) and B3 (post-shapes-b3.md)
# ---------------------------------------------------------------------------

def stage_overworld(context: GenerationContext) -> None:
    """The staged copy of the overworld that the later passes share, and the
    staged hit points and group results, from the base's (no draws)."""
    context.overworld = copy.deepcopy(context.world.overworld)
    context.hit_points = EnemyHpResult.unchanged(context.world.enemies)
    context.groups = GroupShuffleResult()


def shuffle_overworld_monsters_step(context: GenerationContext) -> None:
    """PS-OWM: the overworld monsters, on the staged overworld."""
    assert context.overworld is not None
    shuffle_overworld_monsters(context.world, context.overworld, context.rng)


def change_most_enemy_hp_step(context: GenerationContext) -> None:
    """PS-HP-01."""
    assert context.hit_points is not None
    change_most_enemy_hp(context.hit_points, context.rng)


def change_boss_hp_step(context: GenerationContext) -> None:
    """PS-HP-02."""
    assert context.hit_points is not None
    change_boss_hp(context.hit_points, context.rng)


def shuffle_enemy_groups_step(context: GenerationContext) -> None:
    """PS-EGRP, with B5's sprite repack."""
    groups, monster_shuffle = context.groups, context.monster_shuffle
    assert groups is not None and monster_shuffle is not None
    assert context.overworld is not None and context.hit_points is not None
    groups.enemy_deal, groups.goriya_tile, groups.rooms_redrawn = shuffle_enemy_groups(
        context.sets.blocks, context.world,
        monster_shuffle.enemy_tiers[context.item_shuffle_result.goriya_level], context.rng,
        context.overworld, context.hit_points.hp[Enemy.ZOL], groups.staged
    )


def randomize_boss_groups_step(context: GenerationContext) -> None:
    """PS-BGRP."""
    groups = context.groups
    assert groups is not None
    groups.boss_deal, groups.bosses_redrawn = randomize_boss_groups(context.sets.blocks, context.world,
                                                                    context.rng, groups.staged)


def exchange_rooms_step(context: GenerationContext) -> None:
    """PS-XCHG: the exchange between dungeons, only with the full room shuffle (C14 = 2)."""
    context.result.room_shuffle = exchange_rooms(context.sets.levels, context.rng)


def second_drop_shuffle_step(context: GenerationContext) -> None:
    """PS-XCHG-05: the room exchange's last step, which also needs Shuffle Dungeon Drops (B15)."""
    second_drop_shuffle(context.sets.levels, context.rng)


# ---------------------------------------------------------------------------
# The overworld passes (overworld-behavior.md): the dungeons' start rooms are
# final here (OW-CAVE-03); VA-REJ-02 lists cave placement before the late
# gate. OW-SHOP-06's front-door guarantees are judged by the acceptance check
# (E4/E5).
# ---------------------------------------------------------------------------

def enroll_caves(context: GenerationContext) -> None:
    """OW-CAVE-02 step 1 (no draws); the armos screen is PRG0's unless Shuffle Armos moves it."""
    assert context.overworld is not None
    context.cave_entries = enrolled_entries(context.overworld)
    context.armos_screen = prg0_armos_screen(context.overworld)


def shuffle_armos_step(context: GenerationContext) -> None:
    """OW-CAVE-05: the formation tables, screen 36 and the re-pointed entry."""
    assert context.overworld is not None
    context.armos_screen = shuffle_armos(context.overworld, context.rng, context.cave_entries)


def shuffle_caves_step(context: GenerationContext) -> None:
    """OW-CAVE-02 step 3 and OW-CAVE-04's write-back."""
    assert context.overworld is not None and context.armos_screen is not None
    context.caves = shuffle_caves(context.overworld, context.cave_entries, context.armos_screen,
                                  _start_rooms(context.plans), context.rng,
                                  context.settings.steps.shuffle_take_any_road_caves,
                                  context.settings.extras.gates)


def _start_rooms(worlds: list[SetWorld]) -> dict[int, int]:
    """Each dungeon's start room (LevelInfo_StartRoomId): its entrance cell."""
    return {level: room_number for world in worlds for level, room_number in world.entrance.items()}


def recorder_to_new_dungeons_step(context: GenerationContext) -> None:
    """OW-WARP-01."""
    assert context.overworld is not None and context.caves is not None
    recorder_to_new_dungeons(context.overworld, context.caves)


def shuffle_shop_items_step(context: GenerationContext) -> None:
    """OW-SHOP-02 to OW-SHOP-04."""
    assert context.overworld is not None
    shuffle_shop_items(context.overworld, context.rng)


def extra_candles_step(context: GenerationContext) -> None:
    """OW-SHOP-05."""
    assert context.overworld is not None
    extra_candles(context.overworld)


# ---------------------------------------------------------------------------
# The late gate and the passes after it
# ---------------------------------------------------------------------------

def late_gate_step(context: GenerationContext) -> None:
    """Late room-deal acceptance gate (VA-REJ-01..04): a per-level attempt
    loop sharing one 1,000-attempt budget, with the placement, swap-safety
    and connectivity checks. Connectivity is required of final output but is
    not a shapes-stage restart site, since stair placement may leave pieces
    unjoined. Budget exhaustion (VA-REJ-04) is the only late-gate outcome
    that restarts the whole generation; a rejected attempt costs one attempt
    of the budget."""
    result = context.result
    context.l1_gate_entry = _l1_census(context.sets.levels)
    stats = GateStats()
    try:
        late_gate(context.sets.levels, context.rng, stats)
    except GenerationFailure:
        result.gate_attempts += 1
        result.gate_rejections += stats.rejections
        result.gate_per_level.update(stats.per_level)
        result.gate_kinds.update(stats.kinds)
        result.gate_exhaustion.extend(stats.exhaustion)
        result.gate_surveys.append((True, stats.survey))
        raise
    result.gate_surveys.append((False, stats.survey))
    result.gate_rejections += stats.rejections
    result.gate_per_level.update(stats.per_level)
    result.gate_kinds.update(stats.kinds)


def _l1_census(levels: list[Level]) -> tuple[int, int]:
    """Level 1 at gate entry: person rooms, and rooms whose in-room move
    table restricts the walk (walk.py's table)."""
    from zora.generate.late_gate.walk import _FREE_MOVES, _moves
    rooms = levels[0].rooms
    persons = sum(room.is_person for room in rooms)
    restrict = sum(_moves(room, None) is not _FREE_MOVES for room in rooms)
    return persons, restrict


def level9_records_step(context: GenerationContext) -> None:
    """PS-L9REC-01: level 9's records, after the gate (no draws)."""
    level9 = context.sets.levels[LEVEL_9 - 1]
    level9_records(level9, level9.block)


def shuffle_start_screen_step(context: GenerationContext) -> None:
    """OW-START-01: after the gate and level 9's record step, before map
    relocation; the exchange itself is written when the attempt ships."""
    context.start = shuffle_start_screen(context.rng)


def move_last_boss_room_items_step(context: GenerationContext) -> None:
    """VA-REJ-20: after the start-screen pass, before the map move; no receiving room
    restarts the pass."""
    move_last_boss_room_items(context.sets.levels[LEVEL_9 - 1], context.rng)


def move_map_near_entrance_step(context: GenerationContext) -> None:
    """SH-MAP-03..07, after the gate: map relocation (best-effort; never rejects)."""
    for level in context.sets.generation_order:
        move_map_near_entrance(level, context.rng)


def change_money_or_life_toll_step(context: GenerationContext) -> None:
    """PS-MERCH-02 pricing (late)."""
    change_money_or_life_toll(context.item_shuffle_result, context.rng)


# The ZORA extras join the pool after every pass that reads $03 as "no item"
# (docs/zora-extras.md section 3); neither is a tracked item.

def randomize_magical_sword_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    randomize_magical_sword(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                            context.overworld, context.rng)


def randomize_letter_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    randomize_letter(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                     context.overworld, context.rng)


def shop_items_in_pool_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    shop_items_in_pool(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                       context.overworld, context.rng)


def shuffle_blue_potion_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    shuffle_blue_potion(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                        context.overworld, context.rng)


def add_l4_sword_step(context: GenerationContext) -> None:
    """Add L4 Sword (docs/design/l4-sword.md): the progressive sword in a level-9 room, after every
    step that changes level 9's rooms."""
    add_l4_sword(context.sets.levels, context.rng)


def change_sword_hearts_before_check(context: GenerationContext) -> None:
    """With Randomize Magical Sword on, the sword caves' requirements are drawn
    here, before the checks, so the heart check judges the exact N (owner
    requirement); otherwise after the attempt ships (change_sword_hearts_after_ship)."""
    assert context.overworld is not None
    _change_sword_hearts(context, context.overworld)


def acceptance_check_step(context: GenerationContext) -> None:
    """acceptance.md: the finished attempt is judged; any failure restarts the
    whole seed (VA-REJ-06)."""
    assert context.overworld is not None and context.caves is not None
    _reject_unless_accepted(context, acceptance_check(context.sets.levels, context.item_shuffle_result,
                                                      context.overworld, context.caves,
                                                      context.settings.extras.logic_rules))


def check_magical_sword_hearts_step(context: GenerationContext) -> None:
    """Randomize Magical Sword's heart check (owner requirement), judged as an acceptance check."""
    assert context.overworld is not None and context.caves is not None
    accepted = has_magical_sword_hearts(context.sets.levels, context.item_shuffle_result,
                                        context.extra_pool_items,
                                        OverworldResult(context.overworld, context.caves),
                                        context.settings.extras)
    _reject_unless_accepted(context, None if accepted else "hearts")


def _reject_unless_accepted(context: GenerationContext, failure: str | None) -> None:
    if failure is not None:
        context.result.acceptance_rejections[failure] += 1
        raise GenerationFailure(failure)


def has_magical_sword_hearts(levels: list[Level], item_shuffle_result: ItemShuffleResult,
                             extra_pool_items: ExtraPoolItems, overworld_state: OverworldResult,
                             extras: ExtraOptions) -> bool:
    """Randomize Magical Sword's heart check (owner requirement), on the requirements the two
    sword caves ask for in this pass."""
    overworld = overworld_state.overworld
    white_sword_cave = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    magical_sword_cave = overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert white_sword_cave is not None and magical_sword_cave is not None
    return check_magical_sword_hearts(levels, item_shuffle_result, extra_pool_items, overworld,
                                      overworld_state.caves, hearts_required=magical_sword_cave.heart_requirement,
                                      starting_hearts=extras.starting_heart_containers,
                                      white_sword_hearts_required=white_sword_cave.heart_requirement,
                                      rules=extras.logic_rules)


def ship_step(context: GenerationContext) -> None:
    """The accepted attempt: its figures into the result, and its staged
    results into the GameWorld (ship.SHIP_STEPS)."""
    result = context.result
    result.item_shuffle_result = context.item_shuffle_result
    result.monster_shuffle = context.monster_shuffle
    result.groups = context.groups
    result.extra_pool_items = context.extra_pool_items
    result.l1_gate_entry = context.l1_gate_entry
    result.sets = context.plans
    result.hint_level9_left_column = level9_left_edge(context.plans[1])
    overworld_state = None
    if context.overworld is not None and context.caves is not None:
        overworld_state = OverworldResult(context.overworld, context.caves)
        result.overworld = context.caves
    ship(context.world, Staged(context.sets, context.item_shuffle_result, overworld_state,
                               context.hint_assignment, context.monster_shuffle, context.hit_points,
                               context.groups, context.palettes, context.start, context.extra_pool_items))


# ---------------------------------------------------------------------------
# After ship, on the shipped world: the hint text runs after the item and map
# passes (HT-TEXT-04) and reads what they wrote: the shipped level 9 (trio
# rooms and quadrants), the cave items B1 placed (white-sword and coast
# items), the group passes' mixed lists (the compass family). B10's DATA
# items follow it, so the level-9 refusal text can be overwritten in place.
# ---------------------------------------------------------------------------

def draw_person_appearances_step(context: GenerationContext) -> None:
    """FP-PERSON-01 owns the cave person appearances; the hint text names
    three pairs of them, so it draws them first, at the stream position
    where the hint pass drew its six."""
    draw_person_appearances(context.world, context.rng)


def change_sword_hearts_after_ship(context: GenerationContext) -> None:
    """FP-SWORD-01's heart counts, before the hint text (with Randomize
    Magical Sword off; see change_sword_hearts_before_check)."""
    _change_sword_hearts(context, context.world.overworld)


def _change_sword_hearts(context: GenerationContext, overworld: Overworld) -> None:
    """FP-SWORD-01, or FL-ALT-03's white-sword range with C20 at 1; the magical sword's range is
    the ZORA cap's (zora_flags.magical_sword_heart_range) either way."""
    magical_sword_hearts = context.settings.extras.magical_sword_hearts
    if context.settings.alternatives.change_sword_hearts_from_five_hearts:
        change_sword_hearts_from_five_hearts(overworld, context.rng, magical_sword_hearts)
    else:
        change_sword_hearts(overworld, context.rng, magical_sword_hearts)


def randomize_mazes_step(context: GenerationContext) -> None:
    """Randomize Lost Hills / Dead Woods (owner's 2.0 flags): the sequences, before the hint text,
    which sells each in its hint shop."""
    gates = context.settings.extras.gates
    context.maze_offers = randomize_mazes(context.world.overworld, context.rng, gates.lost_hills, gates.dead_woods)


def generate_hint_text_step(context: GenerationContext) -> None:
    """HT-TEXT, or FL-ALT-04's community hints with C03 at 2; with Randomize Magical Sword on,
    the cave's own text names the item it offers."""
    assert context.hint_assignment is not None
    gw = context.world
    # PI-TEXT-01: with Progressive Items on, the texts name upgrade-line items by their line
    names = PROGRESSIVE_NAMES if context.settings.extras.progressive_items else VANILLA_NAMES
    cave_text = magical_sword_cave_text(gw, names) if context.settings.extras.randomize_magical_sword else None
    if context.settings.alternatives.generate_community_hint_text:
        context.hint_text = generate_community_hint_text(gw, context.item_shuffle_result, context.hint_assignment,
                                                         context.rng, cave_text, names, context.maze_offers)
    else:
        context.hint_text = generate_hint_text(gw, context.item_shuffle_result, context.hint_assignment,
                                               context.rng, cave_text, names, context.maze_offers)


def shuffle_dungeon_text_step(context: GenerationContext) -> None:
    """HT-TEXT-04."""
    assert context.hint_text is not None
    context.hint_text = shuffle_dungeon_text(context.hint_text, context.rng)


def ship_hint_text_step(context: GenerationContext) -> None:
    assert context.hint_text is not None
    ship_hint_text(context.world, context.hint_text)


# B10's DATA items (features-behavior.md). Bomb/mmg values are drawn here
# rather than earlier in the stream; the spec only constrains their marginal
# distributions, so stream position does not matter. Book is an Atlas
# (FP-BOOK-01) is a code patch only (zora/rom/code_patches.py).

def change_bomb_upgrades_step(context: GenerationContext) -> None:
    change_bomb_upgrades(context.world, context.rng)


def change_money_making_game_step(context: GenerationContext) -> None:
    change_money_making_game(context.world, context.rng)


def speed_up_text_step(context: GenerationContext) -> None:
    speed_up_text(context.world)


def write_fixed_feature_data_step(context: GenerationContext) -> None:
    write_fixed_feature_data(context.world, context.settings.seed)


def start_with_four_hearts_step(context: GenerationContext) -> None:
    start_with_four_hearts(context.world)


# ---------------------------------------------------------------------------
# The step list
# ---------------------------------------------------------------------------

def post_shapes(settings: GenerationSettings) -> bool:
    return settings.post_shapes


def feature_data(settings: GenerationSettings) -> bool:
    return settings.post_shapes and settings.feature_data


STEPS: tuple[Step, ...] = (
    # The shape stage: one step for now (it still works on CellPlan)
    Step("shape_stage", "", shape_stage, restart_label=""),
    Step("build_levels", "", build_levels),
    # B1
    Step("start_post_shapes", "", start_post_shapes, post_shapes),
    Step("shuffle_items", "C06", shuffle_items_step, post_shapes),
    Step("shuffle_dungeon_drops", "B15", shuffle_dungeon_drops_step,
         lambda s: s.post_shapes and s.steps.shuffle_dungeon_drops),
    Step("shuffle_hungry_goriya", "B28", shuffle_hungry_goriya_step,
         lambda s: s.post_shapes and s.steps.shuffle_hungry_goriya),
    Step("shuffle_bomb_upgrade_men", "B29", shuffle_bomb_upgrade_men_step, post_shapes),
    Step("add_money_or_life_rooms", "B22", add_money_or_life_rooms_step,
         lambda s: s.post_shapes and s.steps.add_money_or_life_rooms),
    # B2.5 and B5
    Step("assign_hints_for_hint_type", "C03", assign_hints_for_hint_type_step, post_shapes),
    Step("shuffle_dungeon_palettes", "B27", shuffle_dungeon_palettes_step,
         lambda s: s.post_shapes and s.steps.shuffle_dungeon_palettes),
    # B2
    Step("shuffle_bosses", "B34", shuffle_bosses_step,
         lambda s: s.post_shapes and s.steps.shuffle_bosses, restart_label="B2: "),
    Step("shuffle_monsters_between_levels", "B36", shuffle_monsters_between_levels_step,
         lambda s: s.post_shapes and s.steps.shuffle_monsters_between_levels, restart_label="B2: "),
    Step("shuffle_dungeon_monsters", "B32", shuffle_dungeon_monsters_step, post_shapes, restart_label="B2: "),
    # B8
    Step("stage_overworld", "", stage_overworld, post_shapes),
    Step("shuffle_overworld_monsters", "B31", shuffle_overworld_monsters_step,
         lambda s: s.post_shapes and s.steps.shuffle_overworld_monsters),
    Step("change_most_enemy_hp", "C09", change_most_enemy_hp_step,
         lambda s: s.post_shapes and s.steps.change_most_enemy_hp),
    Step("change_boss_hp", "C10", change_boss_hp_step, lambda s: s.post_shapes and s.steps.change_boss_hp),
    # B4
    Step("shuffle_enemy_groups", "B42", shuffle_enemy_groups_step,
         lambda s: s.post_shapes and s.steps.shuffle_enemy_groups),
    Step("randomize_boss_groups", "B40", randomize_boss_groups_step,
         lambda s: s.post_shapes and s.steps.randomize_boss_groups),
    # B3
    Step("dungeon_room_shuffle", "C14", exchange_rooms_step, lambda s: s.post_shapes and s.steps.exchange_rooms),
    Step("second_drop_shuffle", "C14 + B15", second_drop_shuffle_step,
         lambda s: s.post_shapes and s.steps.exchange_rooms and s.steps.shuffle_dungeon_drops),
    # The overworld passes
    Step("enroll_caves", "", enroll_caves, post_shapes),
    Step("shuffle_armos", "B13", shuffle_armos_step, lambda s: s.post_shapes and s.steps.shuffle_armos),
    Step("shuffle_caves", "", shuffle_caves_step, post_shapes),
    Step("recorder_to_new_dungeons", "B01", recorder_to_new_dungeons_step,
         lambda s: s.post_shapes and s.steps.recorder_to_new_dungeons),
    Step("shuffle_shop_items", "B08", shuffle_shop_items_step,
         lambda s: s.post_shapes and s.steps.shuffle_shop_items),
    Step("extra_candles", "B09", extra_candles_step, lambda s: s.post_shapes and s.steps.extra_candles),
    # The late gate and after
    Step("late_gate", "", late_gate_step, restart_label="late gate: "),
    Step("level9_records", "", level9_records_step),
    Step("shuffle_start_screen", "C04", shuffle_start_screen_step,
         lambda s: s.post_shapes and s.steps.shuffle_start_screen),
    Step("move_last_boss_room_items", "", move_last_boss_room_items_step, restart_label="last-boss rooms: "),
    Step("move_map_near_entrance", "", move_map_near_entrance_step),
    Step("change_money_or_life_toll", "B23", change_money_or_life_toll_step,
         lambda s: s.post_shapes and s.steps.change_money_or_life_toll),
    # The ZORA extras and the acceptance check
    Step("randomize_magical_sword", "ZORA randomize_magical_sword", randomize_magical_sword_step,
         lambda s: s.post_shapes and s.extras.randomize_magical_sword),
    Step("randomize_letter", "ZORA randomize_letter", randomize_letter_step,
         lambda s: s.post_shapes and s.extras.randomize_letter),
    Step("shop_items_in_pool", "ZORA shop_items_in_pool", shop_items_in_pool_step,
         lambda s: s.post_shapes and s.extras.shop_items_in_pool),
    Step("shuffle_blue_potion", "ZORA shuffle_blue_potion", shuffle_blue_potion_step,
         lambda s: s.post_shapes and s.extras.shuffle_blue_potion),
    Step("add_l4_sword", "ZORA add_l4_sword", add_l4_sword_step, lambda s: s.post_shapes and s.extras.add_l4_sword),
    Step("change_sword_hearts", "B10 + ZORA randomize_magical_sword", change_sword_hearts_before_check,
         lambda s: (s.post_shapes and s.extras.randomize_magical_sword and s.feature_data
                    and s.steps.change_sword_hearts)),
    Step("acceptance_check", "", acceptance_check_step, post_shapes, restart_label="acceptance: "),
    Step("check_magical_sword_hearts", "ZORA randomize_magical_sword", check_magical_sword_hearts_step,
         lambda s: s.post_shapes and s.extras.randomize_magical_sword, restart_label="acceptance: "),
    Step("ship", "", ship_step),
    # On the shipped world
    Step("draw_person_appearances", "", draw_person_appearances_step, post_shapes),
    Step("change_sword_hearts", "B10", change_sword_hearts_after_ship,
         lambda s: (s.post_shapes and s.feature_data and s.steps.change_sword_hearts
                    and not s.extras.randomize_magical_sword)),
    Step("randomize_mazes", "ZORA randomize_lost_hills + randomize_dead_woods", randomize_mazes_step,
         lambda s: s.post_shapes and (s.extras.gates.lost_hills or s.extras.gates.dead_woods)),
    Step("generate_hint_text", "C03", generate_hint_text_step, post_shapes),
    Step("shuffle_dungeon_text", "B19", shuffle_dungeon_text_step,
         lambda s: s.post_shapes and s.steps.shuffle_dungeon_text),
    Step("ship_hint_text", "", ship_hint_text_step, post_shapes),
    Step("change_bomb_upgrades", "B12", change_bomb_upgrades_step,
         lambda s: feature_data(s) and s.steps.change_bomb_upgrades),
    Step("change_money_making_game", "B11", change_money_making_game_step,
         lambda s: feature_data(s) and s.steps.change_money_making_game),
    Step("speed_up_text", "B54", speed_up_text_step, lambda s: feature_data(s) and s.steps.speed_up_text),
    Step("write_fixed_feature_data", "", write_fixed_feature_data_step, feature_data),
    Step("start_with_four_hearts", "C16 = 3", start_with_four_hearts_step,
         lambda s: s.alternatives.start_with_four_hearts),
)
