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
from collections import Counter
from dataclasses import replace

from ..flags.fields import ItemShuffleScope, Level9Requirement, WoodenSwordState
from ..model.enums import Destination, Enemy
from ..model.game_world import GameWorld
from ..model.levels import LEVEL_9, LEVEL_BLOCK_ROOMS, Level
from ..model.overworld import ItemCave, Overworld
from .acceptance_check import LogicRules, acceptance_check
from .alternative_values import MVP_VALUES, AlternativeValues
from .boss_sounds import boss_sound_end_pass, check_boss_sounds
from .context import GenerationContext, GenerationResult, GenerationSettings, Step
from .errors import GenerationFailure
from .extra_options import NO_EXTRAS, ExtraOptions
from .flag_steps import ALL_STEPS_ON, FlagSteps
from .item_spots import check_item_spots
from .late_gate.gate import GateStats, late_gate
from .late_gate.gatekeeper import (
    GATEKEEPER_LEVELS,
    TRIES_WITHOUT_GATE,
    GatekeeperPlan,
    gatekeeper_problems,
    heart_place_rooms,
    place_gatekeeper,
)
from .rng import Rng
from .shapes.bosses import place_bosses
from .shapes.doors import place_doors
from .shapes.enemies import EnemyPools, harvest_pools, place_enemies
from .shapes.entrances import place_entrances
from .shapes.gridgen import grow_set
from .shapes.items import place_progression_items
from .shapes.minimap import level9_left_edge
from .shapes.numbering import number_with_frees
from .shapes.options import ShapeOptions
from .shapes.rooms import place_rooms
from .shapes.special_rooms import place_special_rooms
from .shapes.stairs import place_stairs
from .shapes.world import D_WALL, CellPlan, SetWorld
from .shapes.writeback import level9_records
from .ship import BOSS_BANKS, Staged, build_sets, cave_item_bytes, ship, ship_hint_text
from .steps.add_l4_sword import add_l4_sword
from .steps.add_money_or_life_rooms import add_money_or_life_rooms
from .steps.assign_hints_for_hint_type import PRG0_RECORDED_LEVELS, HintAssignmentResult, assign_hints_for_hint_type
from .steps.bait_in_pool import bait_in_pool
from .steps.cave_entries import OverworldResult
from .steps.change_bomb_upgrades import change_bomb_upgrades
from .steps.change_enemy_hp import (
    EnemyHpResult,
    cap_level_9_vire_hp,
    change_boss_hp,
    change_most_enemy_hp,
    maximum_boss_hp,
    maximum_enemy_hp,
    zero_ganon_hp,
)
from .steps.change_money_making_game import change_money_making_game
from .steps.change_money_or_life_toll import change_money_or_life_toll
from .steps.change_sword_hearts import change_sword_hearts
from .steps.dungeon_quest import (
    SET_LEVELS,
    SetSource,
    draw_attempt_set_sources,
    draw_seed_set_sources,
    monsters_take_second_quest_path,
    vanilla_set,
)
from .steps.dungeon_room_shuffle import exchange_rooms, second_drop_shuffle
from .steps.expanded_dungeon_locations import (
    ARMOS_SPOT_SCREEN,
    FIRST_QUEST,
    SECOND_QUEST,
    apply_deal,
    deal_entries,
    deal_expanded_dungeon_locations,
)
from .steps.extra_pool_items import ExtraPoolItems
from .steps.feature_data import LEVEL_9_SWORD_REFUSAL_TEXT, write_fixed_feature_data
from .steps.force_overworld_block import force_overworld_block
from .steps.highlight_no_drop_rooms import highlight_no_drop_rooms
from .steps.hint_text import (
    PROGRESSIVE_NAMES,
    VANILLA_NAMES,
    HintTextResult,
    generate_blank_hint_text,
    generate_community_hint_text,
    generate_hint_text,
    generate_normal_hint_text,
)
from .steps.item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from .steps.level_2_sword import join_level_2_sword
from .steps.level_9_entry import draw_level_9_gate, refusal_text
from .steps.mixed_overworld_quest import (
    SECOND_QUEST_DEALT_POSITIONS,
    mix_overworld_quest,
    prepare_second_quest_screen_11,
    second_quest_overworld,
    show_second_quest_overworld,
    staged_second_quest_entries,
)
from .steps.monster_lists import MonsterShuffleResult, build_room_lists
from .steps.move_last_boss_room_items import move_last_boss_room_items
from .steps.move_map_near_entrance import move_map_near_entrance
from .steps.oops_all import oops_all_bosses, oops_all_enemies
from .steps.person_appearances import draw_person_appearances
from .steps.place_triforces import place_triforces
from .steps.potion_shop import shuffle_blue_potion
from .steps.randomize_boss_groups import randomize_boss_groups
from .steps.randomize_letter import randomize_letter
from .steps.randomize_magical_sword import (
    check_magical_sword_hearts,
    randomize_magical_sword,
    white_sword_cave_hearts_met,
)
from .steps.randomize_mazes import randomize_mazes
from .steps.recorder_to_new_dungeons import recorder_to_new_dungeons
from .steps.remove_most_open_stairs import remove_most_open_stairs
from .steps.shop_items_in_pool import shop_items_in_pool
from .steps.shuffle_armos import shuffle_armos
from .steps.shuffle_bomb_upgraders import shuffle_bomb_upgraders
from .steps.shuffle_bosses import bosses_beaten_by_planted_items, shuffle_bosses
from .steps.shuffle_caves import (
    cave_walk_parts,
    enrolled_entries,
    leave_wood_sword_cave_in_place,
    prg0_armos_screen,
    shuffle_caves,
)
from .steps.shuffle_dungeon_drops import shuffle_dungeon_drops, snapshot_shapes
from .steps.shuffle_dungeon_monsters import RedealOptions, shuffle_dungeon_monsters
from .steps.shuffle_dungeon_palettes import shuffle_dungeon_palettes
from .steps.shuffle_dungeon_text import shuffle_dungeon_text
from .steps.shuffle_enemy_groups import shuffle_enemy_groups
from .steps.shuffle_groups import GroupShuffleResult
from .steps.shuffle_hungry_goriya import PRE_SHAPES_TILES, shuffle_hungry_goriya
from .steps.shuffle_items import keep_items_in_place, shuffle_items, shuffle_items_within_levels
from .steps.shuffle_monsters_between_levels import (
    VANILLA_ENEMY_TIER,
    level_quests,
    second_quest_list_values,
    shuffle_monsters_between_levels,
)
from .steps.shuffle_overworld_monsters import shuffle_overworld_monsters
from .steps.shuffle_shop_items import extra_candles, shuffle_shop_items
from .steps.shuffle_start_screen import (
    FULL_START_SCREENS,
    START_SCREENS,
    shuffle_start_screen,
    start_on_wood_sword_screen,
)
from .steps.shuffle_wood_sword import shuffle_wood_sword
from .steps.speed_up_text import speed_up_text
from .steps.starting_hearts import set_starting_hearts
from .steps.swap_start_rooms import swap_start_rooms
from .steps.sword_states import BOMB_UPGRADE_STATES, change_sword_caves, red_candle_for_maximum_boss_health
from .steps.wood_sword_behind_blocks import wood_sword_extra_screens

# The attempt cap: SH-FLOW-03 (revised spec) says a rebuild must retry, then
# fail visibly, never ship a half-built dungeon; the cap keeps a
# pathological seed from hanging.
MAX_ATTEMPTS = 2000
HALF_START_ROOM_SWAP = "the start-room swap on shaped dungeons needs the post-shapes passes (PS-START)"


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
    result.seed_set_sources = draw_seed_set_sources(alternatives.dungeon_quest, rng)
    shaped = result.seed_set_sources is not None and not all(source.is_vanilla for source in result.seed_set_sources)
    if opts.start_room_swap and not post_shapes and shaped:       # None: Mixed Quest, two vanilla sets
        # Half a swap: the shape stage draws entrances off the bottom row (SH-GRID-02, SH-ENT-01) and
        # only PS-START, a post-shapes pass, moves the start rooms to the edge (no flag string does this)
        raise ValueError(HALF_START_ROOM_SWAP)
    for _ in range(MAX_ATTEMPTS):
        result.attempts += 1
        context = GenerationContext(gw, settings, rng, result, pools, pre_tile)
        restart_reason = run_attempt(context)
        if restart_reason is None:
            gw.record_level_entry_codes()          # FP-ENTR-01/02: the rooms' owners are final
            return result
        result.restart_reasons.append(restart_reason)
    raise RuntimeError(
        f"generation failed after {result.attempts} attempts, none accepted (VA-REJ-06); "
        f"restarts: {describe_restarts(result.restart_reasons)}"
    )


# Who restarted an attempt, by its step's restart label; a reason with none
# of these labels comes from the shape stage, whose label is empty
RESTART_STAGES = {
    "acceptance: ": "the acceptance check",
    "late gate: ": "the late gate",
    "B81: ": "Force Overworld Block (B81)",
    "B2: ": "the monster shuffles (B2)",
    "last-boss rooms: ": "the last-boss room items",
}
SHAPE_STAGE = "the shape stage"
# The most common reasons named for each stage in the attempt-cap error
REASONS_NAMED = 2


def describe_restarts(restart_reasons: list[str]) -> str:
    """The attempt-cap error's account of what kept failing: each stage that restarted an
    attempt, most restarts first, with its count and its most common reasons (an acceptance
    rejection's code, such as E1)."""
    by_stage: dict[str, Counter[str]] = {}
    for reason in restart_reasons:
        label = next((label for label in RESTART_STAGES if reason.startswith(label)), "")
        stage = RESTART_STAGES.get(label, SHAPE_STAGE)
        by_stage.setdefault(stage, Counter())[reason.removeprefix(label)] += 1
    stages = sorted(by_stage.items(), key=lambda item: -item[1].total())
    return "; ".join(
        f"{stage} {reasons.total()} ("
        + ", ".join(f"{reason} {count}" for reason, count in reasons.most_common(REASONS_NAMED))
        + (", ..." if len(reasons) > REASONS_NAMED else "") + ")"
        for stage, reasons in stages)


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
    # SH-SRC-01/09: the sources of this attempt's two sets (Mixed Quest's coin is drawn again)
    context.set_sources = draw_attempt_set_sources(context.result.seed_set_sources, context.rng)
    for source, (base, count) in zip(context.set_sources, ((0, 6), (6, 3)), strict=True):
        if source.is_vanilla:
            context.plans.append(None)       # a vanilla set keeps its quest's levels (SH-SRC-02)
            continue
        world = SetWorld(base_level=base, blob_count=count,
                         beside_second_quest=SetSource.SECOND_QUEST in context.set_sources)
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
    context.sets = build_sets(context.world, context.plans, context.set_sources)


def _blank_unowned_plans(worlds: list[SetWorld | None]) -> None:
    """SH-GRID-17: the shapes stage's own blank of every cell no level owns
    and no stair uses — walls on all four sides (monster/layout/item 0 and
    trigger $01 are written at serialization) — BEFORE the gate, so a tail
    write that lands there (A43) is the cell's last write."""
    for world in worlds:
        if world is None:
            continue
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
    context.room_lists = build_room_lists(context.plans, context.sets.levels, context.set_sources)
    context.shapes_snapshot = snapshot_shapes(context.sets.levels)
    context.monster_shuffle = MonsterShuffleResult(enemy_tiers=dict(VANILLA_ENEMY_TIER))


def item_shuffle_options(context: GenerationContext) -> ItemShuffleOptions:
    """The pool's options: only under full scope (C06 = 3) are the dungeon hearts pool items
    (PS-ITEM-02; not within each dungeon, PS-ITW-01, nor Item Only or None, PS-ITEM-09 and
    PS-ITEM-10), for the deal and for the ZORA extras that join the pool later; and the pins (C11,
    C12, C13, C26, C27; PS-ITEM-12), which act inside the deal (the first under PS-ITW). B47 leaves
    the Book in the pool (no PS-ITEM-13: docs/deviations.md). And the shop price classes the joins
    price their wares by (steps/shop_prices.py)."""
    alternatives = context.settings.alternatives
    return ItemShuffleOptions(dungeon_hearts=alternatives.item_deal is ItemShuffleScope.FULL,
                              set_sources=context.set_sources,
                              armos_item=alternatives.armos_pin, white_sword_item=alternatives.white_sword_pin,
                              coast_item=alternatives.coast_pin, level_9_items=alternatives.level_9_pins,
                              prices=context.settings.extras.price_rules)


def place_triforces_step(context: GenerationContext) -> None:
    """Allow Triforces in Stairways: each Triforce of levels 1-8 takes its spot before the item
    shuffle, which then runs over everything else (steps/place_triforces.py)."""
    place_triforces(context.sets.levels, context.item_shuffle_result, context.rng)


def shuffle_items_step(context: GenerationContext) -> None:
    """PS-ITEM: the big item shuffle by its scope (C06, resolved): full (fifteen fixed places +
    dungeon hearts), Item Only (the fifteen places, PS-ITEM-09), None (no deal, PS-ITEM-10, but
    as Item Only under Mixed Quest), or within each dungeon (PS-ITW's two deals)."""
    deal = context.settings.alternatives.item_deal
    levels, state, rng = context.sets.levels, context.item_shuffle_result, context.rng
    heart_places = heart_place_rooms(levels)
    if deal is ItemShuffleScope.WITHIN_EACH_DUNGEON:
        shuffle_items_within_levels(levels, state, rng, item_shuffle_options(context))
    elif deal is ItemShuffleScope.NONE:
        keep_items_in_place(levels, state, item_shuffle_options(context))
    elif deal is ItemShuffleScope.DUNGEON_ITEMS_ONLY:
        shuffle_items(levels, state, rng, item_shuffle_options(context))
    else:
        shuffle_items(levels, state, rng, item_shuffle_options(context))
    if context.settings.extras.gatekeeper_bosses:
        # Gatekeeper Bosses (owner decision 5): each gatekeeper takes what the shuffle left in its
        # level's heart-container room
        context.gatekeeper_plan = GatekeeperPlan(context.settings.extras.gatekeeper_bosses,
                                                 {level: room.item for level, room in heart_places.items()})


def shuffle_dungeon_drops_step(context: GenerationContext) -> None:
    """PS-DROP: the within-level drop shuffle."""
    assert context.shapes_snapshot is not None
    shuffle_dungeon_drops(context.sets.levels, context.shapes_snapshot, context.rng)


def shuffle_hungry_goriya_step(context: GenerationContext) -> None:
    """PS-GRUM: the hungry-goriya move."""
    shuffle_hungry_goriya(context.sets.levels, context.item_shuffle_result, context.rng)


def shuffle_bomb_upgraders_step(context: GenerationContext) -> None:
    """PS-BOMB: the bomb-upgrade person move."""
    shuffle_bomb_upgraders(context.sets.levels, context.item_shuffle_result, context.rng)


def _first_quest_block_levels(context: GenerationContext) -> list[Level]:
    """The levels the passes that scan the two first-quest blocks read (PS-MERCH-01, PS-HINT-01;
    PS-VAN-07): a second-quest set's are its first-quest block's, which no level points at (a
    copy of PRG0's, made once per attempt, so their writes never ship)."""
    if context.first_quest_block_levels is None:
        levels: list[Level] = []
        for set_index, source in enumerate(context.set_sources):
            if source is SetSource.SECOND_QUEST:
                levels += vanilla_set(context.world, set_index, SetSource.FIRST_QUEST)[1]
            else:
                levels += [level for level in context.sets.levels if level.level_num in SET_LEVELS[set_index]]
        context.first_quest_block_levels = levels
    return context.first_quest_block_levels


def add_money_or_life_rooms_step(context: GenerationContext) -> None:
    """PS-MERCH-01: adding life-or-money merchants."""
    add_money_or_life_rooms(_first_quest_block_levels(context), context.item_shuffle_result, context.rng)


def assign_hints_for_hint_type_step(context: GenerationContext) -> None:
    """post-shapes-b25.md (no draws), over the two first-quest blocks (PS-VAN-07). PS-HINT-02's
    record is the person-kind table as the bomb-upgrade move left it; with the move off (Dungeon
    Quest, SH-SRC-08) that is PRG0's, which marks levels 1, 2, 5 and 7."""
    recorded = (context.item_shuffle_result.bomb_levels if context.settings.steps.shuffle_bomb_upgraders
                else PRG0_RECORDED_LEVELS)
    context.hint_assignment = assign_hints_for_hint_type(_first_quest_block_levels(context), recorded)


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
    quests = None
    if any(source.is_vanilla for source in context.set_sources):
        # PS-VAN-01/04, PS-MONLV-05: each level's quest, its other quest's PRG0 list, the mixed groups
        second_quest_sets = {set_index for set_index, source in enumerate(context.set_sources)
                             if source is SetSource.SECOND_QUEST}
        quests = level_quests(context.sets.levels, second_quest_sets, context.world.levels,
                              context.world.levels_2q, context.world.enemies.mixed_groups)
    second_quest_lists = (second_quest_list_values(context.world.levels_2q)
                          if context.settings.shape_options.second_quest_monsters else None)
    shuffle_monsters_between_levels(context.sets.blocks, context.sets.levels, context.room_lists,
                                    context.monster_shuffle, context.rng, quests,
                                    level_9_included=context.settings.alternatives.shuffle_level_9_monsters,
                                    second_quest_lists=second_quest_lists)


def swap_start_rooms_step(context: GenerationContext) -> None:
    """PS-START (B26): each level's start room moves to an edge of the level, after the monster
    moves between levels and before the per-level re-deal, which reads the room lists the swap
    exchanges."""
    assert context.room_lists is not None
    swap_start_rooms(context.sets.blocks, context.sets.levels, context.room_lists, context.rng)


def shuffle_dungeon_monsters_step(context: GenerationContext) -> None:
    """PS-MONRD: the per-level monster re-deal, which writes the lists into the rooms (with
    B32, B33 and B18 off: PS-MONRD-06, PS-MONRD-04, PS-MONRD-05)."""
    assert context.room_lists is not None and context.monster_shuffle is not None
    alternatives = context.settings.alternatives
    shuffle_dungeon_monsters(context.sets.blocks, context.sets.levels, context.room_lists,
                             context.monster_shuffle, context.rng,
                             RedealOptions(shuffle=alternatives.shuffle_dungeon_monsters,
                                           ganon_and_zelda=alternatives.shuffle_ganon_and_zelda,
                                           force_ganon_fight=alternatives.force_ganon_fight))


# ---------------------------------------------------------------------------
# B8 (post-shapes-b8.md), B4 (post-shapes-b4.md) and B3 (post-shapes-b3.md)
# ---------------------------------------------------------------------------

def stage_overworld(context: GenerationContext) -> None:
    """The staged copy of the overworld that the later passes share, and the
    staged hit points and group results, from the base's (no draws)."""
    context.overworld = copy.deepcopy(context.world.overworld)
    if context.settings.alternatives.second_quest_overworld:
        # OW-QST-04 step 3: before the overworld monster pass, which then leaves screen 11
        prepare_second_quest_screen_11(context.overworld)
    context.hit_points = EnemyHpResult.unchanged(context.world.enemies)
    context.groups = GroupShuffleResult()


def expanded_dungeon_locations_step(context: GenerationContext) -> None:
    """Expanded Dungeon Locations (ZORA's own; expanded_dungeon_locations.py): the deal from its own
    stream, on the staged overworld before the overworld monster pass. The start rooms are final
    here, as at the cave pass (OW-CAVE-03)."""
    assert context.overworld is not None
    second_quest = context.settings.alternatives.second_quest_overworld
    deal = deal_expanded_dungeon_locations(context.settings.extras.expanded_dungeon_locations_seed,
                                           _start_rooms(context.plans, context.sets.levels),
                                           SECOND_QUEST if second_quest else FIRST_QUEST)
    if second_quest:
        # The second quest's codes and looks first (enroll_caves then only lists them), so the deal
        # is made over the 2nd Quest overworld
        show_second_quest_overworld(context.overworld)
    apply_deal(context.overworld, deal, context.world.overworld)
    context.expanded_deal = deal


def change_sword_caves_step(context: GenerationContext) -> None:
    """FP-WOOD-01 to FP-WOOD-03: the sword caves' wares, on the staged overworld (no draw)."""
    assert context.overworld is not None
    change_sword_caves(context.overworld, context.settings.alternatives.wooden_sword_state)


def shuffle_overworld_monsters_step(context: GenerationContext) -> None:
    """PS-OWM: the overworld monsters, on the staged overworld."""
    assert context.overworld is not None
    shuffle_overworld_monsters(context.world, context.overworld, context.rng)


def change_most_enemy_hp_step(context: GenerationContext) -> None:
    """PS-HP-01 and PS-HP-04."""
    assert context.hit_points is not None
    change_most_enemy_hp(context.hit_points, context.settings.alternatives.enemy_hit_points, context.rng)


def change_boss_hp_step(context: GenerationContext) -> None:
    """PS-HP-02 and PS-HP-05."""
    assert context.hit_points is not None
    change_boss_hp(context.hit_points, context.settings.alternatives.boss_hit_points, context.rng)


def zero_ganon_hp_step(context: GenerationContext) -> None:
    """PS-HP-06."""
    assert context.hit_points is not None
    zero_ganon_hp(context.hit_points)


def maximum_enemy_hp_step(context: GenerationContext) -> None:
    """PS-HP-08, and under Swordless the wooden-sword cave's red candle."""
    assert context.hit_points is not None and context.overworld is not None
    maximum_enemy_hp(context.hit_points)
    if context.settings.alternatives.wooden_sword_state is WoodenSwordState.SWORDLESS:
        red_candle_for_maximum_boss_health(context.overworld)


def maximum_boss_hp_step(context: GenerationContext) -> None:
    """PS-HP-07, and under Swordless the wooden-sword cave's red candle."""
    assert context.hit_points is not None and context.overworld is not None
    maximum_boss_hp(context.hit_points)
    if context.settings.alternatives.wooden_sword_state is WoodenSwordState.SWORDLESS:
        red_candle_for_maximum_boss_health(context.overworld)


def shuffle_enemy_groups_step(context: GenerationContext) -> None:
    """PS-EGRP, with B5's sprite repack."""
    groups, monster_shuffle = context.groups, context.monster_shuffle
    assert groups is not None and monster_shuffle is not None
    assert context.overworld is not None and context.hit_points is not None
    groups.enemy_deal, groups.goriya_tile, groups.rooms_redrawn = shuffle_enemy_groups(
        context.sets.blocks, context.world,
        monster_shuffle.enemy_tiers[context.item_shuffle_result.goriya_level], context.rng,
        context.overworld, context.hit_points.hp[Enemy.ZOL], groups.staged,
        overworld_group=context.settings.alternatives.shuffle_overworld_group,
        wizzrobes_in_level_9_group=not context.settings.alternatives.shuffle_level_9_monsters,
    )


def randomize_boss_groups_step(context: GenerationContext) -> None:
    """PS-BGRP."""
    groups = context.groups
    assert groups is not None
    groups.boss_deal, groups.bosses_redrawn = randomize_boss_groups(context.sets.blocks, context.world,
                                                                    context.rng, groups.staged)


def exchange_rooms_step(context: GenerationContext) -> None:
    """PS-XCHG: the exchange between dungeons, only with the full room shuffle (C14 = 2)."""
    context.result.room_shuffle = exchange_rooms(context.sets.levels, context.rng,
                                                 context.settings.alternatives.shuffle_ganon_and_zelda)


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
    """OW-CAVE-02 step 1 (no draws); the armos screen is PRG0's unless Shuffle Armos moves it.
    A mixed overworld quest (C01 = 2) deals the first-quest secret caves first (OW-MIX-02 to
    OW-MIX-04, eleven draws), and the list is the dealt one; Mixed Quest - 2nd (C01 = 3) deals the
    eighteen second-quest codes (OW-QST-01, OW-QST-02); 2nd Quest (C01 = 1) takes the second
    quest's list (OW-QST-03, OW-QST-04; no draws). With Shuffle Wood Sword Cave off (B02) the list
    keeps PRG0's order (OW-CAVE-12)."""
    assert context.overworld is not None
    alternatives = context.settings.alternatives
    if alternatives.mix_overworld_quest:
        context.cave_entries = mix_overworld_quest(context.overworld, context.rng)
    elif alternatives.mix_overworld_quest_second_variant:
        context.cave_entries = mix_overworld_quest(context.overworld, context.rng, SECOND_QUEST_DEALT_POSITIONS)
    elif alternatives.second_quest_overworld and context.expanded_deal is not None:
        # Expanded Dungeon Locations wrote the second quest's codes and looks before its deal
        context.cave_entries = staged_second_quest_entries(context.overworld)
    elif alternatives.second_quest_overworld:
        context.cave_entries = second_quest_overworld(context.overworld)
    else:
        context.cave_entries = enrolled_entries(context.overworld)
    if not context.settings.steps.move_wood_sword_cave:
        context.cave_entries = leave_wood_sword_cave_in_place(context.cave_entries)
    if context.expanded_deal is not None:
        context.cave_entries = deal_entries(context.overworld, context.cave_entries)
    context.armos_screen = prg0_armos_screen(context.overworld)


def shuffle_armos_step(context: GenerationContext) -> None:
    """OW-CAVE-05: the formation tables, screen 36 and the re-pointed entry. With Expanded Dungeon
    Locations, 2Q2's screen is never the Armos item's while it holds a dungeon."""
    assert context.overworld is not None
    deal = context.expanded_deal
    kept_off = frozenset({ARMOS_SPOT_SCREEN}) if deal is not None and ARMOS_SPOT_SCREEN in deal.door_screens.values() \
        else frozenset()
    context.armos_screen = shuffle_armos(context.overworld, context.rng, context.cave_entries, kept_off)


def shuffle_caves_step(context: GenerationContext) -> None:
    """OW-CAVE-02 step 3 and OW-CAVE-04's write-back; with Allow OW Blocks of Wood Sword (B03) the
    wooden-sword cave's partner set widens by the item gates the free item opens (OW-CAVE-07). Cave
    Shuffle (C05) and the overworld quest choose the walk's parts (OW-CAVE-09). Expanded Dungeon
    Locations dealt the dungeons already (shuffle_caves' dungeons_dealt): Dungeons Only then walks
    nothing ("Expanded Brackets"), All Caves only the other caves ("Expanded + shuffle everything
    else")."""
    assert context.overworld is not None and context.armos_screen is not None
    alternatives = context.settings.alternatives
    parts = cave_walk_parts(alternatives.cave_shuffle, alternatives.mix_overworld_quest
                            or alternatives.mix_overworld_quest_second_variant)
    extra = frozenset[int]()
    if context.settings.alternatives.wood_sword_cave_behind_blocks:
        caves = context.item_shuffle_result.caves
        # OW-CAVE-07 reads the starting inventory (FP-START-04)
        extra = wood_sword_extra_screens(context.overworld, caves["armos"], caves["coast"],
                                         frozenset(context.settings.alternatives.start_items))
    context.caves = shuffle_caves(context.overworld, context.cave_entries, context.armos_screen,
                                  _start_rooms(context.plans, context.sets.levels), context.rng,
                                  context.settings.steps.shuffle_take_any_road_caves,
                                  context.settings.extras.gates,
                                  context.settings.alternatives.second_quest_secrets, extra,
                                  context.settings.steps.move_wood_sword_cave, parts,
                                  dungeons_dealt=context.expanded_deal is not None)


def _start_rooms(worlds: list[SetWorld | None], levels: list[Level]) -> dict[int, int]:
    """Each dungeon's start room (LevelInfo_StartRoomId) as it stands when the cave pass runs
    (OW-CAVE-03: "already final"): its entrance cell, or a vanilla level's own start room
    (SH-SRC-03), or where the start-room swap moved it (B26, PS-START)."""
    start_rooms = {level.level_num: level.entrance_room for level in levels}
    start_rooms.update({level: room_number for world in worlds if world is not None
                        for level, room_number in world.entrance.items()})
    start_rooms.update({level.level_num: level.entrance_room for level in levels if level.arrival_code is not None})
    return start_rooms


def force_overworld_block_step(context: GenerationContext) -> None:
    """Force Overworld Block (B81; OW-CAVE-08): at the end of the cave pass, a result without a
    dungeon door or the white-sword cave behind an item gate restarts the whole seed."""
    assert context.overworld is not None and context.caves is not None
    failure = force_overworld_block(context.overworld, context.caves)
    if failure is not None:
        raise GenerationFailure(failure)


def recorder_to_new_dungeons_step(context: GenerationContext) -> None:
    """OW-WARP-01."""
    assert context.overworld is not None and context.caves is not None
    recorder_to_new_dungeons(context.overworld, context.caves)


def shuffle_shop_items_step(context: GenerationContext) -> None:
    """OW-SHOP-02 to OW-SHOP-04."""
    assert context.overworld is not None
    shuffle_shop_items(context.overworld, context.rng)


def unsegmented_levels(context: GenerationContext) -> frozenset[int]:
    """Do Not Segment Dungeons: the shapes sets' level numbers, which the late gate walks without
    transport staircases (vanilla sets keep their stairway-linked areas)."""
    if not context.settings.shape_options.do_not_segment_dungeons:
        return frozenset()
    return frozenset(level for source, levels in zip(context.set_sources, SET_LEVELS, strict=True)
                     if not source.is_vanilla for level in levels)


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
    of the budget.

    VA-REJ-02 (beta 8 export): under C14 = 0 with every level set from a vanilla source neither the
    remap nor the gate runs, and the levels keep their source rooms."""
    if not context.settings.steps.remap_rooms and all(source.is_vanilla for source in context.set_sources):
        place_gatekeepers_without_gate(context)
        return
    result = context.result
    context.l1_gate_entry = _l1_census(context.sets.levels)
    stats = GateStats()
    try:
        late_gate(context.sets.levels, context.rng, stats, context.settings.alternatives.force_ganon_fight,
                  unsegmented_levels(context), context.gatekeeper_plan)
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


def place_gatekeepers_without_gate(context: GenerationContext) -> None:
    """Gatekeeper Bosses when the late gate does not run (VA-REJ-02): each level 1-8 as it stands
    builds its gatekeeper, with TRIES_WITHOUT_GATE tries, or the generation restarts."""
    plan = context.gatekeeper_plan
    if plan is None:
        return
    for level in context.sets.levels:
        if level.level_num in GATEKEEPER_LEVELS and not place_gatekeeper(level, context.rng, plan,
                                                                          tries=TRIES_WITHOUT_GATE):
            raise GenerationFailure(f"level {level.level_num}: no gatekeeper")


def _l1_census(levels: list[Level]) -> tuple[int, int]:
    """Level 1 at gate entry: person rooms, and rooms whose in-room move
    table restricts the walk (walk.py's table)."""
    from .late_gate.walk import _FREE_MOVES, _moves
    rooms = levels[0].rooms
    persons = sum(room.is_person for room in rooms)
    restrict = sum(_moves(room, None) is not _FREE_MOVES for room in rooms)
    return persons, restrict


def remove_most_open_stairs_step(context: GenerationContext) -> None:
    """PS-OSTAIR (B30): right after the late gate (VA-REJ-01 to VA-REJ-05), before the passes
    after it and the acceptance check, which judges the new layouts and triggers (VA-REJ-17)."""
    remove_most_open_stairs(context.sets.blocks, context.rng)


def level9_records_step(context: GenerationContext) -> None:
    """PS-L9REC-01: level 9's records, after the gate (no draws)."""
    level9 = context.sets.levels[LEVEL_9 - 1]
    level9_records(level9, level9.block)


def shuffle_start_screen_step(context: GenerationContext) -> None:
    """OW-START-01: after the gate and level 9's record step, before map
    relocation; the exchange itself is written when the attempt ships. Full Start Shuffle
    (C04 = 2) draws over OW-START-02's 90 screens; Wood Sword Screen (C04 = 3) starts on the
    wooden-sword cave's screen (OW-START-03). Either draw leaves out the screens the ZORA block
    flags wall in and the screens past each randomized maze (OverworldGates.start_barred; of
    OW-START-01's 51, only Randomize Dead Woods' $70-$72); the wooden-sword cave never moves
    onto a gated screen (wood_sword_barred)."""
    alternatives = context.settings.alternatives
    barred = context.settings.extras.gates.start_barred()
    if alternatives.start_on_wood_sword_screen:
        assert context.overworld is not None
        context.start = start_on_wood_sword_screen(context.overworld, context.rng)
    elif alternatives.full_start_shuffle:
        context.start = shuffle_start_screen(context.rng, FULL_START_SCREENS - barred)
    else:
        context.start = shuffle_start_screen(context.rng, START_SCREENS - barred)


def move_last_boss_room_items_step(context: GenerationContext) -> None:
    """VA-REJ-20: after the start-screen pass, before the map move; no receiving room
    restarts the pass."""
    move_last_boss_room_items(context.sets.levels[LEVEL_9 - 1], context.rng)


def move_map_near_entrance_step(context: GenerationContext) -> None:
    """SH-MAP-03..07, after the gate: map relocation (best-effort; never rejects). It runs when
    at least one set is shapes, then over all nine levels (SH-SRC-06 item 2, PS-VAN-05)."""
    if all(source.is_vanilla for source in context.set_sources):
        return
    for level in context.sets.generation_order:
        move_map_near_entrance(level, context.rng)


def change_money_or_life_toll_step(context: GenerationContext) -> None:
    """PS-MERCH-02 pricing (late)."""
    change_money_or_life_toll(context.item_shuffle_result, context.rng)


def oops_all_step(context: GenerationContext) -> None:
    """Oops All Enemies and Oops All Bosses (docs/design/oops-all.md): after every monster pass
    and the late gate, before the first walk that reads monsters (2.6), on their own stream (2.8)."""
    groups, overworld, monster_shuffle = context.groups, context.overworld, context.monster_shuffle
    assert groups is not None and overworld is not None and monster_shuffle is not None
    extras, rng = context.settings.extras, Rng(context.settings.extras.oops_all_seed)
    if extras.oops_all_enemies:
        oops_all_enemies(context.world, context.sets.levels, overworld, groups.enemy_deal, extras.oops_all_enemies,
                         rng, groups.staged)
    if extras.oops_all_bosses:
        boss_sets = {level.level_num: BOSS_BANKS[monster_shuffle.boss_tiers[level.level_num]]
                     if level.level_num in monster_shuffle.boss_tiers else level.boss_sprite_set
                     for level in context.sets.levels}
        oops_all_bosses(context.world, context.sets.levels, boss_sets, groups.boss_deal, rng, groups.staged)


# The ZORA extras join the pool after every pass that reads $03 as "no item"
# (docs/zora-extras.md section 3); neither is a tracked item.

def level_9_gate_step(context: GenerationContext) -> None:
    """Level 9 Entry (C08; FP-TRIF-02 to FP-TRIF-06): what this attempt's entrance asks for, before
    the joins and checks that judge by it; C08 = 9, 10 and 11 draw it anew in every attempt."""
    context.level_9_gate = draw_level_9_gate(context.settings.alternatives.level_9_entry, context.rng)


def randomize_magical_sword_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    randomize_magical_sword(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                            context.overworld, context.rng, item_shuffle_options(context),
                            tracked=context.settings.extras.level_9_entrance_sword)


def randomize_letter_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    randomize_letter(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                     context.overworld, context.rng, item_shuffle_options(context))


def shuffle_wood_sword_step(context: GenerationContext) -> None:
    """Shuffle Wood Sword (docs/zora-extras.md section 13): the last of the joins (after Add L4
    Sword = Level 2's, whose cellar sword has the wood sword's item code), so no later join moves
    the weapon it puts in an open cave."""
    assert context.overworld is not None and context.caves is not None
    shuffle_wood_sword(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                       context.overworld, context.caves, context.logic_rules, context.rng,
                       item_shuffle_options(context))


def shop_items_in_pool_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    shop_items_in_pool(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                       context.overworld, context.rng, item_shuffle_options(context))
    # the baits join after the other three, before the blue potion's join (docs/zora-extras.md 10)
    bait_in_pool(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                 context.overworld, context.rng, item_shuffle_options(context))


def shuffle_blue_potion_step(context: GenerationContext) -> None:
    assert context.overworld is not None
    shuffle_blue_potion(context.sets.levels, context.item_shuffle_result, context.extra_pool_items,
                        context.overworld, context.rng, item_shuffle_options(context))


def join_level_2_sword_step(context: GenerationContext) -> None:
    """Add L4 Sword = Level 2 (docs/design/asnb.md section 4): level 2's cellar sword joins the
    pool, after the other joins; tracked with Level 9 Entrance = Level 4 sword."""
    join_level_2_sword(context.sets.levels, context.item_shuffle_result, context.extra_pool_items, context.rng,
                       tracked=context.settings.extras.level_9_entrance_sword, opts=item_shuffle_options(context))


def add_l4_sword_step(context: GenerationContext) -> None:
    """Add L4 Sword (docs/design/l4-sword.md): the progressive sword in a level-9 room, after every
    step that changes level 9's rooms."""
    add_l4_sword(context.sets.levels, context.rng)


def check_item_spots_step(context: GenerationContext) -> None:
    """ZORA's item-spot check (zora/generate/item_spots.py): after every step that puts an item in a
    room, an attempt with any room's item on a block, statue or staircase restarts."""
    check_item_spots(context.sets.levels)


def change_sword_hearts_before_check(context: GenerationContext) -> None:
    """With Randomize Magical Sword on, the sword caves' requirements are drawn
    here, before the checks, so the heart check judges the exact N (owner
    requirement); otherwise after the attempt ships (change_sword_hearts_after_ship)."""
    assert context.overworld is not None
    _change_sword_hearts(context, context.overworld)


def check_gatekeepers_step(context: GenerationContext) -> None:
    """Gatekeeper Bosses' final check (docs/zora-extras.md section 19): after every step that moves a
    room's monsters, items or doors, each gatekeeper still holds: its boss, its trigger-7 item, its
    shutters, and a cut no staircase, door repair, bombable or walk-through wall gets around, with the
    compass in front. The steps keep it so; a failure restarts the attempt and is a bug to trace."""
    problems = [problem for level in context.sets.levels for problem in gatekeeper_problems(level)]
    if problems:
        raise GenerationFailure("; ".join(problems))


def acceptance_check_step(context: GenerationContext) -> None:
    """acceptance.md: the finished attempt is judged; any failure restarts the
    whole seed (VA-REJ-06)."""
    assert context.overworld is not None and context.caves is not None
    _reject_unless_accepted(context, acceptance_check(context.sets.levels, context.item_shuffle_result,
                                                      context.overworld, context.caves,
                                                      context.logic_rules))


def check_white_sword_hearts_step(context: GenerationContext) -> None:
    """ZORA's E11: the white-sword cave's tracked item is taken only with the cave's hearts
    (white_sword_cave_hearts_met). With B10's heart counts drawn after the attempt ships
    (change_sword_hearts_after_ship), the highest count the draw can give is judged."""
    assert context.overworld is not None and context.caves is not None
    cave = context.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert cave is not None
    drawn_after_ship = draws_sword_hearts_after_ship(context.settings)
    hearts = max(context.settings.alternatives.white_sword_hearts) if drawn_after_ship else cave.heart_requirement
    accepted = white_sword_cave_hearts_met(context.sets.levels, context.item_shuffle_result,
                                           context.extra_pool_items, context.overworld, context.caves,
                                           hearts_required=hearts,
                                           starting_hearts=context.settings.extras.starting_heart_containers,
                                           rules=context.logic_rules)
    _reject_unless_accepted(context, None if accepted else "E11")


def check_magical_sword_hearts_step(context: GenerationContext) -> None:
    """Randomize Magical Sword's heart check (owner requirement), judged as an acceptance check."""
    assert context.overworld is not None and context.caves is not None
    accepted = has_magical_sword_hearts(context.sets.levels, context.item_shuffle_result,
                                        context.extra_pool_items,
                                        OverworldResult(context.overworld, context.caves),
                                        context.settings.extras, context.logic_rules)
    _reject_unless_accepted(context, None if accepted else "hearts")


def _reject_unless_accepted(context: GenerationContext, failure: str | None) -> None:
    if failure is not None:
        context.result.acceptance_rejections[failure] += 1
        raise GenerationFailure(failure)


def has_magical_sword_hearts(levels: list[Level], item_shuffle_result: ItemShuffleResult,
                             extra_pool_items: ExtraPoolItems, overworld_state: OverworldResult,
                             extras: ExtraOptions, rules: LogicRules | None = None) -> bool:
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
                                      rules=extras.logic_rules if rules is None else rules)


def ship_step(context: GenerationContext) -> None:
    """The accepted attempt: its figures into the result, and its staged
    results into the GameWorld (ship.SHIP_STEPS)."""
    result = context.result
    result.item_shuffle_result = context.item_shuffle_result
    result.monster_shuffle = context.monster_shuffle
    result.groups = context.groups
    result.extra_pool_items = context.extra_pool_items
    result.l1_gate_entry = context.l1_gate_entry
    result.set_plans = context.plans
    levels_7_to_9 = context.plans[1]
    result.hint_level9_left_column = level9_left_edge(levels_7_to_9) if levels_7_to_9 is not None else None
    overworld_state = None
    if context.overworld is not None and context.caves is not None:
        overworld_state = OverworldResult(context.overworld, context.caves)
        result.overworld = context.caves
    result.expanded_deal = context.expanded_deal
    ship(context.world, Staged(context.sets, context.item_shuffle_result, overworld_state,
                               context.hint_assignment, context.monster_shuffle, context.hit_points,
                               context.groups, context.palettes, context.start, context.extra_pool_items,
                               monsters_take_second_quest_path(context.settings.alternatives.dungeon_quest,
                                                               context.set_sources)
                               or second_quest_monster_branches(context)))


def second_quest_monster_branches(context: GenerationContext) -> bool:
    """SH-ENEMY-05: Add 2nd Quest Monsters (B37) sends every rope and Stalfos down the second-quest
    path whenever the shape stage placed enemies (a set from it) or the monsters-between-levels pass
    (B36) ran, whatever C02 is."""
    settings = context.settings
    return settings.shape_options.second_quest_monsters and settings.post_shapes and (
        not all(source.is_vanilla for source in context.set_sources) or settings.steps.shuffle_monsters_between_levels)


# ---------------------------------------------------------------------------
# After ship, on the shipped world: the hint text runs after the item and map
# passes (HT-TEXT-04) and reads what they wrote: the shipped level 9 (trio
# rooms and quadrants), the cave items B1 placed (white-sword and coast
# items), the group passes' mixed lists (the compass family). B10's DATA
# items follow it, so the level-9 refusal text can be overwritten in place.
# ---------------------------------------------------------------------------

def cap_level_9_vire_hp_step(context: GenerationContext) -> None:
    """The owner's level-9 Vire cap (tetraly/zora#14): on the shipped world, whose monsters and hit
    points are final."""
    cap_level_9_vire_hp(context.world)


def highlight_no_drop_rooms_step(context: GenerationContext) -> None:
    """Highlight No-Drop Rooms (ZORA flag): the shipped rooms' inner palette selectors, after
    every pass that moves rooms, items, layouts or palettes, before the level encoding."""
    highlight_no_drop_rooms(context.world.levels, context.settings.alternatives.remove_most_open_stairs)


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
    """FP-SWORD-01 with FL-ALT-05's white-sword range (C20, C21); the magical sword's range is
    the ZORA cap's (zora_flags.magical_sword_heart_range, from C22 and C23)."""
    change_sword_hearts(overworld, context.rng, context.settings.extras.magical_sword_hearts,
                        context.settings.alternatives.white_sword_hearts)


def randomize_mazes_step(context: GenerationContext) -> None:
    """Randomize Lost Hills / Dead Woods (owner's 2.0 flags): the sequences, before the hint text,
    which sells each in its hint shop."""
    gates = context.settings.extras.gates
    context.maze_offers = randomize_mazes(context.world.overworld, context.rng, gates.lost_hills, gates.dead_woods)


def generate_hint_text_step(context: GenerationContext) -> None:
    """HT-TEXT (HT-HINT-04's helpful hints with C03 at 1), or FL-ALT-04's community hints with
    C03 at 2; with Randomize Magical Sword on, the cave's own text names the item it offers. What it
    reads besides the world is kept in the result, for FINISH (no draws)."""
    assert context.hint_assignment is not None
    context.result.hint_assignment = context.hint_assignment
    context.result.maze_offers = context.maze_offers
    context.hint_text = compose_hint_text(context.world, context.item_shuffle_result, context.hint_assignment,
                                          context.rng, context.settings.extras, context.settings.alternatives,
                                          context.maze_offers)


def compose_hint_text(gw: GameWorld, item_shuffle_result: ItemShuffleResult, hint_assignment: HintAssignmentResult,
                      rng: Rng, extras: ExtraOptions, alternatives: AlternativeValues,
                      maze_offers: dict[int, list[str]], foreign_code: int | None = None) -> HintTextResult:
    """The hint text step's work on a shipped world: also FINISH's, on an assigned world
    (Archipelago Phase 2), which passes foreign_code, the code another player's item is written
    as, so that a hint naming such a place says so (ItemNames.foreign_code)."""
    # PI-TEXT-01: with Progressive Items on, the texts name upgrade-line items by their line
    names = PROGRESSIVE_NAMES if extras.progressive_items else VANILLA_NAMES
    if alternatives.wooden_sword_state in BOMB_UPGRADE_STATES:
        names = replace(names, bomb_upgrade=True)       # FP-WOOD-02: item $02 is a bomb upgrade
    if foreign_code is not None:
        names = replace(names, foreign_code=foreign_code)
    if extras.pegasus_boots:
        names = replace(names, pegasus_boots=True)      # the boomerangs' items are the boots
    if alternatives.normal_hints:
        return generate_normal_hint_text(gw, item_shuffle_result, hint_assignment, maze_offers)
    if alternatives.blank_hints:
        return generate_blank_hint_text(gw, item_shuffle_result, hint_assignment, maze_offers)
    if alternatives.generate_community_hint_text:
        return generate_community_hint_text(gw, item_shuffle_result, hint_assignment, rng, names,
                                            maze_offers, book_needed=alternatives.book_to_understand_npcs)
    return generate_hint_text(gw, item_shuffle_result, hint_assignment, rng, names, maze_offers,
                              extras.gates, every_helpful_hint=alternatives.show_every_helpful_hint,
                              book_needed=alternatives.book_to_understand_npcs,
                              deceive=alternatives.deception_hints)


def shuffle_dungeon_text_step(context: GenerationContext) -> None:
    """HT-TEXT-04."""
    assert context.hint_text is not None
    context.hint_text = shuffle_dungeon_text(context.hint_text, context.rng)


def ship_hint_text_step(context: GenerationContext) -> None:
    assert context.hint_text is not None
    ship_hint_text(context.world, context.hint_text)


def boss_sound_end_pass_step(context: GenerationContext) -> None:
    """PS-MONRD-07, once per seed after the accepted pass: every boss sound reset, only Ganon's
    level-9 neighbours keep one. After the hint text, which reads the sounds before it (PS-MONRD-03)."""
    boss_sound_end_pass(context.world)


def check_boss_sounds_step(context: GenerationContext) -> None:
    """The finished world's boss sounds are exactly PS-MONRD-07's (zora/generate/boss_sounds.py)."""
    check_boss_sounds(context.world)


# B10's DATA items (features-behavior.md). Bomb/mmg values are drawn here
# rather than earlier in the stream; the spec only constrains their marginal
# distributions, so stream position does not matter. Book is an Atlas
# (FP-BOOK-01) is a code patch only (zora/rom/code_patches.py).

def change_bomb_upgrades_step(context: GenerationContext) -> None:
    """FP-BOMB-01: the price and capacity drawn under B12, and 2 more capacity under B90 (with B12
    off the pass draws nothing and gives PRG0's 4 plus 2)."""
    change_bomb_upgrades(context.world, context.rng if context.settings.steps.change_bomb_upgrades else None,
                         larger_capacity=context.settings.steps.increase_bomb_capacity)


def change_money_making_game_step(context: GenerationContext) -> None:
    change_money_making_game(context.world, context.rng)


def speed_up_text_step(context: GenerationContext) -> None:
    speed_up_text(context.world)


def write_fixed_feature_data_step(context: GenerationContext) -> None:
    write_fixed_feature_data(context.world, context.settings.seed)


def level_9_entrance_text_step(context: GenerationContext) -> None:
    """ASNB 3c: the level-9 refusal text (person text 34) asks for four sword upgrades."""
    context.world.level9_refusal_text = LEVEL_9_SWORD_REFUSAL_TEXT


def level_9_gate_text_step(context: GenerationContext) -> None:
    """FP-TRIF-01 to FP-TRIF-06: the shipped attempt's gate, and the entrance person's text naming
    its count, levels or item (after write_fixed_feature_data's text for eight)."""
    context.world.level_9_gate = context.level_9_gate
    context.world.level9_refusal_text = refusal_text(context.level_9_gate)


def set_starting_hearts_step(context: GenerationContext) -> None:
    set_starting_hearts(context.world, context.settings.alternatives.starting_hearts)


def start_items_step(context: GenerationContext) -> None:
    """FP-START-02 and FP-START-03: the kept start items (drawn with the plan, apart from the
    generation's stream) go into the starting table; nothing else in generation reads them but
    the wooden-sword cave pass (FP-START-04)."""
    context.world.start_items = context.settings.alternatives.start_items


def start_triforce_pieces_step(context: GenerationContext) -> None:
    """FL-ALT-06: the start pieces (drawn with the plan) go into the starting table; no generation
    pass and no acceptance rule reads them (level 9 still needs eight completions)."""
    context.world.start_triforce_pieces = context.settings.alternatives.start_triforce_pieces


# ---------------------------------------------------------------------------
# The step list
# ---------------------------------------------------------------------------

def post_shapes(settings: GenerationSettings) -> bool:
    return settings.post_shapes


def feature_data(settings: GenerationSettings) -> bool:
    return settings.post_shapes and settings.feature_data


def has_level_9_gate(settings: GenerationSettings) -> bool:
    """Level 9 Entry (C08) asks for anything but PRG0's eight pieces (FP-TRIF-02 to FP-TRIF-06)."""
    return settings.alternatives.level_9_entry.requirement != Level9Requirement.EIGHT_PIECES


def draws_sword_hearts_after_ship(settings: GenerationSettings) -> bool:
    """B10's heart counts drawn after the attempt ships (change_sword_hearts_after_ship): with
    Randomize Magical Sword or Level 9 Entrance off they are not known to the checks."""
    return (settings.post_shapes and settings.feature_data and settings.steps.change_sword_hearts
            and not settings.extras.checks_magical_sword_hearts)


STEPS: tuple[Step, ...] = (
    # The shape stage: one step for now (it still works on CellPlan)
    Step("shape_stage", "", shape_stage, restart_label=""),
    Step("build_levels", "", build_levels),
    # B1
    Step("start_post_shapes", "", start_post_shapes, post_shapes),
    Step("place_triforces", "ZORA allow_triforces_in_stairways", place_triforces_step,
         lambda s: s.post_shapes and s.extras.allow_triforces_in_stairways),
    Step("shuffle_items", "C06", shuffle_items_step, post_shapes),
    Step("shuffle_dungeon_drops", "B15", shuffle_dungeon_drops_step,
         lambda s: s.post_shapes and s.steps.shuffle_dungeon_drops),
    Step("shuffle_hungry_goriya", "B28", shuffle_hungry_goriya_step,
         lambda s: s.post_shapes and s.steps.shuffle_hungry_goriya),
    Step("shuffle_bomb_upgraders", "B29", shuffle_bomb_upgraders_step,
         lambda s: s.post_shapes and s.steps.shuffle_bomb_upgraders),
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
    Step("swap_start_rooms", "B26", swap_start_rooms_step,
         lambda s: s.post_shapes and s.shape_options.start_room_swap),
    Step("shuffle_dungeon_monsters", "B32", shuffle_dungeon_monsters_step, post_shapes, restart_label="B2: "),
    # B8
    Step("stage_overworld", "", stage_overworld, post_shapes),
    Step("expanded_dungeon_locations", "ZORA expanded_dungeon_locations", expanded_dungeon_locations_step,
         lambda s: s.post_shapes and s.extras.expanded_dungeon_locations),
    Step("change_sword_caves", "C07", change_sword_caves_step,
         lambda s: s.post_shapes and s.alternatives.wooden_sword_state is not WoodenSwordState.NORMAL),
    Step("shuffle_overworld_monsters", "B31", shuffle_overworld_monsters_step,
         lambda s: s.post_shapes and s.steps.shuffle_overworld_monsters),
    Step("change_most_enemy_hp", "C09", change_most_enemy_hp_step,
         lambda s: s.post_shapes and s.steps.change_most_enemy_hp),
    Step("change_boss_hp", "C10", change_boss_hp_step, lambda s: s.post_shapes and s.steps.change_boss_hp),
    Step("zero_ganon_hp", "B41", zero_ganon_hp_step,
         lambda s: s.post_shapes and s.alternatives.ganon_hit_points_zero),
    Step("maximum_enemy_hp", "B45", maximum_enemy_hp_step,
         lambda s: s.post_shapes and s.alternatives.maximum_enemy_health),
    Step("maximum_boss_hp", "B46", maximum_boss_hp_step,
         lambda s: s.post_shapes and s.alternatives.maximum_boss_health),
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
    Step("force_overworld_block", "B81", force_overworld_block_step,
         lambda s: s.post_shapes and s.alternatives.force_overworld_block, restart_label="B81: "),
    Step("recorder_to_new_dungeons", "B01", recorder_to_new_dungeons_step,
         lambda s: s.post_shapes and s.steps.recorder_to_new_dungeons),
    Step("shuffle_shop_items", "B08", shuffle_shop_items_step,
         lambda s: s.post_shapes and s.steps.shuffle_shop_items),
    Step("extra_candles", "B09", extra_candles_step, lambda s: s.post_shapes and s.steps.extra_candles),
    # The late gate and after
    Step("late_gate", "", late_gate_step, restart_label="late gate: "),
    Step("remove_most_open_stairs", "B30", remove_most_open_stairs_step,
         lambda s: s.post_shapes and s.alternatives.remove_most_open_stairs),
    Step("level9_records", "", level9_records_step),
    Step("shuffle_start_screen", "C04", shuffle_start_screen_step,
         lambda s: s.post_shapes and s.steps.shuffle_start_screen),
    Step("move_last_boss_room_items", "", move_last_boss_room_items_step, restart_label="last-boss rooms: "),
    Step("move_map_near_entrance", "", move_map_near_entrance_step),
    Step("change_money_or_life_toll", "B23", change_money_or_life_toll_step,
         lambda s: s.post_shapes and s.steps.change_money_or_life_toll),
    # The ZORA extras and the acceptance check
    Step("level_9_gate", "C08", level_9_gate_step, lambda s: s.post_shapes and has_level_9_gate(s)),
    Step("oops_all", "ZORA oops_all_enemies + oops_all_bosses", oops_all_step,
         lambda s: s.post_shapes and s.extras.oops_all, restart_label="oops all: "),
    Step("randomize_magical_sword", "ZORA randomize_magical_sword", randomize_magical_sword_step,
         lambda s: s.post_shapes and s.extras.randomize_magical_sword),
    Step("randomize_letter", "ZORA randomize_letter", randomize_letter_step,
         lambda s: s.post_shapes and s.extras.randomize_letter),
    Step("shop_items_in_pool", "ZORA shop_items_in_pool", shop_items_in_pool_step,
         lambda s: s.post_shapes and s.extras.shop_items_in_pool),
    Step("shuffle_blue_potion", "ZORA shuffle_blue_potion", shuffle_blue_potion_step,
         lambda s: s.post_shapes and s.extras.shuffle_blue_potion),
    Step("join_level_2_sword", "ZORA add_l4_sword = Level 2", join_level_2_sword_step,
         lambda s: s.post_shapes and s.extras.l4_sword_in_level_2),
    Step("shuffle_wood_sword", "ZORA shuffle_wood_sword", shuffle_wood_sword_step,
         lambda s: s.post_shapes and s.extras.shuffle_wood_sword, restart_label="shuffle wood sword: "),
    Step("add_l4_sword", "ZORA add_l4_sword = Level 9", add_l4_sword_step,
         lambda s: s.post_shapes and s.extras.l4_sword_in_level_9),
    Step("change_sword_hearts", "B10 + ZORA randomize_magical_sword or level 9 entrance",
         change_sword_hearts_before_check,
         lambda s: (s.post_shapes and s.extras.checks_magical_sword_hearts and s.feature_data
                    and s.steps.change_sword_hearts)),
    Step("check_item_spots", "", check_item_spots_step, post_shapes, restart_label=""),
    Step("check_gatekeepers", "ZORA gatekeeper_bosses", check_gatekeepers_step,
         lambda s: bool(s.extras.gatekeeper_bosses), restart_label="gatekeeper: "),
    Step("acceptance_check", "", acceptance_check_step, post_shapes, restart_label="acceptance: "),
    Step("check_white_sword_hearts", "", check_white_sword_hearts_step, post_shapes, restart_label="acceptance: "),
    Step("check_magical_sword_hearts", "ZORA randomize_magical_sword or level 9 entrance",
         check_magical_sword_hearts_step,
         lambda s: s.post_shapes and s.extras.checks_magical_sword_hearts, restart_label="acceptance: "),
    Step("ship", "", ship_step),
    # On the shipped world
    Step("cap_level_9_vire_hp", "owner rule #14", cap_level_9_vire_hp_step, post_shapes),
    Step("highlight_no_drop_rooms", "ZORA highlight_no_drop_rooms", highlight_no_drop_rooms_step,
         lambda s: (s.post_shapes and s.extras.highlight_no_drop_rooms
                    and not s.shape_options.universal_drops)),
    Step("draw_person_appearances", "", draw_person_appearances_step, post_shapes),
    Step("change_sword_hearts", "B10", change_sword_hearts_after_ship, draws_sword_hearts_after_ship),
    Step("randomize_mazes", "ZORA randomize_lost_hills + randomize_dead_woods", randomize_mazes_step,
         lambda s: s.post_shapes and (s.extras.gates.lost_hills or s.extras.gates.dead_woods)),
    Step("generate_hint_text", "C03", generate_hint_text_step, post_shapes),
    Step("shuffle_dungeon_text", "B19", shuffle_dungeon_text_step,
         lambda s: s.post_shapes and s.steps.shuffle_dungeon_text),
    Step("ship_hint_text", "", ship_hint_text_step, post_shapes),
    Step("boss_sound_end_pass", "", boss_sound_end_pass_step, post_shapes),
    Step("change_bomb_upgrades", "B12, B90", change_bomb_upgrades_step,
         lambda s: feature_data(s) and (s.steps.change_bomb_upgrades or s.steps.increase_bomb_capacity)),
    Step("change_money_making_game", "B11", change_money_making_game_step,
         lambda s: feature_data(s) and s.steps.change_money_making_game),
    Step("speed_up_text", "B54", speed_up_text_step, lambda s: feature_data(s) and s.steps.speed_up_text),
    Step("write_fixed_feature_data", "", write_fixed_feature_data_step, feature_data),
    Step("level_9_entrance_text", "ZORA level 9 entrance", level_9_entrance_text_step,
         lambda s: feature_data(s) and s.extras.level_9_entrance_sword),
    Step("level_9_gate_text", "C08", level_9_gate_text_step, lambda s: s.post_shapes and has_level_9_gate(s)),
    Step("set_starting_hearts", "C16", set_starting_hearts_step,
         lambda s: s.alternatives.starting_hearts != MVP_VALUES.starting_hearts),
    Step("start_items", "B57-B78, B85 with C17", start_items_step, lambda s: bool(s.alternatives.start_items)),
    Step("start_triforce_pieces", "C18", start_triforce_pieces_step,
         lambda s: bool(s.alternatives.start_triforce_pieces)),
    Step("check_boss_sounds", "", check_boss_sounds_step, post_shapes),
)
