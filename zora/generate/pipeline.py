"""Generation from a flag string and a seed: every entry point's way in.

The flag string is decoded (flags-behavior.md FL-ENC), corrected (FL-DEP-06:
B23 off when B22 is off), checked against the dependency rules (FL-DEP-01/02,
refused with the rule's message), adjusted (FL-DEP-02 rules 4-5, FL-DEP-05)
and judged against the support matrix (FL-SUP-01, FL-OFF-07, FL-ALT): a string with
any field the MVP does not produce is refused, naming the fields, and a "?"
that may come up at an unsupported value is refused up front. Encode level
data (B82) is on or off and never "?" (owner ruling, 2026-10-06). Nothing falls
back silently. The "?" values are then resolved per seed from their own
stream (FL-DEP-04), the generator's settings and its flag-switched steps
(FL-OFF) are derived from the resolved fields, and the result carries the
canonical, unresolved flag string, which is also part of the level-encoding
key.

The ZORA flag string (zora/flags/zora_flags.py, docs/zora-extras.md) comes
beside it: empty is every ZORA flag off and today's output. It is decoded
strictly and judged against the Z1R settings; any ZORA flag on mixes both
strings into the generation seed, and the level-encoding key covers both.
"""
from __future__ import annotations

import copy
import hashlib
from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..flags import zora_flags
from ..flags.codec import FlagStringError, decode, encode
from ..flags.dependencies import (
    apply_dependencies,
    boss_hit_point_change,
    check_dependencies,
    enemy_hit_point_change,
    generation_settings,
    is_resolved,
    meet_cave_prerequisite,
    meet_monster_prerequisite,
    meet_room_prerequisite,
    piece_count_range,
    resolve,
    starting_hearts,
    white_sword_hearts,
    with_the_toll_beside_merchants,
    without_both_boss_health_rules,
)
from ..flags.fields import (
    ARMOS_PIN,
    BOOK_EXPLOSION,
    BOOK_TO_UNDERSTAND_NPCS,
    BOSS_HIT_POINTS,
    CAVE_SHUFFLE,
    CHANGE_HIDDEN_TILES,
    COAST_PIN,
    DO_NOT_SORT_SHAPES,
    DUNGEON_LAYOUT_SOURCE,
    DUNGEON_MONSTER_SHUFFLE,
    DUNGEON_ROOM_SHUFFLE,
    ENCODE_LEVEL_DATA,
    ENEMY_HIT_POINTS,
    FORCE_OVERWORLD_BLOCK,
    GANON_AND_ZELDA_SHUFFLE,
    GANON_HIT_POINTS_ZERO,
    GANON_MUST_BE_BEATEN,
    HIDDEN_HEALTH,
    HIDDEN_NUMBERS,
    HIDE_DUNGEON_NUMBERS,
    HINT_STYLE,
    IMPORTANT_ITEM_DROPS,
    IMPORTANT_ITEMS_IN_LEVEL_9,
    ITEM_APPEARANCE,
    ITEM_SHUFFLE_SCOPE,
    KILLABLE_DROP_ITEMS,
    LEVEL_9_FIRST_PIN,
    LEVEL_9_MONSTER_MOVES,
    LEVEL_9_REQUIREMENT,
    LEVEL_9_SECOND_PIN,
    LOST_WOODS_SHORTCUT,
    MAXIMUM_BOSS_HEALTH,
    MAXIMUM_ENEMY_HEALTH,
    MOST_OPEN_STAIRS_REMOVED,
    ONE_HIT_KNOCK_OUT,
    OPTIONS_BY_ID,
    OVERWORLD_GROUP_REDRAW,
    OVERWORLD_QUEST,
    PERMANENT_SWORD_BEAM,
    PREVENT_CLIPPING,
    RANDOM_DROP_RATE,
    RECORDER_TO_UNBEATEN,
    RED_BUBBLE,
    RIVER_BRIDGES,
    RUPEES_AFFECT_SPEED,
    START_ROOM_MAY_MOVE,
    START_SCREEN,
    TOGGLES_BY_ID,
    UNIVERSAL_DROPS_IN_SHAPES,
    WHITE_SWORD_CAVE_PIN,
    WOOD_SWORD_CAVE_BEHIND_BLOCKS,
    WOODEN_SWORD_STATE,
    CaveShuffle,
    DungeonLayoutSource,
    DungeonRoomShuffle,
    HintStyle,
    HitPointChange,
    ItemShuffleScope,
    Level9Requirement,
    OverworldQuest,
    Settings,
    StartScreen,
    ThreeState,
    WoodenSwordState,
)
from ..flags.support import (
    ENCODE_LEVEL_DATA_RANDOM_NOTICE,
    encode_level_data_is_random,
    is_postponed,
    postponed_notices,
    unsupported_fields,
    with_random_level_encoding_off,
)
from ..flags.zora_flags import ZoraFlags, ZoraFlagStringError
from ..model.enums import DungeonNothingCode
from ..rom import level_encoding
from ..rom.game_config import GameConfig, HintMode, LevelEncodingKey
from ..rom.player_settings import DEFAULT_PLAYER_SETTINGS, PlayerSettings, check_music_allowed
from .alternative_values import AlternativeValues
from .extra_options import ExtraOptions
from .flag_steps import FlagSteps
from .rng import Rng
from .shapes.options import ShapeOptions
from .steps.expanded_dungeon_locations import expanded_dungeon_locations_seed
from .steps.level_9_entry import Level9Entry
from .steps.overworld_gates import OverworldGates
from .steps.start_items import resolve_start_item_coins, start_state
from .steps.sword_states import BOMB_UPGRADE_STATES

if TYPE_CHECKING:
    from ..model.enums import Item
    from ..model.game_world import GameWorld
    from .acceptance_check import LogicRules
    from .context import GenerationResult
    from .finish import Assignment, Finished, ForeignLook
    from .places import Place

# C03 (hint style): mixed (index 4), helpful (index 1, HT-HINT-04) and community (index 2,
# FL-ALT-04) all write the generated 45-slot block; only its generation differs
# (show_every_helpful_hint, generate_community_hint_text). The level-9 and triforce texts depend
# only on whether hints are normal (FL-ALT-04), so they are the same.
HINT_STYLE_MODES: dict[int, HintMode] = {
    HintStyle.NORMAL: HintMode.NORMAL,
    HintStyle.MIXED: HintMode.CONSTERNATION,
    HintStyle.HELPFUL: HintMode.CONSTERNATION,
    HintStyle.COMMUNITY: HintMode.CONSTERNATION,
    HintStyle.DECEPTIVE: HintMode.CONSTERNATION,     # HT-HINT-06
    HintStyle.BLANK: HintMode.CONSTERNATION,         # HT-HINT-07
}
# The start of the refusal that names the fields the support matrix does not produce.
NOT_PRODUCED_PREFIX = "not produced: "
# Book is an Atlas: a code patch, so the serializer's switch (GameConfig).
BOOK_IS_AN_ATLAS = TOGGLES_BY_ID["B49"]
# The "?" stream's key: the seed number as eight bytes, and its own label.
SEED_BYTES = 8
QUESTION_MARK_STREAM = b"zora ? values"
# FL-DEP-02 rule 1's coin (OW-CAVE-10): its own stream, so no other draw moves
CAVE_PREREQUISITE_STREAM = b"zora cave coin"
MONSTER_PREREQUISITE_STREAM = b"zora rule3 coin"
ROOM_PREREQUISITE_STREAM = b"zora rule2 coin"
# B39 and B44 (PS-EDROP-01, PS-EDROP-02): their own stream, drawn in the final steps
ENEMY_DROPS_STREAM = b"zora enemy drops"
# C15 (FP-SPRITE-01): its own stream, drawn in the final steps
ITEM_SPRITES_STREAM = b"zora sprites"
# The marker mixed into the generation seed when level encoding is on.
ENCODED_GENERATION_STREAM = b"zora encoded"


# FL-SEED-01: the seed number is a decimal whole number; ZORA generates from 0 to 2^64 - 1
# (eight bytes, SEED_BYTES), which the page's digits-only seed field can exceed.
SEED_LIMIT = 1 << (8 * SEED_BYTES)


class SeedRefused(ValueError):
    """A seed number outside the range ZORA generates from."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        super().__init__(f"seed number {seed} refused: it must be a whole number from 0 to {SEED_LIMIT - 1}")


class FlagsRefused(ValueError):
    """A flag string that generation refuses, with every reason."""

    def __init__(self, flag_string: str, reasons: list[str]) -> None:
        self.flag_string = flag_string
        self.reasons = reasons
        super().__init__(f"flag string {flag_string!r} refused: " + "; ".join(reasons))


@dataclass(frozen=True)
class GenerationPlan:
    """What a flag string and seed ask the generator for."""
    seed: int
    flag_string: str                 # canonical (FL-ENC-03)
    settings: Settings               # resolved, as the generator sees them (FL-DEP-04, FL-DEP-05)
    shape_options: ShapeOptions
    steps: FlagSteps                 # the flag-switched steps that run (FL-OFF)
    alternatives: AlternativeValues  # the alternative values produced (FL-ALT)
    post_shapes: bool                # the post-shapes passes (off only in tests of the shape stage)
    config: GameConfig
    zora_flag_string: str = ""       # canonical; empty: every ZORA flag off
    # The game's part of it (zora_flags.game_string: the flags that rule only the player settings
    # left out), which the random streams and the level encoding key take.
    zora_game_string: str = ""
    zora: ZoraFlags = zora_flags.DEFAULT     # the decoded ZORA flags, "?" values as asked
    # The ZORA flags as the generator sees them: version-3 "?" values decided from their own stream
    # and the owner's dependencies applied (zora_flags.resolve_owner_dependencies). Never shown.
    zora_resolved: ZoraFlags = zora_flags.DEFAULT
    # What the seed leaves out of what was asked for, said on the page and in the spoiler log
    # (support.postponed_notices: Mirrored Overworld, B06)
    notices: tuple[str, ...] = ()

    @property
    def encode_level_data(self) -> bool:
        return self.config.level_encoding is not None

    @property
    def generation_seed(self) -> int:
        """The main random stream's key. With level encoding on, the seed number is mixed with a
        fixed marker, so the whole generation differs from the same seed number with encoding off
        and a plain ROM tells nothing about the encoded one
        (owner requirement, 2026-10-04). Plain seeds use the seed number itself. A ZORA flag on
        then mixes in both canonical strings (zora_flags.generation_seed; the empty ZORA string
        leaves the number as it is)."""
        seed = self.seed
        if self.encode_level_data:
            key = hashlib.blake2b(self.seed.to_bytes(SEED_BYTES, "little"), digest_size=SEED_BYTES,
                                  person=ENCODED_GENERATION_STREAM).digest()
            seed = int.from_bytes(key, "little")
        return zora_flags.generation_seed(seed, self.flag_string, self.zora_game_string)


@dataclass(frozen=True)
class GeneratedRom:
    rom: bytes
    seed: int
    flag_string: str                 # canonical, "?" values unresolved; part of the level-encoding key
    encode_level_data: bool
    code: tuple[str, ...] = ()        # the seed's code (FP-HASH-01): four item names, in screen order
    zora_flag_string: str = ""       # canonical


def _option_name(field_id: str) -> str:
    field = OPTIONS_BY_ID.get(field_id) or TOGGLES_BY_ID[field_id]
    return f"{field_id} ({field.setting})"


def _unsupported_name(settings: Settings, field_id: str) -> str:
    """A field the support matrix refuses, as the refusal names it: a "?" (a possible three-state
    field or an option at its random index) is refused as such, up front (owner ruling)."""
    if field_id in OPTIONS_BY_ID:
        undecided = OPTIONS_BY_ID[field_id].is_random(settings.option(field_id))
    else:
        undecided = settings.toggle(field_id) is ThreeState.POSSIBLE
    return _option_name(field_id) + (": ?" if undecided else "")


def _flag_key(seed: int, flag_string: str, person: bytes) -> int:
    """A stream's key derived only from the seed number and the canonical flag string."""
    key = hashlib.blake2b(flag_string.encode("utf-8"), key=seed.to_bytes(SEED_BYTES, "little"),
                          digest_size=SEED_BYTES, person=person).digest()
    return int.from_bytes(key, "little")


def _flag_stream(seed: int, flag_string: str, person: bytes) -> Rng:
    """A stream derived only from the seed number and the canonical flag string, separate from the
    generation's stream, whose draws it leaves untouched."""
    return Rng(_flag_key(seed, flag_string, person))


def question_mark_rng(seed: int, flag_string: str) -> Rng:
    """The stream that resolves "?" values (FL-DEP-04)."""
    return _flag_stream(seed, flag_string, QUESTION_MARK_STREAM)


def monster_prerequisite_rng(seed: int, flag_string: str) -> Rng:
    """The stream of FL-DEP-02 rule 3's coin (2026-10-22 export)."""
    return _flag_stream(seed, flag_string, MONSTER_PREREQUISITE_STREAM)


def room_prerequisite_rng(seed: int, flag_string: str) -> Rng:
    """The stream of FL-DEP-02 rule 2's coin (beta 8 export)."""
    return _flag_stream(seed, flag_string, ROOM_PREREQUISITE_STREAM)


def after_resolving(asked: Settings, resolved: Settings) -> Settings:
    """FL-DEP-04's rules after resolving that FL-DEP-01 rule 3 adds (B41 and B46 never both on) and
    the B22 and B23 rule (merchants never come without the toll re-drawn, owner ruling), each its own
    spoiler-log stage. Rule 4 (B47 beside a Book pin) is not applied: docs/deviations.md."""
    return with_the_toll_beside_merchants(asked, without_both_boss_health_rules(asked, resolved))


def cave_prerequisite_rng(seed: int, flag_string: str) -> Rng:
    """The stream of FL-DEP-02 rule 1's coin (OW-CAVE-10)."""
    return _flag_stream(seed, flag_string, CAVE_PREREQUISITE_STREAM)


def resolve_question_marks(settings: Settings, seed: int, flag_string: str) -> Settings:
    """FL-DEP-04: each "?" decided for this seed, a possible field by a fair coin and a random
    index uniformly among its alternatives; then FL-DEP-02 rule 4 again (C02 = 5 and 6 act through
    their drawn value, SH-SRC-10: a drawn 1, 2 or 4 turns B28 and B29 off). B23 is kept as drawn
    whatever B22's coin gives (FL-DEP-06). The resolved values are never shown or returned."""
    if is_resolved(settings):
        return settings
    # FP-START-02: the start items' coins first, from their own stream, so "?" draws none for them
    settings = resolve_start_item_coins(settings, seed, flag_string)
    return apply_dependencies(resolve(settings, question_mark_rng(seed, flag_string)))


def plan(flag_string: str, seed: int, zora_flag_string: str = "") -> GenerationPlan:
    """Decode and vet a flag string and a ZORA flag string; raise FlagsRefused or
    LevelEncodingUnavailable rather than generate something else; an out-of-range seed raises
    SeedRefused before anything is decoded."""
    if not 0 <= seed < SEED_LIMIT:
        raise SeedRefused(seed)
    try:
        decoded = decode(flag_string)        # B23 kept as given, whatever B22 is (FL-DEP-06)
    except FlagStringError as exc:
        raise FlagsRefused(flag_string, [str(exc)]) from exc
    refused = check_dependencies(decoded)
    if refused:
        raise FlagsRefused(flag_string, [f"{r.rule}: {r.message}" for r in refused])
    adjusted = apply_dependencies(decoded)
    # FP-TOURNEY-01: B82 at "?" reads as off, so the canonical string and the seed are the off string's
    level_encoding_read_as_off = encode_level_data_is_random(adjusted)
    adjusted = with_random_level_encoding_off(adjusted)
    reasons: list[str] = []
    # a postponed field is accepted and not produced (support.POSTPONED_TOGGLES; the plan's notices)
    unsupported = [field_id for field_id in unsupported_fields(adjusted)
                   if field_id != ENCODE_LEVEL_DATA.id and not is_postponed(adjusted, field_id)]
    if unsupported:
        reasons.append(NOT_PRODUCED_PREFIX + ", ".join(_unsupported_name(adjusted, field_id)
                                                       for field_id in unsupported))
    if reasons:
        raise FlagsRefused(flag_string, reasons)
    canonical = encode(adjusted)
    zora = decode_zora_flags(flag_string, zora_flag_string, adjusted)
    zora_canonical = zora_flags.encode(zora)
    resolved = after_resolving(adjusted, resolve_question_marks(adjusted, seed, canonical))
    zora_game = zora_flags.game_string(zora)        # without the flags that rule only player settings
    zora_resolved, resolved = zora_flags.resolve_owner_dependencies(
        zora_flags.resolve_question_marks(zora, seed, canonical, zora_game), zora, resolved, adjusted)
    resolved = meet_cave_prerequisite(resolved, cave_prerequisite_rng(seed, canonical))     # FL-DEP-02 rule 1
    resolved = meet_room_prerequisite(resolved, room_prerequisite_rng(seed, canonical))     # rule 2
    resolved = meet_monster_prerequisite(resolved, monster_prerequisite_rng(seed, canonical))   # rule 3
    settings = generation_settings(resolved)
    # FP-START-02 and FL-ALT-06: the kept start items and the start pieces, from their own stream
    start = start_state(settings, seed, canonical)
    encode_level_data = settings.is_on(ENCODE_LEVEL_DATA)
    if encode_level_data:
        level_encoding.require_available()
    return GenerationPlan(
        seed=seed,
        flag_string=canonical,
        settings=settings,
        # ASNB (docs/design/asnb.md section 4): Add L4 Sword = Level 2 adds level 2's item cellar
        shape_options=replace(shape_options(settings),
                              level_2_sword_cellar=zora_resolved.l4_sword is zora_flags.L4Sword.LEVEL_2,
                              do_not_segment_dungeons=zora_resolved.is_on("do_not_segment_dungeons")),
        steps=flag_steps(settings),
        alternatives=replace(alternative_values(settings), start_items=start.items,
                             start_triforce_pieces=start.triforce_pieces),
        post_shapes=True,                # every C02 value runs them (PS-VAN-01)
        config=GameConfig(
            hint_mode=HINT_STYLE_MODES[settings.option(HINT_STYLE)],
            features_b10=True,
            book_is_an_atlas=settings.is_on(BOOK_IS_AN_ATLAS),
            book_to_understand_npcs=settings.is_on(BOOK_TO_UNDERSTAND_NPCS),
            level_encoding=(LevelEncodingKey(seed, zora_flags.level_encoding_text(canonical, zora_game))
                            if encode_level_data else None),
            # a magical sword may lie in a dungeon room: "no item" becomes $0E (docs/zora-extras.md section 6)
            dungeon_nothing_code=(DungeonNothingCode.ZORA_REMAP if zora.randomize_magical_sword
                                  else DungeonNothingCode.VANILLA),
            progressive_items=zora.progressive_items,
            shop_items_in_pool=zora.shop_items_in_pool,
            potion_shop_in_pool=zora_resolved.is_on("shuffle_blue_potion"),
            owner_flags=tuple(name for name in zora_flags.THREE_STATE_FIELDS if zora_resolved.is_on(name)),
            level_9_entrance_sword=zora_resolved.level_9_entrance_sword,
            permanent_sword_beam=settings.is_on(PERMANENT_SWORD_BEAM),
            one_hit_knock_out=settings.is_on(ONE_HIT_KNOCK_OUT),
            river_bridges=settings.is_on(RIVER_BRIDGES),                  # FP-BRIDGE-01
            lost_woods_shortcut=settings.is_on(LOST_WOODS_SHORTCUT),      # FP-WOODS-01
            # FP-WOOD-02 and FP-WOOD-03
            bomb_upgrade_item=settings.option(WOODEN_SWORD_STATE) in BOMB_UPGRADE_STATES,
            wand_fights_ganon=settings.option(WOODEN_SWORD_STATE) == WoodenSwordState.SWORDLESS,
            recorder_to_unbeaten=settings.is_on(RECORDER_TO_UNBEATEN),             # OW-WARP-02
            book_explosion=settings.is_on(BOOK_EXPLOSION),                         # FP-BOOK-02's blast
            change_hidden_tiles=settings.is_on(CHANGE_HIDDEN_TILES),               # FP-VIS-01
            item_appearance=settings.option(ITEM_APPEARANCE),                      # FP-SPRITE-01
            item_sprites_key=(_flag_key(seed, canonical, ITEM_SPRITES_STREAM)
                              if settings.option(ITEM_APPEARANCE) else None),
            plain_dead_secrets=(settings.is_on(CHANGE_HIDDEN_TILES) and settings.option(OVERWORLD_QUEST)
                                in (OverworldQuest.FIRST_QUEST, OverworldQuest.SECOND_QUEST)),
            hide_dungeon_numbers=settings.is_on(HIDE_DUNGEON_NUMBERS),             # FP-LEVEL-02
            hidden_health=settings.is_on(HIDDEN_HEALTH),                           # FP-HIDE-01
            red_bubble_curse=settings.option(RED_BUBBLE),                          # FP-BUBL-01
            killable_drop_items=settings.is_on(KILLABLE_DROP_ITEMS),               # FP-KILL-01
            hidden_numbers=settings.is_on(HIDDEN_NUMBERS),                         # FP-NUM-01
            rupees_affect_speed=settings.is_on(RUPEES_AFFECT_SPEED),               # FP-RSPD-01
            prevent_clipping=settings.is_on(PREVENT_CLIPPING),                     # FP-CLIP-01
            important_item_drops=settings.is_on(IMPORTANT_ITEM_DROPS),             # PS-EDROP-01
            random_drop_rates=settings.is_on(RANDOM_DROP_RATE),                    # PS-EDROP-02
            enemy_drops_key=(_flag_key(seed, canonical, ENEMY_DROPS_STREAM)
                             if settings.is_on(IMPORTANT_ITEM_DROPS) or settings.is_on(RANDOM_DROP_RATE) else None),
            seed_number=seed,
        ),
        zora_flag_string=zora_canonical,
        zora_game_string=zora_game,
        zora=zora,
        zora_resolved=zora_resolved,
        notices=(*postponed_notices(adjusted),
                 *((ENCODE_LEVEL_DATA_RANDOM_NOTICE,) if level_encoding_read_as_off else ())),
    )


def decode_zora_flags(flag_string: str, zora_flag_string: str, adjusted: Settings) -> ZoraFlags:
    """The ZORA flags, refused (FlagsRefused, every reason) when the string does not decode or
    conflicts with the Z1R settings; never changed to fit."""
    try:
        zora = zora_flags.decode(zora_flag_string.strip())
    except ZoraFlagStringError as exc:
        raise FlagsRefused(flag_string, [f"ZORA flag string: {exc}"]) from exc
    reasons = zora_flags.validate(zora, adjusted)
    unproduced = zora_flags.unproduced_fields(zora)
    if unproduced:
        reasons.append("ZORA flags not produced yet: " + ", ".join(unproduced))
    if reasons:
        raise FlagsRefused(flag_string, reasons)
    return zora


def flag_steps(settings: Settings) -> FlagSteps:
    """FL-OFF-02 to FL-OFF-06: each flag-switched step runs unless its field holds its turn-off
    value (supported values only reach here)."""
    on = settings.is_on
    return FlagSteps(
        recorder_to_new_dungeons=on("B01"),
        shuffle_shop_items=on("B08"),
        extra_candles=on("B09"),
        shuffle_armos=on("B13"),
        move_wood_sword_cave=on("B02"),
        shuffle_take_any_road_caves=on("B04"),
        change_sword_hearts=on("B10"),
        change_money_making_game=on("B11"),
        change_bomb_upgrades=on("B12"),
        increase_bomb_capacity=on("B90"),
        shuffle_dungeon_drops=on("B15"),
        shuffle_dungeon_text=on("B19"),
        add_money_or_life_rooms=on("B22"),
        change_money_or_life_toll=on("B23"),
        shuffle_dungeon_palettes=on("B27"),
        shuffle_hungry_goriya=on("B28"),
        shuffle_bomb_upgraders=on("B29"),
        shuffle_overworld_monsters=on("B31"),
        shuffle_bosses=on("B34"),
        shuffle_monsters_between_levels=on("B36"),
        randomize_boss_groups=on("B40"),
        shuffle_enemy_groups=on("B42"),
        speed_up_text=on("B54"),
        shuffle_start_screen=settings.option(START_SCREEN) != StartScreen.NORMAL,
        change_most_enemy_hp=settings.option(ENEMY_HIT_POINTS) != HitPointChange.NORMAL,
        change_boss_hp=settings.option(BOSS_HIT_POINTS) != HitPointChange.NORMAL,
        exchange_rooms=settings.option(DUNGEON_ROOM_SHUFFLE) == DungeonRoomShuffle.FULL,
        remap_rooms=settings.option(DUNGEON_ROOM_SHUFFLE) != DungeonRoomShuffle.VANILLA,
    )


def alternative_values(settings: Settings) -> AlternativeValues:
    """FL-ALT-02 to FL-ALT-04: each alternative value's function runs when its field holds that
    value (supported values only reach here)."""
    quest = settings.option(OVERWORLD_QUEST)
    return AlternativeValues(
        starting_hearts=starting_hearts(settings),
        white_sword_hearts=_inclusive(*white_sword_hearts(settings)),
        generate_community_hint_text=settings.option(HINT_STYLE) == HintStyle.COMMUNITY,
        show_every_helpful_hint=settings.option(HINT_STYLE) == HintStyle.HELPFUL,
        normal_hints=settings.option(HINT_STYLE) == HintStyle.NORMAL,
        deception_hints=settings.option(HINT_STYLE) == HintStyle.DECEPTIVE,
        blank_hints=settings.option(HINT_STYLE) == HintStyle.BLANK,
        item_shuffle=ItemShuffleScope(settings.option(ITEM_SHUFFLE_SCOPE)),
        mix_overworld_quest=quest == OverworldQuest.MIXED_FIRST_QUEST_VARIANT,
        mix_overworld_quest_second_variant=quest == OverworldQuest.MIXED_SECOND_QUEST_VARIANT,
        second_quest_overworld=quest == OverworldQuest.SECOND_QUEST,
        full_start_shuffle=settings.option(START_SCREEN) == StartScreen.FULL_SHUFFLE,
        start_on_wood_sword_screen=settings.option(START_SCREEN) == StartScreen.WOODEN_SWORD_SCREEN,
        force_overworld_block=settings.is_on(FORCE_OVERWORLD_BLOCK),
        wood_sword_cave_behind_blocks=settings.is_on(WOOD_SWORD_CAVE_BEHIND_BLOCKS),
        dungeon_quest=DungeonLayoutSource(settings.option(DUNGEON_LAYOUT_SOURCE)),
        important_items_in_level_9=settings.is_on(IMPORTANT_ITEMS_IN_LEVEL_9),
        remove_most_open_stairs=settings.is_on(MOST_OPEN_STAIRS_REMOVED),
        book_to_understand_npcs=settings.is_on(BOOK_TO_UNDERSTAND_NPCS),
        cave_shuffle=CaveShuffle(settings.option(CAVE_SHUFFLE)),
        enemy_hit_points=enemy_hit_point_change(settings),
        boss_hit_points=boss_hit_point_change(settings),
        ganon_hit_points_zero=settings.is_on(GANON_HIT_POINTS_ZERO),
        maximum_boss_health=settings.is_on(MAXIMUM_BOSS_HEALTH),
        maximum_enemy_health=settings.is_on(MAXIMUM_ENEMY_HEALTH),
        armos_pin=settings.option(ARMOS_PIN),
        white_sword_pin=settings.option(WHITE_SWORD_CAVE_PIN),
        coast_pin=settings.option(COAST_PIN),
        level_9_pins=(settings.option(LEVEL_9_FIRST_PIN), settings.option(LEVEL_9_SECOND_PIN)),
        wooden_sword_state=WoodenSwordState(settings.option(WOODEN_SWORD_STATE)),
        level_9_entry=level_9_entry(settings),
        shuffle_level_9_monsters=settings.is_on(LEVEL_9_MONSTER_MOVES),
        shuffle_ganon_and_zelda=settings.is_on(GANON_AND_ZELDA_SHUFFLE),
        force_ganon_fight=settings.is_on(GANON_MUST_BE_BEATEN),
        shuffle_dungeon_monsters=settings.is_on(DUNGEON_MONSTER_SHUFFLE),
        shuffle_overworld_group=settings.is_on(OVERWORLD_GROUP_REDRAW),
    )


def level_9_entry(settings: Settings) -> Level9Entry:
    """C08 with what its draws read: the range only under C08 = 9 and 10 (FP-TRIF-04, FP-TRIF-05;
    inert otherwise, FL-ALT-06), the sword state only under C08 = 11 (FP-TRIF-06)."""
    requirement = settings.option(LEVEL_9_REQUIREMENT)
    entry = Level9Entry(requirement)
    if requirement in (Level9Requirement.RANDOM_COUNT_IN_RANGE, Level9Requirement.SPECIFIC_PIECES):
        entry = replace(entry, piece_range=piece_count_range(settings))
    if requirement == Level9Requirement.ITEM_INSTEAD_OF_PIECES:
        entry = replace(entry, wooden_sword_state=WoodenSwordState(settings.option(WOODEN_SWORD_STATE)))
    return entry


def _inclusive(lowest: int, highest: int) -> range:
    return range(lowest, highest + 1)


def shape_options(settings: Settings) -> ShapeOptions:
    """The shapes generator's options from their three-state fields."""
    return ShapeOptions(
        sort_shapes=not settings.is_on(DO_NOT_SORT_SHAPES),     # SH-NUM-04
        start_room_swap=settings.is_on(START_ROOM_MAY_MOVE),
        second_quest_doors=settings.is_on("B21"),
        second_quest_rooms=settings.is_on("B20"),
        second_quest_monsters=settings.is_on("B37"),
        universal_drops=settings.is_on(UNIVERSAL_DROPS_IN_SHAPES),     # SH-ROOM-16
    )


def generate_world(chosen: GenerationPlan, base_rom: bytes) -> tuple[GameWorld, GenerationResult]:
    """The generated world for a plan, on the player's base ROM (not yet serialized): either
    release, with or without modified graphics (revision.identify_rom; RomNotRecognized for
    any other). Both releases parse into the same world, so the generation never knows which."""
    from ..rom.base_rom import player_rom_of, remember_base_rom, using_player_rom
    from ..rom.parse.rom_file import parse_rom
    from .generation_pass import generate_shapes
    from .rng import Rng
    player = player_rom_of(base_rom)
    # The process's fallback for reading the finished ROM afterwards (the web page's seed
    # report parses it); this call itself reads only its own ROM.
    remember_base_rom(base_rom)
    with using_player_rom(player):
        world = parse_rom(base_rom)
        result = generate_shapes(world, Rng(chosen.generation_seed), chosen.shape_options,
                                 post_shapes=chosen.post_shapes, feature_data=chosen.config.features_b10,
                                 seed=chosen.seed, steps=chosen.steps, extras=extra_options(chosen),
                                 alternatives=chosen.alternatives)
    # the "no item" code the engine compares, the one the room bytes are written in
    world.dungeon_nothing_code = chosen.config.dungeon_nothing_code
    if chosen.encode_level_data:
        world.store_second_quest_sets_in_first_quest_slots()
    return world, result


def extra_options(chosen: GenerationPlan) -> ExtraOptions:
    """The ZORA extras' switches and the heart figures the magical sword's check needs."""
    from ..model.enums import Item
    return ExtraOptions(
        randomize_magical_sword=chosen.zora.randomize_magical_sword,
        randomize_letter=chosen.zora.randomize_letter,
        magical_sword_hearts=zora_flags.magical_sword_heart_range(chosen.zora, chosen.settings),
        starting_heart_containers=zora_flags.starting_heart_containers(chosen.settings),
        progressive_items=chosen.zora.progressive_items,
        shop_items_in_pool=chosen.zora.shop_items_in_pool,
        gates=overworld_gates(chosen.zora_resolved, chosen.settings),
        shuffle_blue_potion=chosen.zora_resolved.is_on("shuffle_blue_potion"),
        add_l4_sword=chosen.zora_resolved.is_on("add_l4_sword"),
        l4_sword_in_level_2=chosen.zora_resolved.l4_sword is zora_flags.L4Sword.LEVEL_2,
        level_9_entrance_sword=chosen.zora_resolved.level_9_entrance_sword,
        eleven_screen_recorder_set=chosen.alternatives.second_quest_secrets,
        important_items_in_level_9=chosen.alternatives.important_items_in_level_9,
        wooden_sword_state=chosen.alternatives.wooden_sword_state,
        maze_hints_need_book=(chosen.alternatives.book_to_understand_npcs
                              and Item.BOOK not in chosen.alternatives.start_items),
        oops_all_enemies=chosen.zora_resolved.oops_all_enemies,
        oops_all_bosses=chosen.zora_resolved.oops_all_bosses,
        oops_all_seed=zora_flags.oops_all_seed(chosen.seed, chosen.flag_string, chosen.zora_game_string),
        allow_triforces_in_stairways=chosen.zora_resolved.is_on("allow_triforces_in_stairways"),
        shuffle_wood_sword=chosen.zora_resolved.is_on("shuffle_wood_sword"),
        pegasus_boots=chosen.zora_resolved.is_on("pegasus_boots"),
        expanded_dungeon_locations=chosen.zora_resolved.is_on("expanded_dungeon_locations"),
        expanded_dungeon_locations_seed=expanded_dungeon_locations_seed(chosen.seed, chosen.flag_string,
                                                                        chosen.zora_game_string),
        highlight_no_drop_rooms=chosen.zora_resolved.is_on("highlight_no_drop_rooms"),
        gatekeeper_bosses=chosen.zora_resolved.gatekeeper_bosses,
    )


def shipped_logic_rules(chosen: GenerationPlan, world: GameWorld) -> LogicRules:
    """The rules a shipped seed was judged by: the ZORA extras', with the level-9 gate its accepted
    attempt asked for (C08; FP-TRIF-02 to FP-TRIF-06 draw it in each attempt)."""
    return replace(extra_options(chosen).logic_rules, level_9_gate=world.level_9_gate)


def overworld_gates(zora: ZoraFlags, settings: Settings) -> OverworldGates:
    """The owner's 2.0 overworld gates a seed's resolved ZORA flags turn on, and whether its
    resolved Z1R settings open the river's west side (B87 or B88, FP-BRIDGE-01, FP-WOODS-01)."""
    return OverworldGates(raft_blocks=zora.is_on("extra_raft_blocks"),
                          bracelet_blocks=zora.is_on("extra_power_bracelet_blocks"),
                          lost_hills=zora.is_on("randomize_lost_hills"),
                          dead_woods=zora.is_on("randomize_dead_woods"),
                          river_west_open=settings.is_on(RIVER_BRIDGES) or settings.is_on(LOST_WOODS_SHORTCUT))


@dataclass
class Built:
    """BUILD's output (Archipelago Phase 2; docs/archipelago.md): a whole ZORA generation, every
    step run and the attempt shipped, before serialization; with the places its items sit in,
    read from the finished world (places.all_item_places)."""
    plan: GenerationPlan
    world: GameWorld
    result: GenerationResult
    places: list[Place]
    # The player's base ROM it was built on, which FINISH writes over (Archipelago keeps one
    # Built per player, each with its own ROM and release).
    base_rom: bytes = b""


def build(chosen: GenerationPlan, base_rom: bytes) -> Built:
    """BUILD: generate_world, unchanged, and the item places of the world it made."""
    from .places import all_item_places
    world, result = generate_world(chosen, base_rom)
    return Built(chosen, world, result, all_item_places(world, extra_options(chosen)), base_rom)


def finish(built: Built, base_rom: bytes, assignment: Assignment | None = None,
           player_settings: PlayerSettings = DEFAULT_PLAYER_SETTINGS, recompute: bool = True,
           received: Collection[Item] = (), check: bool = True, slot_identity: bytes = b"",
           look: ForeignLook | None = None) -> bytes:
    """FINISH: the built world as a ROM. With no assignment (ZORA mode) it is serialize_to_rom on
    the built world, which only reads it, so one build can be finished more than once. With one
    (External mode) the items go into a copy of the world first (finish_world); `slot_identity`
    is Archipelago's record for the slot (zora/rom/slot_identity.py), written only with one;
    `look`, how another player's item looks (finish.ForeignLook; the rupee by default)."""
    from ..rom.base_rom import player_rom_of, using_player_rom
    from ..rom.serialize.rom_file import serialize_to_rom
    if assignment is None:
        assert not slot_identity, "a slot identity is External mode's"
        return serialize_to_rom(built.world, base_rom, config=built.plan.config, player_settings=player_settings)
    with using_player_rom(player_rom_of(base_rom)):
        world, finished = finish_world(built, assignment, recompute, received, check, look)
    config = replace(finished.config, slot_identity=slot_identity, archipelago_rom=True, seed_number=None)
    return serialize_to_rom(world, base_rom, config=config, player_settings=player_settings)


def finish_world(built: Built, assignment: Assignment, recompute: bool = True, received: Collection[Item] = (),
                 check: bool = True, look: ForeignLook | None = None) -> tuple[GameWorld, Finished]:
    """External mode before serialization: a deep copy of the built world with the assignment
    applied (finish.apply_assignment, which also takes `received` and `check`), on FINISH's own
    stream; the built world is left as it is."""
    from .finish import ForeignLook, apply_assignment, finish_rng
    world = copy.deepcopy(built.world)
    finished = apply_assignment(world, built, assignment, finish_rng(built.plan.generation_seed), recompute,
                                received, check, look or ForeignLook.RUPEE)
    return world, finished


def generate_rom(flag_string: str, seed: int, base_rom: bytes,
                 player_settings: PlayerSettings = DEFAULT_PLAYER_SETTINGS, zora_flag_string: str = "") -> GeneratedRom:
    """One finished ROM for a flag string, a ZORA flag string and a seed, on
    the player's base ROM, with the player settings applied last (FP-SET-01: after
    the level encoding and the seed's code, which they never change):
    BUILD, then FINISH with no assignment (ZORA mode). Disable Custom Music on refuses a random
    Music value (PlayerSettingError)."""
    from ..rom.code_patches import seed_code
    chosen = plan(flag_string, seed, zora_flag_string)
    check_music_allowed(player_settings, chosen.zora.disable_custom_music)
    rom = finish(build(chosen, base_rom), base_rom, None, player_settings)
    return GeneratedRom(rom, seed, chosen.flag_string, chosen.encode_level_data, seed_code(rom),
                        chosen.zora_flag_string)
