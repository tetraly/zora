"""
GameConfig: resolved configuration for a single game generation.

This is the internal representation produced by resolving a Flags instance
against the RNG. All tristates are collapsed to bools and item enum fields
are resolved to concrete Item values or None.

This is Layer 2 in the three-layer design:
  Layer 1: Flags      — wire format (base62, tristates, shareable between racers)
  Layer 2: GameConfig — resolved config for one specific generation (internal only)
  Layer 3: modules    — assumed_fill, validator etc. take only what they need
"""

from dataclasses import dataclass
from enum import Enum, auto

from flags.flags_generated import (
    BossHp,
    CaveShuffleMode,
    CosmeticFlags,
    DeathwarpButton,
    EnemyHp,
    Flags,
    LevelName,
    LowHeartsSound,
    SelectSwapMode,
    StartScreen,
    Tristate,
    VisualRoarSound,
)
from flags.flags_generated import (
    HintMode as FlagHintMode,
)
from flags.flags_generated import (
    Item as FlagItem,
)
from zora.data_model import Item
from zora.rng import Rng


class HintMode(Enum):
    VANILLA   = auto()
    BLANK     = auto()
    COMMUNITY = auto()
    HELPFUL   = auto()


@dataclass(frozen=True)
class GameConfig:
    # Item shuffle scope
    shuffle_dungeon_items: bool = False
    shuffle_dungeon_hearts: bool = False
    shuffle_within_dungeons: bool = False
    triforces_in_stairways: bool = False
    shuffle_wood_sword: bool = False
    shuffle_white_sword: bool = False
    shuffle_magical_sword: bool = False
    shuffle_letter: bool = False
    shuffle_armos_item: bool = False
    shuffle_coast_item: bool = False
    shuffle_major_shop_items: bool = False
    shuffle_blue_potion: bool = False

    # Forced placements (None = not forced / random)
    forced_white_sword_item: Item | None = None
    forced_armos_item: Item | None = None
    forced_coast_item: Item | None = None

    # Level 9 constraints
    allow_important_in_l9: bool = False
    force_rr_to_l9: bool = False
    force_sa_to_l9: bool = False

    # Validator behaviour
    avoid_required_hard_combat: bool = False

    # Item behaviour
    progressive_items: bool = False
    add_extra_candles: bool = False

    # Hint randomization
    hint_mode: HintMode = HintMode.VANILLA

    # MMG prize randomization
    randomize_mmg: bool = False

    # Bomb upgrade randomization
    randomize_bomb_upgrade: bool = False

    # Start screen randomization (mutually exclusive; all False = vanilla)
    easy_start_shuffle: bool = False
    full_start_shuffle: bool = False
    wood_sword_cave_start: bool = False

    # Entrance shuffle
    shuffle_dungeon_entrances: bool = False
    shuffle_non_dungeon_caves: bool = False
    shuffle_armos_location: bool = False
    include_wood_sword_cave: bool = False
    include_any_road_caves: bool = False

    # Speed patches
    speed_up_dungeon_transitions: bool = False
    speed_up_text: bool = False

    # Overworld block patches
    extra_raft_blocks: bool = False
    extra_power_bracelet_blocks: bool = False

    # Maze direction randomization
    randomize_lost_hills: bool = False
    randomize_dead_woods: bool = False

    # Recorder warp screen update
    update_recorder_warp_screens: bool = False

    randomize_dungeon_palettes: bool = False

    # Quality of life patches
    fast_fill: bool = False
    flute_kills_pols: bool = False
    low_hearts_sound: LowHeartsSound = LowHeartsSound.REGULAR
    four_potion_inventory: bool = False
    auto_show_letter: bool = False
    like_like_rupees: bool = False

    # Shop item shuffling
    shuffle_shop_items: bool = False

    # Cave heart requirement randomization
    randomize_white_sword_hearts: bool = False
    randomize_magical_sword_hearts: bool = False

    # Gameplay patches
    permanent_sword_beam: bool = False
    book_is_an_atlas: bool = False
    book_is_a_translator: bool = False
    disable_music: bool = False
    reduce_flashing: bool = False
    visual_roar_sound: VisualRoarSound = VisualRoarSound.DISABLED
    replace_book_fire_with_explosion: bool = False
    fix_known_bugs: bool = False

    # Cosmetic patches
    select_swap_mode: SelectSwapMode = SelectSwapMode.PAUSE
    deathwarp_button: DeathwarpButton = DeathwarpButton.P2_UP_A
    level_name: LevelName = LevelName.LEVEL

    # Item behaviour patches
    add_l4_sword: bool = False
    magical_boomerang_does_one_hp_damage: bool = False

    # Color cosmetics (None = vanilla, int = NES palette byte 0x00-0x3F)
    green_tunic_color: int | None = None
    blue_ring_color: int | None = None
    red_ring_color: int | None = None
    heart_color: int | None = None

    # Dungeon room randomization
    shuffle_dungeon_rooms: bool = False
    scramble_dungeon_rooms: bool = False

    # Enemy randomization
    shuffle_dungeon_monsters: bool = False
    shuffle_ganon_zelda: bool = False
    force_ganon: bool = False
    shuffle_enemy_groups: bool = False
    shuffle_bosses: bool = False
    change_dungeon_boss_groups: bool = False
    randomize_overworld_enemies: bool = False
    include_level_9: bool = False
    shuffle_monsters_between_levels: bool = False
    add_2nd_quest_monsters: bool = False
    change_enemy_hp: int = 0
    enemy_hp_to_zero: bool = False
    shuffle_boss_hp: int = 0
    boss_hp_to_zero: bool = False
    ganon_hp_to_zero: bool = False
    max_enemy_health: bool = False
    max_boss_health: bool = False
    swordless: bool = False

def _resolve_hint_mode(flag_hint_mode: FlagHintMode, rng: Rng) -> HintMode:
    """Resolve the hint_mode enum flag to a concrete HintMode.

    FlagHintMode.RANDOM resolves to a uniform random choice among the four
    concrete modes.
    """
    concrete_modes = [HintMode.VANILLA, HintMode.BLANK, HintMode.COMMUNITY, HintMode.HELPFUL]
    mapping = {
        FlagHintMode.VANILLA:   HintMode.VANILLA,
        FlagHintMode.BLANK:     HintMode.BLANK,
        FlagHintMode.COMMUNITY: HintMode.COMMUNITY,
        FlagHintMode.HELPFUL:   HintMode.HELPFUL,
        FlagHintMode.RANDOM:    rng.choice(concrete_modes),
    }
    return mapping[flag_hint_mode]


_CONCRETE_ROAR_SOUNDS = [
    VisualRoarSound.ROAR,
    VisualRoarSound.RAWR,
    VisualRoarSound.MEOW,
    VisualRoarSound.WOOF,
    VisualRoarSound.HISS,
    VisualRoarSound.HONK,
]


_CONCRETE_LEVEL_NAMES = [name for name in LevelName if name not in (LevelName.RANDOM_CHOICE,)]


def _resolve_level_name(name: LevelName, rng: Rng) -> LevelName:
    if name == LevelName.RANDOM_CHOICE:
        return rng.choice(_CONCRETE_LEVEL_NAMES)
    return name


def _resolve_visual_roar_sound(sound: VisualRoarSound, rng: Rng) -> VisualRoarSound:
    if sound == VisualRoarSound.RANDOM:
        return rng.choice(_CONCRETE_ROAR_SOUNDS)
    return sound


# ---------------------------------------------------------------------------
# Color flag resolution
# ---------------------------------------------------------------------------

# Flag value → NES palette index mapping.
# Value 0 = vanilla, value 14 = random, others map to NES colors
# (0x0D and 0x0E are excluded from the palette).
_COLOR_FLAG_TO_NES: dict[int, int] = {}
_nes_idx = 0
for _flag_val in range(1, 64):
    if _flag_val == 14:
        continue  # slot 14 = random, not a NES color
    while _nes_idx in (0x0D, 0x0E):
        _nes_idx += 1
    _COLOR_FLAG_TO_NES[_flag_val] = _nes_idx
    _nes_idx += 1

# Curated random color pools (NES palette indices)
_TUNIC_RANDOM_POOL = [0x29, 0x32, 0x16, 0x24, 0x31, 0x30, 0x3D, 0x0C, 0x1A, 0x03, 0x17]
_HEART_RANDOM_POOL = [0x29, 0x22, 0x16, 0x0C, 0x1A, 0x03, 0x17]


def _resolve_color(
    flag_value: int,
    rng: Rng,
    random_pool: list[int],
    exclude: list[int] | None = None,
) -> int | None:
    """Resolve a color flag value to a NES palette byte or None (vanilla).

    Args:
        flag_value: Raw flag value (0=vanilla, 14=random, others=NES color).
        rng: RNG for random resolution.
        random_pool: Curated color pool for random picks.
        exclude: NES palette bytes to exclude from random picks (for tunic uniqueness).

    Returns:
        NES palette byte (0x00-0x3F) or None for vanilla.
    """
    if flag_value == 0:
        return None  # vanilla
    if flag_value == 14:
        # Random: pick from curated pool, excluding specified colors
        pool = random_pool
        if exclude:
            pool = [c for c in pool if c not in exclude]
        return rng.choice(pool) if pool else rng.choice(random_pool)
    return _COLOR_FLAG_TO_NES.get(flag_value)


def resolve_game_config(flags: Flags, rng: Rng, cosmetic_flags: CosmeticFlags | None = None) -> GameConfig:
    """Resolve a Flags instance into a GameConfig using the RNG.

    Tristates are resolved to bools: ON -> True, OFF -> False, RANDOM ->
    coin-flip via rng.random(). Resolution respects flag dependencies — if a
    prerequisite resolves to False, dependents cascade to False regardless of
    their own value.

    Args:
        flags:          Flags instance (may contain Tristate.RANDOM values).
        rng:            Rng instance used to resolve RANDOM tristates.
        cosmetic_flags: Optional CosmeticFlags instance. Defaults to vanilla
                        (all-default) when None.

    Returns:
        GameConfig with all fields resolved to concrete values.
    """
    if cosmetic_flags is None:
        cosmetic_flags = CosmeticFlags()

    def resolve(tristate: Tristate) -> bool:
        if tristate == Tristate.ON:
            return True
        if tristate == Tristate.OFF:
            return False
        return rng.random() < 0.5

    def resolve_location_item(flag_item: FlagItem) -> tuple[bool, Item | None]:
        """Resolve a location item flag to (shuffle, forced_item).

        NOT_SHUFFLED → (False, None): location stays vanilla, not in pool
        RANDOM       → (True, None):  location in pool, no forced placement
        <named item> → (True, item):  location in pool, item forced here
        """
        if flag_item == FlagItem.NOT_SHUFFLED:
            return False, None
        if flag_item == FlagItem.RANDOM:
            return True, None
        return True, Item[flag_item.name]

    # Resolve with dependency ordering: prerequisites before dependents.
    progressive_items = resolve(flags.progressive_items)
    add_extra_candles = resolve(flags.add_extra_candles) and not progressive_items

    shuffle_dungeon_items = resolve(flags.shuffle_dungeon_items)
    shuffle_dungeon_hearts = resolve(flags.shuffle_dungeon_hearts) if shuffle_dungeon_items else False
    shuffle_within_dungeons = resolve(flags.shuffle_within_dungeons)
    triforces_in_stairways = resolve(flags.allow_triforces_in_stairways) if shuffle_within_dungeons else False
    shuffle_wood_sword = resolve(flags.shuffle_wood_sword)
    shuffle_magical_sword = resolve(flags.shuffle_magical_sword)
    shuffle_letter = resolve(flags.shuffle_letter)
    shuffle_major_shop_items = resolve(flags.shuffle_major_shop_items)
    shuffle_blue_potion = resolve(flags.shuffle_blue_potion)

    shuffle_white_sword, forced_white_sword_item = resolve_location_item(flags.white_sword_item)
    shuffle_armos_item, forced_armos_item = resolve_location_item(flags.armos_item)
    shuffle_coast_item, forced_coast_item = resolve_location_item(flags.coast_item)

    allow_important_in_l9 = resolve(flags.allow_important_in_l9)

    # force_rr/sa require shuffle_dungeon_items to be meaningful
    force_rr_to_l9 = resolve(flags.force_rr_to_l9) if shuffle_dungeon_items else False
    force_sa_to_l9 = resolve(flags.force_sa_to_l9) if shuffle_dungeon_items else False

    # Entrance shuffle — resolve cave_shuffle_mode enum (may be random)
    _cave_mode = flags.cave_shuffle_mode
    if _cave_mode == CaveShuffleMode.VANILLA:
        shuffle_dungeon_entrances = False
        shuffle_non_dungeon_caves = False
    elif _cave_mode == CaveShuffleMode.DUNGEONS_ONLY:
        shuffle_dungeon_entrances = True
        shuffle_non_dungeon_caves = False
    elif _cave_mode == CaveShuffleMode.NON_DUNGEONS_ONLY:
        shuffle_dungeon_entrances = False
        shuffle_non_dungeon_caves = True
    else:  # ALL_CAVES
        shuffle_dungeon_entrances = True
        shuffle_non_dungeon_caves = True

    shuffle_armos_location = resolve(flags.shuffle_armos_location)
    include_wood_sword_cave = resolve(flags.include_wood_sword_cave) if shuffle_non_dungeon_caves else False
    include_any_road_caves = resolve(flags.include_any_road_caves) if shuffle_non_dungeon_caves else False

    _ss = flags.start_screen
    easy_start_shuffle    = (_ss == StartScreen.EASY_SHUFFLE)
    full_start_shuffle    = (_ss == StartScreen.FULL_SHUFFLE)
    wood_sword_cave_start = (_ss == StartScreen.WOOD_SWORD_SCREEN)

    # Resolve color cosmetics (order matters: blue ring excludes start, red excludes both)
    green_tunic_color = _resolve_color(cosmetic_flags.green_tunic_color, rng, _TUNIC_RANDOM_POOL)
    blue_ring_color = _resolve_color(
        cosmetic_flags.blue_ring_color, rng, _TUNIC_RANDOM_POOL,
        exclude=[green_tunic_color] if green_tunic_color is not None else [],
    )
    red_ring_color = _resolve_color(
        cosmetic_flags.red_ring_color, rng, _TUNIC_RANDOM_POOL,
        exclude=[c for c in (green_tunic_color, blue_ring_color) if c is not None],
    )
    heart_color = _resolve_color(cosmetic_flags.heart_color, rng, _HEART_RANDOM_POOL)

    # Dungeon room randomization
    shuffle_dungeon_rooms = resolve(flags.shuffle_dungeon_rooms)
    scramble_dungeon_rooms = resolve(flags.scramble_dungeon_rooms)

    # Enemy randomization — resolve HP enums to config fields
    _enemy_hp = flags.enemy_hp
    if _enemy_hp == EnemyHp.RANDOM:
        _enemy_hp = rng.choice([EnemyHp.NORMAL, EnemyHp.PLUS_MINUS_2,
                                EnemyHp.PLUS_MINUS_4, EnemyHp.ZERO])

    if _enemy_hp == EnemyHp.NORMAL:
        change_enemy_hp = 0
        enemy_hp_to_zero = False
    elif _enemy_hp == EnemyHp.PLUS_MINUS_2:
        change_enemy_hp = 2
        enemy_hp_to_zero = False
    elif _enemy_hp == EnemyHp.PLUS_MINUS_4:
        change_enemy_hp = 4
        enemy_hp_to_zero = False
    else:  # ZERO
        change_enemy_hp = 0
        enemy_hp_to_zero = True

    _boss_hp = flags.boss_hp
    if _boss_hp == BossHp.RANDOM:
        _boss_hp = rng.choice([BossHp.NORMAL, BossHp.PLUS_MINUS_2,
                               BossHp.PLUS_MINUS_4, BossHp.ZERO])

    if _boss_hp == BossHp.NORMAL:
        shuffle_boss_hp = 0
        boss_hp_to_zero = False
    elif _boss_hp == BossHp.PLUS_MINUS_2:
        shuffle_boss_hp = 2
        boss_hp_to_zero = False
    elif _boss_hp == BossHp.PLUS_MINUS_4:
        shuffle_boss_hp = 4
        boss_hp_to_zero = False
    else:  # ZERO
        shuffle_boss_hp = 0
        boss_hp_to_zero = True

    shuffle_dungeon_monsters = resolve(flags.shuffle_dungeon_monsters)
    shuffle_ganon_zelda = resolve(flags.shuffle_ganon_zelda) if shuffle_dungeon_monsters else False
    include_level_9 = resolve(flags.shuffle_level_9_monsters)
    shuffle_monsters_between_levels = resolve(flags.shuffle_monsters_between_levels)
    add_2nd_quest_monsters = resolve(flags.add_2nd_quest_monsters) if shuffle_monsters_between_levels else False
    shuffle_enemy_groups = resolve(flags.shuffle_enemy_groups)
    shuffle_bosses = resolve(flags.shuffle_bosses)
    change_dungeon_boss_groups = resolve(flags.change_dungeon_boss_groups)
    randomize_overworld_enemies = resolve(flags.shuffle_overworld_monsters) if shuffle_enemy_groups else False

    return GameConfig(
        shuffle_dungeon_items=shuffle_dungeon_items,
        shuffle_dungeon_hearts=shuffle_dungeon_hearts,
        shuffle_within_dungeons=shuffle_within_dungeons,
        triforces_in_stairways=triforces_in_stairways,
        shuffle_wood_sword=shuffle_wood_sword,
        shuffle_white_sword=shuffle_white_sword,
        shuffle_magical_sword=shuffle_magical_sword,
        shuffle_letter=shuffle_letter,
        shuffle_armos_item=shuffle_armos_item,
        shuffle_coast_item=shuffle_coast_item,
        shuffle_major_shop_items=shuffle_major_shop_items,
        shuffle_blue_potion=shuffle_blue_potion,
        forced_white_sword_item=forced_white_sword_item,
        forced_armos_item=forced_armos_item,
        forced_coast_item=forced_coast_item,
        allow_important_in_l9=allow_important_in_l9,
        force_rr_to_l9=force_rr_to_l9,
        force_sa_to_l9=force_sa_to_l9,
        avoid_required_hard_combat=resolve(flags.avoid_required_hard_combat),
        progressive_items=progressive_items,
        add_extra_candles=add_extra_candles,
        hint_mode=_resolve_hint_mode(flags.hint_mode, rng),
        randomize_mmg=resolve(flags.randomize_mmg),
        randomize_bomb_upgrade=resolve(flags.randomize_bomb_upgrade),
        easy_start_shuffle=easy_start_shuffle,
        full_start_shuffle=full_start_shuffle,
        wood_sword_cave_start=wood_sword_cave_start,
        shuffle_dungeon_entrances=shuffle_dungeon_entrances,
        shuffle_non_dungeon_caves=shuffle_non_dungeon_caves,
        shuffle_armos_location=shuffle_armos_location,
        include_wood_sword_cave=include_wood_sword_cave,
        include_any_road_caves=include_any_road_caves,
        speed_up_dungeon_transitions=resolve(flags.speed_up_dungeon_transitions),
        speed_up_text=resolve(flags.speed_up_text),
        extra_raft_blocks=resolve(flags.extra_raft_blocks),
        extra_power_bracelet_blocks=resolve(flags.extra_power_bracelet_blocks),
        randomize_lost_hills=resolve(flags.randomize_lost_hills),
        randomize_dead_woods=resolve(flags.randomize_dead_woods),
        update_recorder_warp_screens=resolve(flags.update_recorder_warp_screens),
        randomize_dungeon_palettes=resolve(flags.randomize_dungeon_palettes),
        fast_fill=resolve(flags.fast_fill),
        flute_kills_pols=resolve(flags.flute_kills_pols),
        low_hearts_sound=cosmetic_flags.low_hearts_sound,
        four_potion_inventory=resolve(flags.four_potion_inventory),
        auto_show_letter=resolve(flags.auto_show_letter),
        like_like_rupees=resolve(flags.like_like_rupees),
        shuffle_shop_items=resolve(flags.shuffle_shop_items),
        randomize_white_sword_hearts=flags.randomize_white_sword_hearts,
        randomize_magical_sword_hearts=flags.randomize_magical_sword_hearts,
        permanent_sword_beam=resolve(flags.permanent_sword_beam),
        book_is_an_atlas=resolve(flags.book_is_an_atlas),
        book_is_a_translator=resolve(flags.book_is_a_translator),
        disable_music=cosmetic_flags.disable_music == Tristate.ON,
        reduce_flashing=cosmetic_flags.reduce_flashing == Tristate.ON,
        visual_roar_sound=_resolve_visual_roar_sound(flags.visual_roar_sound, rng),
        replace_book_fire_with_explosion=resolve(flags.replace_book_fire_with_explosion),
        fix_known_bugs=resolve(flags.fix_known_bugs),
        select_swap_mode=cosmetic_flags.select_swap_mode,
        deathwarp_button=cosmetic_flags.deathwarp_button,
        level_name=_resolve_level_name(cosmetic_flags.level_name, rng),
        add_l4_sword=flags.add_l4_sword and progressive_items,
        magical_boomerang_does_one_hp_damage=flags.magical_boomerang_does_one_hp_damage,
        green_tunic_color=green_tunic_color,
        blue_ring_color=blue_ring_color,
        red_ring_color=red_ring_color,
        heart_color=heart_color,
        # Dungeon room randomization
        shuffle_dungeon_rooms=shuffle_dungeon_rooms,
        scramble_dungeon_rooms=scramble_dungeon_rooms,
        # Enemy randomization
        shuffle_dungeon_monsters=shuffle_dungeon_monsters,
        shuffle_ganon_zelda=shuffle_ganon_zelda,
        force_ganon=True,
        shuffle_enemy_groups=shuffle_enemy_groups,
        shuffle_bosses=shuffle_bosses,
        change_dungeon_boss_groups=change_dungeon_boss_groups,
        randomize_overworld_enemies=randomize_overworld_enemies,
        include_level_9=include_level_9,
        shuffle_monsters_between_levels=shuffle_monsters_between_levels,
        add_2nd_quest_monsters=add_2nd_quest_monsters,
        change_enemy_hp=change_enemy_hp,
        enemy_hp_to_zero=enemy_hp_to_zero,
        shuffle_boss_hp=shuffle_boss_hp,
        boss_hp_to_zero=boss_hp_to_zero,
        ganon_hp_to_zero=resolve(flags.ganon_hp_to_zero),
        max_enemy_health=False,
        max_boss_health=False,
        swordless=False,
    )
