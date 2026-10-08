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

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from zora.flags import zora_flags
from zora.flags.codec import FlagStringError, decode, encode
from zora.flags.dependencies import (
    apply_dependencies,
    check_dependencies,
    correct_merchant_toll,
    generation_settings,
    is_resolved,
    resolve,
)
from zora.flags.fields import (
    BOSS_HIT_POINTS,
    DUNGEON_LAYOUT_SOURCE,
    DUNGEON_ROOM_SHUFFLE,
    ENCODE_LEVEL_DATA,
    ENEMY_HIT_POINTS,
    FOUR_STARTING_HEARTS,
    HINT_STYLE,
    OPTIONS_BY_ID,
    START_SCREEN,
    STARTING_HEARTS,
    TOGGLES_BY_ID,
    WHITE_SWORD_FROM_FIVE_HEARTS,
    WHITE_SWORD_LOWEST,
    DungeonLayoutSource,
    DungeonRoomShuffle,
    HintStyle,
    HitPointChange,
    Settings,
    StartScreen,
    ThreeState,
)
from zora.flags.support import ENCODE_LEVEL_DATA_NOT_RANDOM, encode_level_data_is_random, unsupported_fields
from zora.flags.zora_flags import ZoraFlags, ZoraFlagStringError
from zora.generate.alternative_values import AlternativeValues
from zora.generate.extra_options import ExtraOptions
from zora.generate.flag_steps import FlagSteps
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.generate.steps.overworld_gates import OverworldGates
from zora.rom import level_encoding
from zora.rom.game_config import DungeonNothingCode, GameConfig, HintMode, LevelEncodingKey
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS, PlayerSettings

if TYPE_CHECKING:
    from zora.generate.context import GenerationResult
    from zora.model.game_world import GameWorld

# C03 (hint style): mixed (index 4) and community (index 2, FL-ALT-04) both write the generated
# 45-slot block; only its generation differs (generate_community_hint_text). The level-9 and
# triforce texts depend only on whether hints are normal (FL-ALT-04), so they are the same.
HINT_STYLE_MODES: dict[int, HintMode] = {
    HintStyle.MIXED: HintMode.CONSTERNATION,
    HintStyle.COMMUNITY: HintMode.CONSTERNATION,
}
# The start of the refusal that names the fields the support matrix does not produce.
NOT_PRODUCED_PREFIX = "not produced: "
# Book is an Atlas: a code patch, so the serializer's switch (GameConfig).
BOOK_IS_AN_ATLAS = TOGGLES_BY_ID["B49"]
# The "?" stream's key: the seed number as eight bytes, and its own label.
SEED_BYTES = 8
QUESTION_MARK_STREAM = b"zora ? values"
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
    post_shapes: bool                # the post-shapes passes (C02 generated shapes)
    config: GameConfig
    zora_flag_string: str = ""       # canonical; empty: every ZORA flag off
    zora: ZoraFlags = zora_flags.DEFAULT     # the decoded ZORA flags, "?" values as asked
    # The ZORA flags as the generator sees them: version-3 "?" values decided from their own stream
    # and the owner's dependencies applied (zora_flags.resolve_owner_dependencies). Never shown.
    zora_resolved: ZoraFlags = zora_flags.DEFAULT

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
        return zora_flags.generation_seed(seed, self.flag_string, self.zora_flag_string)


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


def question_mark_rng(seed: int, flag_string: str) -> Rng:
    """The stream that resolves "?" values (FL-DEP-04): derived only from the seed number and the
    canonical flag string, and separate from the generation's stream, whose draws it leaves
    untouched."""
    key = hashlib.blake2b(flag_string.encode("utf-8"), key=seed.to_bytes(SEED_BYTES, "little"),
                          digest_size=SEED_BYTES, person=QUESTION_MARK_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def resolve_question_marks(settings: Settings, seed: int, flag_string: str) -> Settings:
    """FL-DEP-04: each "?" decided for this seed, a possible field by a fair coin and a random
    index uniformly among its alternatives; then FL-DEP-06 again (a merchant coin that comes up
    off takes the toll re-draw with it). The resolved values are never shown or returned."""
    if is_resolved(settings):
        return settings
    return correct_merchant_toll(resolve(settings, question_mark_rng(seed, flag_string)))


def plan(flag_string: str, seed: int, zora_flag_string: str = "") -> GenerationPlan:
    """Decode and vet a flag string and a ZORA flag string; raise FlagsRefused or
    LevelEncodingUnavailable rather than generate something else; an out-of-range seed raises
    SeedRefused before anything is decoded."""
    if not 0 <= seed < SEED_LIMIT:
        raise SeedRefused(seed)
    try:
        decoded = correct_merchant_toll(decode(flag_string))         # FL-DEP-06
    except FlagStringError as exc:
        raise FlagsRefused(flag_string, [str(exc)]) from exc
    refused = check_dependencies(decoded)
    if refused:
        raise FlagsRefused(flag_string, [f"{r.rule}: {r.message}" for r in refused])
    adjusted = apply_dependencies(decoded)
    reasons = [ENCODE_LEVEL_DATA_NOT_RANDOM] if encode_level_data_is_random(adjusted) else []
    unsupported = [field_id for field_id in unsupported_fields(adjusted) if field_id != ENCODE_LEVEL_DATA.id]
    if unsupported:
        reasons.append(NOT_PRODUCED_PREFIX + ", ".join(_unsupported_name(adjusted, field_id)
                                                       for field_id in unsupported))
    if reasons:
        raise FlagsRefused(flag_string, reasons)
    canonical = encode(adjusted)
    zora = decode_zora_flags(flag_string, zora_flag_string, adjusted)
    zora_canonical = zora_flags.encode(zora)
    resolved = zora_flags.without_extra_candles(zora, resolve_question_marks(adjusted, seed, canonical), adjusted)
    zora_resolved, resolved = zora_flags.resolve_owner_dependencies(
        zora_flags.resolve_question_marks(zora, seed, canonical, zora_canonical), zora, resolved, adjusted)
    settings = generation_settings(resolved)
    encode_level_data = settings.is_on(ENCODE_LEVEL_DATA)
    if encode_level_data:
        level_encoding.require_available()
    return GenerationPlan(
        seed=seed,
        flag_string=canonical,
        settings=settings,
        shape_options=shape_options(settings),
        steps=flag_steps(settings),
        alternatives=alternative_values(settings),
        post_shapes=settings.option(DUNGEON_LAYOUT_SOURCE) == DungeonLayoutSource.GENERATED_SHAPES,
        config=GameConfig(
            hint_mode=HINT_STYLE_MODES[settings.option(HINT_STYLE)],
            features_b10=True,
            book_is_an_atlas=settings.is_on(BOOK_IS_AN_ATLAS),
            level_encoding=(LevelEncodingKey(seed, zora_flags.level_encoding_text(canonical, zora_canonical))
                            if encode_level_data else None),
            # a magical sword may lie in a dungeon room: "no item" becomes $0E (docs/zora-extras.md section 6)
            dungeon_nothing_code=(DungeonNothingCode.ZORA_REMAP if zora.randomize_magical_sword
                                  else DungeonNothingCode.VANILLA),
            progressive_items=zora.progressive_items,
            shop_items_in_pool=zora.shop_items_in_pool,
            potion_shop_in_pool=zora_resolved.is_on("shuffle_blue_potion"),
            owner_flags=tuple(name for name in zora_flags.OWNER_2_0_FIELDS if zora_resolved.is_on(name)),
        ),
        zora_flag_string=zora_canonical,
        zora=zora,
        zora_resolved=zora_resolved,
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
        shuffle_take_any_road_caves=on("B04"),
        change_sword_hearts=on("B10"),
        change_money_making_game=on("B11"),
        change_bomb_upgrades=on("B12"),
        shuffle_dungeon_drops=on("B15"),
        shuffle_dungeon_text=on("B19"),
        add_money_or_life_rooms=on("B22"),
        change_money_or_life_toll=on("B23"),
        shuffle_dungeon_palettes=on("B27"),
        shuffle_hungry_goriya=on("B28"),
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
    )


def alternative_values(settings: Settings) -> AlternativeValues:
    """FL-ALT-02 to FL-ALT-04: each alternative value's function runs when its field holds that
    value (supported values only reach here)."""
    return AlternativeValues(
        start_with_four_hearts=settings.option(STARTING_HEARTS) == FOUR_STARTING_HEARTS,
        change_sword_hearts_from_five_hearts=settings.option(WHITE_SWORD_LOWEST) == WHITE_SWORD_FROM_FIVE_HEARTS,
        generate_community_hint_text=settings.option(HINT_STYLE) == HintStyle.COMMUNITY,
    )


def shape_options(settings: Settings) -> ShapeOptions:
    """The shapes generator's options from their three-state fields."""
    return ShapeOptions(
        sort_shapes=not settings.is_on("B86"),
        start_room_swap=settings.is_on("B26"),
        second_quest_doors=settings.is_on("B21"),
        second_quest_rooms=settings.is_on("B20"),
        second_quest_monsters=settings.is_on("B37"),
        universal_drops=settings.is_on("B91"),
    )


def generate_world(chosen: GenerationPlan, base_rom: bytes) -> tuple[GameWorld, GenerationResult]:
    """The generated world for a plan, on the PRG0 base (not yet serialized)."""
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.rng import Rng
    from zora.rom.parse.rom_file import parse_rom
    world = parse_rom(base_rom)
    result = generate_shapes(world, Rng(chosen.generation_seed), chosen.shape_options, post_shapes=chosen.post_shapes,
                             feature_data=chosen.config.features_b10, seed=chosen.seed, steps=chosen.steps,
                             extras=extra_options(chosen), alternatives=chosen.alternatives)
    return world, result


def extra_options(chosen: GenerationPlan) -> ExtraOptions:
    """The ZORA extras' switches and the heart figures the magical sword's check needs."""
    return ExtraOptions(
        randomize_magical_sword=chosen.zora.randomize_magical_sword,
        randomize_letter=chosen.zora.randomize_letter,
        magical_sword_hearts=zora_flags.magical_sword_heart_range(chosen.zora, chosen.settings),
        starting_heart_containers=zora_flags.starting_heart_containers(chosen.settings),
        progressive_items=chosen.zora.progressive_items,
        shop_items_in_pool=chosen.zora.shop_items_in_pool,
        gates=overworld_gates(chosen.zora_resolved),
        shuffle_blue_potion=chosen.zora_resolved.is_on("shuffle_blue_potion"),
        add_l4_sword=chosen.zora_resolved.is_on("add_l4_sword"),
    )


def overworld_gates(zora: ZoraFlags) -> OverworldGates:
    """The owner's 2.0 overworld gates a seed's resolved ZORA flags turn on."""
    return OverworldGates(raft_blocks=zora.is_on("extra_raft_blocks"),
                          bracelet_blocks=zora.is_on("extra_power_bracelet_blocks"),
                          lost_hills=zora.is_on("randomize_lost_hills"),
                          dead_woods=zora.is_on("randomize_dead_woods"))


def generate_rom(flag_string: str, seed: int, base_rom: bytes,
                 player_settings: PlayerSettings = DEFAULT_PLAYER_SETTINGS, zora_flag_string: str = "") -> GeneratedRom:
    """One finished ROM for a flag string, a ZORA flag string and a seed, on
    the PRG0 base, with the player settings applied last (FP-SET-01: after
    the level encoding and the seed's code, which they never change)."""
    from zora.rom.code_patches import seed_code
    from zora.rom.serialize.rom_file import serialize_to_rom
    chosen = plan(flag_string, seed, zora_flag_string)
    world, _ = generate_world(chosen, base_rom)
    rom = serialize_to_rom(world, base_rom, config=chosen.config, player_settings=player_settings)
    return GeneratedRom(rom, seed, chosen.flag_string, chosen.encode_level_data, seed_code(rom),
                        chosen.zora_flag_string)
