"""Generation as a list of steps (generation_pass.STEPS): the settings every
step reads, the context one attempt's steps share, and the Step record.

Each attempt starts from a fresh GenerationContext: the base world (written
only when the attempt ships), the decoded settings, the random stream (it
continues across attempts, SH-FLOW-03) and this attempt's levels, overworld
and staged results. A step that fails restarts the attempt, and nothing it
or an earlier step of that attempt wrote survives.
"""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from zora.generate.alternative_values import MVP_VALUES, AlternativeValues
from zora.generate.extra_options import NO_EXTRAS, ExtraOptions
from zora.generate.flag_steps import ALL_STEPS_ON, FlagSteps
from zora.generate.rng import Rng
from zora.generate.shapes.enemies import EnemyPools
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.world import SetWorld
from zora.generate.ship import StagedSets
from zora.generate.steps.assign_hints_for_hint_type import HintAssignmentResult
from zora.generate.steps.cave_entries import CaveShuffle, Entry
from zora.generate.steps.change_enemy_hp import EnemyHpResult
from zora.generate.steps.dungeon_room_shuffle import DungeonRoomShuffleResult
from zora.generate.steps.extra_pool_items import ExtraPoolItems
from zora.generate.steps.hint_text import HintTextResult
from zora.generate.steps.item_shuffle_result import ItemShuffleResult
from zora.generate.steps.monster_lists import MonsterShuffleResult, RoomLists
from zora.generate.steps.shuffle_dungeon_drops import ShapeSnapshot
from zora.generate.steps.shuffle_dungeon_palettes import DungeonPaletteResult
from zora.generate.steps.shuffle_groups import GroupShuffleResult
from zora.generate.steps.shuffle_start_screen import StartScreen
from zora.model.game_world import GameWorld
from zora.model.overworld import Overworld


@dataclass
class GenerationResult:
    attempts: int = 0
    # The shipped pass's plans as the shape stage left them. Every pass
    # after it runs on the staged levels built from them and is not
    # reflected here; read the GameWorld for the finished rooms.
    sets: list[SetWorld] = field(default_factory=list)
    pools: EnemyPools | None = None
    hint_level9_left_column: int | None = None
    restart_reasons: list[str] = field(default_factory=list)
    gate_attempts: int = 0       # passes lost to budget exhaustion (gen restarts)
    gate_rejections: int = 0     # total re-deal attempts that failed checks
    gate_per_level: dict[int, int] = field(default_factory=dict)
    gate_kinds: dict[str, int] = field(default_factory=dict)
    gate_exhaustion: list[tuple[int, tuple[int, ...]]] = field(
        default_factory=list
    )
    # survey-only (gate.SURVEY): per pass, (exhausted, per-attempt records)
    gate_surveys: list[tuple[bool, list[tuple[int, str, bool | None, bool, int, bool]]]] = \
        field(default_factory=list)
    item_shuffle_result: ItemShuffleResult | None = None
    monster_shuffle: MonsterShuffleResult | None = None
    room_shuffle: DungeonRoomShuffleResult | None = None     # the last pass's room exchange (PS-XCHG)
    groups: GroupShuffleResult | None = None    # the shipped pass's group passes (B4)
    overworld: CaveShuffle | None = None   # the shipped pass's cave shuffle (OW-CAVE)
    extra_pool_items: ExtraPoolItems | None = None   # the shipped pass's ZORA extras' caves
    # acceptance.md: rejections by check (E1, E3, E4, E5)
    acceptance_rejections: Counter[str] = field(default_factory=Counter)
    # level-1 census at gate entry of the shipped pass: (person rooms,
    # rooms whose layout restricts movement)
    l1_gate_entry: tuple[int, int] | None = None


@dataclass(frozen=True)
class GenerationSettings:
    """The decoded settings the steps read; each step's enabled predicate tests them."""
    shape_options: ShapeOptions
    # False skips every post-shapes pass: the shape stage ships straight into the late gate
    post_shapes: bool = True
    feature_data: bool = False       # B10's DATA items (GameConfig.features_b10)
    seed: int = 0                    # the seed number, shown on the title screen
    steps: FlagSteps = ALL_STEPS_ON   # the flag-switched steps (FL-OFF)
    extras: ExtraOptions = NO_EXTRAS   # the ZORA extras
    alternatives: AlternativeValues = MVP_VALUES   # the alternative values (FL-ALT)


@dataclass
class GenerationContext:
    """One generation attempt. `world` is the base GameWorld: every step before
    ship reads it and none writes it; ship writes the attempt into it, and the
    steps after ship work on the shipped world."""
    world: GameWorld
    settings: GenerationSettings
    rng: Rng
    result: GenerationResult         # shared by every attempt: attempts, restart reasons, the gate's figures
    pools: EnemyPools                # SH-ENEMY-01, harvested once from the base levels
    pre_shapes_goriya_tile: int | None   # PS-GRUM-03's draw before the first attempt
    # This attempt: the shape stage's plans and the levels and blocks built from them
    plans: list[SetWorld] = field(default_factory=list)
    sets: StagedSets = field(init=False)
    item_shuffle_result: ItemShuffleResult = field(init=False)
    extra_pool_items: ExtraPoolItems = field(default_factory=ExtraPoolItems)
    # The post-shapes passes' staged results (None without the post-shapes passes)
    room_lists: RoomLists | None = None
    shapes_snapshot: ShapeSnapshot | None = None
    hint_assignment: HintAssignmentResult | None = None
    palettes: DungeonPaletteResult | None = None
    monster_shuffle: MonsterShuffleResult | None = None
    overworld: Overworld | None = None           # the staged copy of the base overworld
    hit_points: EnemyHpResult | None = None
    groups: GroupShuffleResult | None = None
    cave_entries: list[Entry] = field(default_factory=list)
    armos_screen: int | None = None
    caves: CaveShuffle | None = None
    l1_gate_entry: tuple[int, int] | None = None
    start: StartScreen | None = None
    hint_text: HintTextResult | None = None
    # Randomize Lost Hills / Dead Woods: each hint shop offer's new text (randomize_mazes)
    maze_offers: dict[int, list[str]] = field(default_factory=dict)


def always(_settings: GenerationSettings) -> bool:
    return True


@dataclass(frozen=True)
class Step:
    """One generation step. name: the step's function, after its flag's name
    (docs/flag-names.md), or a descriptive name for a pass without a flag;
    flag: the field or ZORA flag that switches it ("" for none). A step whose
    enabled predicate is false does not run. restart_label: a GenerationFailure
    the step raises restarts the attempt, recorded as this label plus the
    failure; None lets it propagate (a step that never fails)."""
    name: str
    flag: str
    run: Callable[[GenerationContext], None]
    enabled: Callable[[GenerationSettings], bool] = always
    restart_label: str | None = None
