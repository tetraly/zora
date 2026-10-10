"""Pre-tester QA sweep: random supported configurations, fixed cases, refusals.

    python3 scripts/qa_sweep.py random --start K --count N [--workers W]
    python3 scripts/qa_sweep.py fixed --seeds N [--workers W]
    python3 scripts/qa_sweep.py alternatives --seeds N [--workers W]
    python3 scripts/qa_sweep.py emulator --count N [--workers W]
    python3 scripts/qa_sweep.py refusals --count N

`random` draws configuration K, K+1, ... (each from its own index, so a run
splits into chunks that add up to the same sweep). A configuration is a Z1R
flag string with every field at its MVP baseline, a supported turn-off value,
a supported alternative value or a supported "?" (FL-SUP-01 to -03,
FL-OFF-07, FL-ALT-02 to -04; level encoding off or on), a ZORA string
(empty, 1.2, or the magical sword: 1.D, 1.F; then Progressive Items and Shop
Items in the Item Pool each on by a coin), random player settings in the
page's own form, and one seed. `fixed` runs the
baseline and the all-turn-offs strings under every ZORA string and level
encoding choice, N seeds each. `alternatives` runs FL-ALT's Checks: CP-5, each
alternative value alone on CP-5 and the three together, with the ZORA extras
off and with Randomize Magical Sword and Randomize Letter on (1.F), N seeds
each, and judges each batch's FL-ALT figures against the spec's; --start and
--count split it into chunks, best at multiples of N.

Each seed must: generate without error; pass the acceptance check
(acceptance.md, re-run on the shipped world) and Randomize Magical Sword's
heart check; pass the finished-ROM checks; survive parse and re-serialize
byte for byte (an encoded ROM: its plain build does, and its level data
decodes to that build's); carry the seed code (FP-HASH-01) that hashes the
ROM before player settings; differ from that ROM only by the player
settings; and return the page no resolved "?" value and no changed flag
apart from FL-DEP-06's B23 correction.

`emulator` boots the first N random configurations' ROMs (cynes, through
tests/emulator.py): file select, register a file, start, walk one screen.
`refusals` builds N unsupported or conflicting inputs and checks each is
refused with a message naming its cause, never a crash or a silent change.

Prints a summary and every failure; exit status 1 on any failure.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora_web.api import (  # noqa: E402
    PAGE_BOSS_SOUND_WORD, PAGE_CHOICES, PAGE_HEART_SLOT, PAGE_LEVEL_WORD, PAGE_TUNIC_SLOTS, player_settings_from_page,
)
from zora.flags import zora_flags  # noqa: E402
from zora.flags.codec import decode, encode  # noqa: E402
from zora.flags.dependencies import check_dependencies, correct_merchant_toll  # noqa: E402
from zora.flags.fields import (  # noqa: E402
    ENCODE_LEVEL_DATA, MONEY_OR_LIFE_ROOMS, MONEY_OR_LIFE_TOLL, OPTION_FIELDS, OPTIONS_BY_ID, TOGGLE_FIELDS,
    Settings, ThreeState, WoodenSwordState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF  # noqa: E402
from zora.flags.zora_flags import L4Sword  # noqa: E402
from zora.flags.support import (  # noqa: E402
    ALTERNATIVE_OPTIONS, TURN_OFF_OPTIONS, TURN_OFF_TOGGLES, Support, mvp_baseline_settings, support,
)
from zora.generate.acceptance_check import acceptance_check  # noqa: E402
from zora.generate.generation_pass import has_magical_sword_hearts  # noqa: E402
from zora.generate.context import GenerationResult  # noqa: E402
from zora.generate.pipeline import (  # noqa: E402
    FlagsRefused, GeneratedRom, GenerationPlan, SeedRefused, extra_options, generate_rom, generate_world,
    overworld_gates, plan,
)
from zora.generate.steps.cave_entries import OverworldResult  # noqa: E402
from zora_measure.alternative_values import HELPFUL_TEXT_SLOTS, alternative_value_figures  # noqa: E402
from zora_measure.checks import finished_rom_checks, run_checks  # noqa: E402
from zora_measure.owner_flags import owner_flag_problems  # noqa: E402
from zora.model.game_world import GameWorld  # noqa: E402
from zora.rom import level_encoding  # noqa: E402
from zora.rom.base_rom import verify_base_rom  # noqa: E402
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_ITEMS, SEED_CODE_LENGTH, seed_code  # noqa: E402
from zora.rom.game_config import GameConfig  # noqa: E402
from zora.rom.parse.rom_file import parse_rom  # noqa: E402
from zora.rom.player_settings import (  # noqa: E402
    BLACKER_THAN_BLACK, BOSS_SOUND_WORDS, LEVEL_WORD_CHOICES, PALETTE_SIZE, RANDOM_BOSS_SOUND_WORD,
    PlayerSettingError, apply_player_settings,
)
from zora.rom.serialize.rom_file import serialize_to_rom  # noqa: E402

SWEEP_KEY = "zora qa sweep"
# The ZORA strings: every flag off; Randomize Letter; Randomize Magical Sword (heart cap 12)
# without and with the letter. The sword needs a cap of 12 or B10 off (zora_flags.validate).
ZORA_STRINGS = ("", "1.2", "1.D", "1.F")
# Encode level data (B82) is on or off, never "?" (owner ruling, 2026-10-06). Without the
# level-encoding module (zora/rom/level_encoding.py) only off can be built, so only off is drawn.
ENCODING_CHOICES = (ThreeState.OFF, ThreeState.ON) if level_encoding.is_available() else (ThreeState.OFF,)
PALETTE_COLOURS = tuple(colour for colour in range(PALETTE_SIZE) if colour != BLACKER_THAN_BLACK)
SEED_LIMIT = 1 << 64
# The exceptions that refuse input with a message for the player.
REFUSALS = (FlagsRefused, PlayerSettingError, SeedRefused)


@cache
def base_rom() -> bytes:
    return verify_base_rom().read_bytes()


# ---------------------------------------------------------------------------
# Drawing supported configurations
# ---------------------------------------------------------------------------

def _supported(settings: Settings, field_id: str) -> bool:
    return support(settings)[field_id] is Support.SUPPORTED


def supported_choices(field_id: str, settings: Settings) -> dict[str, list[Any]]:
    """A field's supported values given the other fields, grouped: the baseline, the turn-off
    values, the alternative values and "?" (the possible state, or an option's random index)."""
    baseline = mvp_baseline_settings()
    groups: dict[str, list[Any]]
    if field_id in OPTIONS_BY_ID:
        option = OPTIONS_BY_ID[field_id]
        turn_offs = sorted(index for index in TURN_OFF_OPTIONS.get(field_id, ()) if not option.is_random(index))
        alternatives = sorted(ALTERNATIVE_OPTIONS.get(field_id, ()))
        randoms = [index for index in option.random_choices
                   if _supported(settings.updated(options={field_id: index}), field_id)]
        groups = {"baseline": [baseline.option(field_id)], "turn-off": turn_offs, "alternative": alternatives,
                  "?": randoms}
    else:
        values = [state for state in (ThreeState.OFF, ThreeState.ON)
                  if state != baseline.toggle(field_id)
                  and _supported(settings.updated(toggles={field_id: state}), field_id)]
        possible = [ThreeState.POSSIBLE] if _supported(
            settings.updated(toggles={field_id: ThreeState.POSSIBLE}), field_id) else []
        groups = {"baseline": [baseline.toggle(field_id)], "turn-off": values, "?": possible}
    return {name: values for name, values in groups.items() if values}


def draw_settings(rng: random.Random) -> Settings:
    """Every selectable field (FL-OFF-07, FL-ALT-02 to -04 and B82) at its baseline, a turn-off
    value, an alternative value or a "?", the group drawn first so C17's many turn-off values do
    not crowd out the rest; B82 on or off (never "?"). B22 is drawn before B23, whose off needs
    it (FL-DEP-06)."""
    settings = mvp_baseline_settings()
    selectable = [*TURN_OFF_OPTIONS, *ALTERNATIVE_OPTIONS, *TURN_OFF_TOGGLES]
    selectable.sort(key=lambda field_id: field_id == MONEY_OR_LIFE_TOLL.id)
    for field_id in selectable:
        groups = supported_choices(field_id, settings)
        value = rng.choice(groups[rng.choice(sorted(groups))])
        settings = (settings.updated(options={field_id: value}) if field_id in OPTIONS_BY_ID
                    else settings.updated(toggles={field_id: value}))
    return settings.updated(toggles={ENCODE_LEVEL_DATA.id: rng.choice(ENCODING_CHOICES)})


def draw_page_settings(rng: random.Random) -> dict[str, Any]:
    """Player settings as the page sends them: every choice key, colour slot and both words."""
    values: dict[str, Any] = {key: rng.choice(sorted(choices)) for key, (_, choices) in PAGE_CHOICES.items()}
    for slot in (*PAGE_TUNIC_SLOTS, PAGE_HEART_SLOT):
        values[slot] = rng.choice(PALETTE_COLOURS)
    values[PAGE_LEVEL_WORD] = rng.choice(LEVEL_WORD_CHOICES)
    values[PAGE_BOSS_SOUND_WORD] = rng.choice([RANDOM_BOSS_SOUND_WORD, *BOSS_SOUND_WORDS])
    return values


@dataclass(frozen=True)
class Config:
    label: str
    flag_string: str
    zora_flag_string: str
    page_settings: dict[str, Any]
    seed: int


def draw_zora_string(rng: random.Random, settings: Settings | None = None) -> str:
    """One of ZORA_STRINGS, with Progressive Items and Shop Items in the Item Pool each on by a
    coin (version 2; Progressive Items with B09 on is refused, PI-FLAG-03), then each produced
    version-3 flag (the owner's 2.0 flags) off, on or "?" by thirds. Extra Power Bracelet Blocks
    is not drawn on with B04 on, which refuses it (a "?" with B04 on is drawn: it resolves off), nor
    Add L4 Sword on without Progressive Items (likewise); Add L4 Sword on draws its place
    (draw_l4_sword_place)."""
    flags = zora_flags.decode(rng.choice(ZORA_STRINGS))
    flags = replace(flags, progressive_items=rng.random() < 0.5, shop_items_in_pool=rng.random() < 0.5)
    owner = {name: rng.choice(list(ThreeState)) for name in zora_flags.OWNER_2_0_FIELDS
             if name in zora_flags.PRODUCED_OWNER_FIELDS}
    if settings is not None and settings.toggle(zora_flags.TAKE_ANY_ROAD_CAVES) is ThreeState.ON \
            and owner.get("extra_power_bracelet_blocks") is ThreeState.ON:
        owner["extra_power_bracelet_blocks"] = ThreeState.POSSIBLE
    if not flags.progressive_items and owner.get("add_l4_sword") is ThreeState.ON:
        owner["add_l4_sword"] = ThreeState.POSSIBLE         # needs Progressive Items; a "?" resolves off
    asnb: dict[str, bool] = {}
    if owner.get("add_l4_sword") is ThreeState.ON:
        asnb = draw_l4_sword_place(rng, settings)
    return zora_flags.encode(replace(flags, **owner, **asnb))  # type: ignore[arg-type]


def draw_l4_sword_place(rng: random.Random, settings: Settings | None) -> dict[str, bool]:
    """Add L4 Sword drawn on (ASNB, docs/design/asnb.md section 1): Level 9 or Level 2 by a coin
    (Level 9 without generated shapes), and Level 2 takes the level-4-sword entrance by a coin when
    the wooden sword is in its cave. A "?" keeps the released meaning (Off or Level 9, decided per
    seed), which the Level 2 field and the entrance never take. Drawn after every other draw of the
    string, so a configuration without Add L4 Sword on is unchanged."""
    level_2 = rng.random() < 0.5
    if not level_2 or settings is None \
            or settings.option(zora_flags.DUNGEON_LAYOUT_SOURCE) != zora_flags.SHAPES_ONLY:
        return {}
    entrance = (settings.option(zora_flags.WOODEN_SWORD_STATE) == WoodenSwordState.NORMAL
                and rng.random() < 0.5)
    return {"l4_sword_in_level_2": True, "level_9_entrance_sword": entrance}


def random_config(index: int) -> Config:
    rng = random.Random(f"{SWEEP_KEY}:{index}")
    settings = draw_settings(rng)
    return Config(f"random {index}", encode(settings), draw_zora_string(rng, settings),
                  draw_page_settings(rng), rng.randrange(SEED_LIMIT) if rng.random() < 0.5 else rng.randrange(1, 1001))


def all_turn_offs() -> Settings:
    """FL-OFF-01's string: every FL-OFF-07 field at a turn-off value (C17 at 0)."""
    return mvp_baseline_settings().updated(
        toggles=dict.fromkeys(TURN_OFF_TOGGLES, ThreeState.OFF),
        options={field_id: min(values) for field_id, values in TURN_OFF_OPTIONS.items()})


def fixed_configs(seeds: int) -> Iterator[Config]:
    for name, settings in (("baseline", mvp_baseline_settings()), ("all turn-offs", all_turn_offs())):
        for encoding in ENCODING_CHOICES:
            flags = encode(settings.updated(toggles={ENCODE_LEVEL_DATA.id: encoding}))
            for zora in ZORA_STRINGS:
                rng = random.Random(f"{SWEEP_KEY}:{name}:{encoding.name}:{zora}")
                for seed in range(1, seeds + 1):
                    yield Config(f"{name} B82={encoding.name} zora={zora or '-'}", flags, zora,
                                 draw_page_settings(rng), seed)


# FL-ALT's batches: CP-5 (the control), each alternative value alone on it, and the three together.
ALTERNATIVE_BATCHES: dict[str, dict[str, int]] = {
    "control": {},
    **{f"{field_id} = {value}": {field_id: value}
       for field_id, values in ALTERNATIVE_OPTIONS.items() for value in sorted(values)},
    "all three": {field_id: min(values) for field_id, values in ALTERNATIVE_OPTIONS.items()},
}
# The ZORA strings of those batches: the extras off, and Randomize Magical Sword (cap 12) with
# Randomize Letter, whose heart check counts the starting hearts and the white-sword requirement.
ALTERNATIVE_ZORA_STRINGS = ("", "1.F")


def alternative_configs(seeds: int) -> Iterator[Config]:
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    for zora in ALTERNATIVE_ZORA_STRINGS:
        for name, options in ALTERNATIVE_BATCHES.items():
            flags = encode(cp5.updated(options=options))
            for seed in range(1, seeds + 1):
                yield Config(f"{name} zora={zora or '-'}", flags, zora, {}, seed)


# The progressive items' batches (docs/design/progressive-items-plan.md section 9): each flag
# alone and both, plain, with the ZORA extras (sword at cap 12 and letter) and with the TTP4
# values, on CP-5 with B09 off (Progressive Items refuses it, PI-FLAG-03).
PROGRESSIVE_FLAGS: dict[str, dict[str, bool]] = {
    "progressive": {"progressive_items": True},
    "shop pool": {"shop_items_in_pool": True},
    "both": {"progressive_items": True, "shop_items_in_pool": True},
}
PROGRESSIVE_COMPANIONS: dict[str, tuple[dict[str, Any], dict[str, int]]] = {
    "plain": ({}, {}),
    "extras": ({"randomize_magical_sword": True, "randomize_letter": True, "magical_sword_hearts_highest": 12}, {}),
    "TTP4": ({}, {field_id: min(values) for field_id, values in ALTERNATIVE_OPTIONS.items()}),
}


def progressive_configs(seeds: int) -> Iterator[Config]:
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF})
    for name, flags in PROGRESSIVE_FLAGS.items():
        for companion, (extras, options) in PROGRESSIVE_COMPANIONS.items():
            zora = zora_flags.encode(zora_flags.ZoraFlags(**flags, **extras))  # type: ignore[arg-type]
            for seed in range(1, seeds + 1):
                yield Config(f"{name} {companion}", encode(cp5.updated(options=options)), zora, {}, seed)


# ---------------------------------------------------------------------------
# Checking one seed
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    config: Config
    failures: list[str] = field(default_factory=list)
    expected_refusal: str | None = None     # a ZORA string the Z1R settings do not allow
    encoded: bool = False
    rom: bytes | None = None


def expected_seed_code(rom: bytes) -> bytes:
    """FP-HASH-01, recomputed: SHA-256 of the ROM with the code bytes zeroed."""
    image = bytearray(rom)
    image[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = bytes(SEED_CODE_LENGTH)
    digest = hashlib.sha256(image).digest()
    return bytes(SEED_CODE_ITEMS[byte % len(SEED_CODE_ITEMS)] for byte in digest[:SEED_CODE_LENGTH])


def reading_config(config: GameConfig) -> GameConfig:
    """What parsing a finished ROM needs to know: the "no item" code (the magical sword's $0E
    remap) and the hint mode; nothing that runs a final step again."""
    return GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode)


def round_trips(rom: bytes, config: GameConfig) -> bool:
    return serialize_to_rom(parse_rom(rom, config), rom, config) == rom


def check_config(config: Config, keep_rom: bool = False) -> Outcome:
    outcome = Outcome(config)
    try:
        _check(config, outcome, keep_rom)
    except Exception as exc:  # a crash is a finding, not the end of the sweep
        outcome.failures.append(f"crash: {type(exc).__name__}: {exc}")
    return outcome


def _check(config: Config, outcome: Outcome, keep_rom: bool) -> None:
    fail = outcome.failures.append
    asked = correct_merchant_toll(decode(config.flag_string))         # FL-DEP-06, never refused
    zora_reasons = zora_flags.validate(zora_flags.decode(config.zora_flag_string), asked)
    try:
        chosen = plan(config.flag_string, config.seed, config.zora_flag_string)
    except FlagsRefused as exc:
        if zora_reasons:
            outcome.expected_refusal = "; ".join(zora_reasons)
        else:
            fail(f"refused a supported configuration: {'; '.join(exc.reasons)}")
        return
    if zora_reasons:
        fail(f"accepted a ZORA string the settings forbid: {zora_reasons}")
    outcome.encoded = chosen.encode_level_data
    world, result = generate_world(chosen, base_rom())
    check_acceptance(chosen, world, result, fail)
    for problem in owner_flag_problems(world, overworld_gates(chosen.zora_resolved),
                                       chosen.zora_resolved.l4_sword is L4Sword.LEVEL_9,
                                       chosen.zora_resolved.l4_sword is L4Sword.LEVEL_2):
        fail(f"owner flags: {problem}")
    before_settings = serialize_to_rom(world, base_rom(), config=chosen.config)
    finished = generate_rom(config.flag_string, config.seed, base_rom(),
                            player_settings_from_page(config.page_settings), config.zora_flag_string)
    check_seed_code(config, before_settings, finished, fail)
    check_returned_to_page(config, asked, outcome.encoded, finished, fail)
    check_round_trip(chosen, world, finished.rom, fail)
    if keep_rom:
        outcome.rom = finished.rom


def check_acceptance(chosen: GenerationPlan, world: GameWorld, result: GenerationResult,
                     fail: Callable[[str], None]) -> None:
    """acceptance.md (E1, E3, E4, E5) on the shipped world, and Randomize Magical Sword's heart
    check; generation ran both, so a failure here means it shipped something they reject."""
    assert result.item_shuffle_result is not None and result.overworld is not None
    failure = acceptance_check(world.levels, result.item_shuffle_result, world.overworld, result.overworld,
                               extra_options(chosen).logic_rules)
    if failure is not None:
        fail(f"acceptance: {failure}")
    if chosen.zora.randomize_magical_sword:
        assert result.extra_pool_items is not None
        if not has_magical_sword_hearts(world.levels, result.item_shuffle_result, result.extra_pool_items,
                                        OverworldResult(world.overworld, result.overworld),
                                        extra_options(chosen)):
            fail("acceptance: magical-sword hearts")


def check_seed_code(config: Config, before_settings: bytes, finished: GeneratedRom,
                    fail: Callable[[str], None]) -> None:
    """FP-HASH-01 and FP-SET-01: the code hashes the ROM before player settings, and the
    finished ROM is that ROM with the player settings written, nothing else."""
    if finished.rom != apply_player_settings(before_settings, player_settings_from_page(config.page_settings)):
        fail("the finished ROM is not the seed's ROM plus the player settings")
    stamped = before_settings[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH]
    if stamped != expected_seed_code(before_settings):
        fail("the seed code is not the hash of the ROM before player settings")
    if finished.code != seed_code(before_settings) or finished.code != seed_code(finished.rom):
        fail(f"the returned seed code {finished.code} is not the ROM's")


def check_returned_to_page(config: Config, asked: Settings, encoded: bool, finished: GeneratedRom,
                           fail: Callable[[str], None]) -> None:
    """What the page gets back: the strings as asked (B23 corrected), "?" unresolved, and the
    level encoding as asked (B82 is on or off, never "?")."""
    if decode(finished.flag_string) != asked:
        fail(f"returned flags {finished.flag_string!r} differ from the asked {config.flag_string!r}")
    if finished.encode_level_data != encoded:
        fail(f"returned level encoding {finished.encode_level_data!r}, expected {encoded!r}")
    if finished.zora_flag_string != zora_flags.canonicalize(config.zora_flag_string):
        fail(f"returned ZORA flags {finished.zora_flag_string!r} differ from {config.zora_flag_string!r}")
    if finished.seed != config.seed:
        fail(f"returned seed {finished.seed} differs from {config.seed}")


def check_round_trip(chosen: GenerationPlan, world: GameWorld, rom: bytes, fail: Callable[[str], None]) -> None:
    """Parse and re-serialize byte for byte, then the finished-ROM checks. An encoded ROM is
    checked through its plain build, whose level data its own must decode to."""
    if chosen.config.level_encoding is not None:
        plain = serialize_to_rom(world, base_rom(), config=replace(chosen.config, level_encoding=None))
        if level_encoding.decode_level_data(rom, chosen.config.level_encoding) \
                != level_encoding.plain_level_data(plain):
            fail("encoded level data does not decode to the plain build's")
        rom = plain
    reading = reading_config(chosen.config)
    if not round_trips(rom, reading):
        fail("parse and re-serialize changed the ROM")
    level_2_sword = chosen.zora_resolved.l4_sword is L4Sword.LEVEL_2
    for check in run_checks(parse_rom(rom, reading), finished_rom_checks(level_2_sword=level_2_sword)):
        if not check.passed:
            fail(f"finished-ROM check {check.check_id}: {check.message}")


def check_alternative(config: Config) -> tuple[Outcome, dict[str, bool]]:
    """The sweep's checks on one seed, and its FL-ALT figures (measure/alternative_values.py)."""
    outcome = check_config(config, keep_rom=True)
    if outcome.rom is None:
        return outcome, {}
    reading = reading_config(plan(config.flag_string, config.seed, config.zora_flag_string).config)
    figures = alternative_value_figures(parse_rom(outcome.rom, reading), outcome.rom)
    outcome.rom = None
    return outcome, figures


def alternative_expectations(batch: str, counts: Counter[str], seeds: int) -> list[str]:
    """Where a batch's figures differ from FL-ALT-02 to -04's Checks (all of n, or none). The
    alternative-value figures read the other way in batches without that value; None: not judged."""
    fields = ALTERNATIVE_BATCHES[batch]
    four_hearts = "C16" in fields
    from_five = "C20" in fields
    community = "C03" in fields
    expected: dict[str, bool | None] = {
        "new file $32, the rest FP-START-01's": four_hearts,
        "second-quest switch the same": four_hearts,
        "new file FP-START-01's ($22)": not four_hearts,
        "continue $02": True,
        "white 4": False if from_five else None,
        "slot 0 an owner quote": True,                 # owner ruling, every hint mode
        "hint-shop offers PRG0's": community,
        "hint-shop prices PRG0's": community,
        "white-sword selector $66": True,
        "eleven pointers distinct": True,
        **{f"slot {slot} a pool text": True if community else None for slot in HELPFUL_TEXT_SLOTS},
    }
    problems = [f"{figure}: {counts[figure]} of {seeds}" for figure, want in expected.items()
                if want is not None and counts[figure] != (seeds if want else 0)]
    if counts["life toll asks $30"] != counts["life toll"]:
        problems.append(f"life toll asks $30 in {counts['life toll asks $30']} of {counts['life toll']}")
    if from_five and counts["white 5"] + counts["white 6"] != seeds:
        problems.append("white sword outside 5 to 6")
    return problems


def _summarise_alternatives(results: list[tuple[Outcome, dict[str, bool]]]) -> int:
    """The sweep's summary, then each batch's FL-ALT figures, judged on the seeds it ran."""
    status = _summarise([outcome for outcome, _ in results])
    batches: dict[str, Counter[str]] = {}
    seeds: Counter[str] = Counter()
    for outcome, figures in results:
        seeds[outcome.config.label] += 1
        batches.setdefault(outcome.config.label, Counter()).update(name for name, value in figures.items() if value)
    for label, counts in batches.items():
        shown = ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
        print(f"{label} (n = {seeds[label]}): {shown}")
        for problem in alternative_expectations(label.split(" zora=")[0], counts, seeds[label]):
            print(f"FAIL {label}: {problem}")
            status = 1
    return status


# ---------------------------------------------------------------------------
# The emulator sample
# ---------------------------------------------------------------------------

# Walking one screen: a breadth-first search over short moves, keyed by Link's position on an
# 8-pixel grid, until a move ends on another overworld screen.
STEP_FRAMES = 16
SEARCH_LIMIT = 3000                    # positions explored before giving up
POSITION_CELL = 8
SETTLE_FRAMES = 120


def walk_one_screen(emu: Any) -> bool:
    from collections import deque

    from tests.emulator import OBJ_X, OBJ_Y, ROOM_ID, Button, Mode
    start_room = emu[ROOM_ID]
    queue = deque([emu.save()])
    seen = {(emu[OBJ_X] // POSITION_CELL, emu[OBJ_Y] // POSITION_CELL)}
    while queue and len(seen) < SEARCH_LIMIT:
        state = queue.popleft()
        for side in (Button.UP, Button.LEFT, Button.RIGHT, Button.DOWN):
            emu.load(state)
            emu.run(STEP_FRAMES, side)
            if emu.mode != Mode.PLAY:
                emu.run(SETTLE_FRAMES)     # a screen scroll finishes; a cave entrance is a dead end
            if emu[ROOM_ID] != start_room:
                return True
            if emu.mode != Mode.PLAY:
                continue
            position = (emu[OBJ_X] // POSITION_CELL, emu[OBJ_Y] // POSITION_CELL)
            if position not in seen:
                seen.add(position)
                queue.append(emu.save())
    return False


def emulate(config: Config) -> tuple[str, list[str]]:
    """Boot the configuration's ROM: file select, register, start, walk one screen."""
    from tests.emulator import CUR_LEVEL, ROOM_ID, Emulator, Mode
    outcome = check_config(config, keep_rom=True)
    if outcome.rom is None:
        return config.label, outcome.failures or ["no ROM"]
    problems = list(outcome.failures)
    emu = Emulator(outcome.rom)
    try:
        emu.boot_to_file_select()
        emu.register_file()
        emu.start_game()
    except AssertionError as exc:
        return config.label, problems + [f"emulator: boot, register or start failed ({exc}) at mode {emu.mode}"]
    if emu.mode != Mode.PLAY or emu[CUR_LEVEL] != 0:
        return config.label, problems + [f"emulator: started in mode {emu.mode}, level {emu[CUR_LEVEL]}"]
    if not walk_one_screen(emu):
        problems.append(f"emulator: found no way off start screen ${emu[ROOM_ID]:02X}")
    return config.label, problems


# ---------------------------------------------------------------------------
# Unsupported and conflicting input
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BadInput:
    kind: str
    flag_string: str
    must_name: str                         # a word the refusal must contain
    zora_flag_string: str = ""
    page_settings: dict[str, Any] = field(default_factory=dict)
    seed: int = 1


# How a refusal names each colour slot (zora.rom.player_settings); choice keys are named as sent.
SETTING_NAMES = dict(zip((*PAGE_TUNIC_SLOTS, PAGE_HEART_SLOT), ("green tunic", "blue ring", "red ring", "heart colour"),
                         strict=True))


def unsupported_values(field_id: str) -> list[Any]:
    """Values of a field the support matrix refuses on the baseline (with B22 off for B23)."""
    baseline = mvp_baseline_settings()
    if field_id in OPTIONS_BY_ID:
        return [index for index in range(OPTIONS_BY_ID[field_id].count)
                if not _supported(baseline.updated(options={field_id: index}), field_id)]
    return [state for state in ThreeState
            if not _supported(baseline.updated(toggles={field_id: state}), field_id)
            and field_id != MONEY_OR_LIFE_TOLL.id]


def bad_inputs(count: int) -> list[BadInput]:
    rng = random.Random(f"{SWEEP_KEY}:refusals")
    baseline = mvp_baseline_settings()
    makers: list[Callable[[], BadInput]] = []

    def with_value(field_id: str, value: Any) -> Settings:
        return (baseline.updated(options={field_id: value}) if field_id in OPTIONS_BY_ID
                else baseline.updated(toggles={field_id: value}))

    def unsupported_field() -> BadInput:
        # only values no dependency rule refuses first (that refusal names the rule's fields)
        field_ids = [option.id for option in OPTION_FIELDS] + [toggle.id for toggle in TOGGLE_FIELDS]
        choices = {field_id: [value for value in unsupported_values(field_id)
                              if not check_dependencies(with_value(field_id, value))]
                   for field_id in field_ids}
        field_id = rng.choice([field_id for field_id, values in choices.items() if values])
        value = rng.choice(choices[field_id])
        settings = with_value(field_id, value)
        # B82's "?" is refused by name (ENCODE_LEVEL_DATA_NOT_RANDOM), not by field id
        must_name = level_encoding.LABEL if field_id == ENCODE_LEVEL_DATA.id else field_id
        return BadInput("unsupported field value", encode(settings), must_name)

    def random_level_encoding() -> BadInput:
        settings = draw_settings(rng).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.POSSIBLE})
        return BadInput("B82 ?", encode(settings), "cannot be random")

    def toll_without_merchants_on() -> BadInput:
        b22 = rng.choice([ThreeState.ON, ThreeState.POSSIBLE])
        b23 = rng.choice([ThreeState.OFF, ThreeState.POSSIBLE])
        return BadInput("B23 off or ? with B22 on or ?", encode(baseline.updated(
            toggles={MONEY_OR_LIFE_ROOMS.id: b22, MONEY_OR_LIFE_TOLL.id: b23})), "B23")

    def malformed_flags() -> BadInput:
        good = encode(baseline)
        bad = rng.choice([good + "!", good[:-1] + "#", " ", "-", good + good * 4, "a b"])
        return BadInput("malformed flag string", bad, "Flag")

    def malformed_zora() -> BadInput:
        # "2.1" is a valid version-2 string (the progressive items' flags); version 3 is not known
        zora = rng.choice(["3.1", "9.1", "1.!", "x", "1.", ".1", "1.ZZZZZZZ", "0.1", "1.1.1"])
        return BadInput("malformed ZORA string", encode(baseline), "ZORA", zora_flag_string=zora)

    def sword_hearts_conflict() -> BadInput:
        # the magical sword without a heart cap, while B10 may raise the requirement to 14
        b10 = rng.choice([ThreeState.ON, ThreeState.POSSIBLE])
        zora = rng.choice(["1.1", "1.3", "1.H", "1.J", "1.L", "1.N"])
        return BadInput("magical sword over 12 hearts", encode(baseline.updated(toggles={"B10": b10})),
                        "Magical Sword", zora_flag_string=zora)

    def bad_player_setting() -> BadInput:
        slot = rng.choice([*PAGE_TUNIC_SLOTS, PAGE_HEART_SLOT, *PAGE_CHOICES])
        if slot in PAGE_CHOICES:
            value: Any = rng.choice(["", "maybe", 1, None])
        else:
            value = rng.choice([BLACKER_THAN_BLACK, PALETTE_SIZE, -1, 255, "16", None])
        return BadInput("bad player setting", encode(baseline), SETTING_NAMES.get(slot, slot),
                        page_settings={slot: value})

    def bad_seed() -> BadInput:
        encoding = rng.choice(ENCODING_CHOICES)
        return BadInput("seed out of range", encode(baseline.updated(toggles={ENCODE_LEVEL_DATA.id: encoding})),
                        "seed", seed=rng.choice([-1, SEED_LIMIT, SEED_LIMIT * 7, -(SEED_LIMIT // 2)]))

    makers = [unsupported_field, unsupported_field, unsupported_field, toll_without_merchants_on,
              malformed_flags, malformed_zora, sword_hearts_conflict, bad_player_setting, bad_seed,
              random_level_encoding]
    return [makers[index % len(makers)]() for index in range(count)]


def check_refusal(bad: BadInput) -> tuple[str, str | None]:
    """(kind, problem): None when the input is refused with a message naming its cause.
    The B23 case is never refused when B22 is off (FL-DEP-06); here B22 is on or "?"."""
    try:
        settings = player_settings_from_page(bad.page_settings)
        generate_rom(bad.flag_string, bad.seed, base_rom(), settings, bad.zora_flag_string)
    except REFUSALS as exc:
        if bad.must_name.lower() not in str(exc).lower():
            return bad.kind, f"message does not name {bad.must_name!r}: {exc}"
        return bad.kind, None
    except Exception as exc:
        return bad.kind, f"crash: {type(exc).__name__}: {exc}"
    return bad.kind, f"accepted: flags {bad.flag_string!r} zora {bad.zora_flag_string!r} " \
                     f"settings {bad.page_settings} seed {bad.seed}"


# ---------------------------------------------------------------------------
# Running and reporting
# ---------------------------------------------------------------------------

def _summarise(outcomes: list[Outcome]) -> int:
    kinds: Counter[str] = Counter()
    for outcome in outcomes:
        for failure in outcome.failures:
            kinds[failure.split(":")[0]] += 1
            print(f"FAIL {outcome.config.label} seed {outcome.config.seed} flags {outcome.config.flag_string} "
                  f"zora {outcome.config.zora_flag_string or '-'}: {failure}")
    failed = sum(bool(outcome.failures) for outcome in outcomes)
    encoded = sum(outcome.encoded for outcome in outcomes)
    expected = sum(outcome.expected_refusal is not None for outcome in outcomes)
    print(f"{len(outcomes)} configurations, {encoded} encoded, {expected} refused as expected, "
          f"{failed} with failures; by kind {dict(kinds)}")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=["random", "fixed", "alternatives", "progressive", "emulator", "refusals"])
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=None, help="default: 100 (random, emulator, refusals), "
                                                                     "every fixed or alternatives case")
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    if not level_encoding.is_available():
        print("qa_sweep: the level-encoding module is not in this tree; level encoding stays off", file=sys.stderr)
    with ProcessPoolExecutor(args.workers) as pool:
        count = 100 if args.count is None else args.count
        if args.mode == "random":
            configs = [random_config(index) for index in range(args.start, args.start + count)]
            return _summarise(list(pool.map(check_config, configs, chunksize=4)))
        if args.mode == "fixed":
            fixed = list(fixed_configs(args.seeds))[args.start:]
            fixed = fixed if args.count is None else fixed[:args.count]
            return _summarise(list(pool.map(check_config, fixed, chunksize=4)))
        if args.mode == "progressive":
            batch = list(progressive_configs(args.seeds))[args.start:]
            batch = batch if args.count is None else batch[:args.count]
            outcomes = list(pool.map(check_config, batch, chunksize=4))
            for label in dict.fromkeys(outcome.config.label for outcome in outcomes):
                ran = [outcome for outcome in outcomes if outcome.config.label == label]
                print(f"{label}: {sum(not outcome.failures for outcome in ran)} of {len(ran)} accepted and beatable")
            return _summarise(outcomes)
        if args.mode == "alternatives":
            batch = list(alternative_configs(args.seeds))[args.start:]
            batch = batch if args.count is None else batch[:args.count]
            return _summarise_alternatives(list(pool.map(check_alternative, batch, chunksize=4)))
        if args.mode == "emulator":
            configs = [random_config(index) for index in range(args.start, args.start + count)]
            results = list(pool.map(emulate, configs))
            for label, problems in results:
                for problem in problems:
                    print(f"FAIL {label}: {problem}")
            failed = sum(bool(problems) for _, problems in results)
            print(f"{len(results)} ROMs booted, {failed} with problems")
            return 1 if failed else 0
        refusals = list(pool.map(check_refusal, bad_inputs(count)))
    by_kind: Counter[str] = Counter(kind for kind, _ in refusals)
    for kind, refusal_problem in refusals:
        if refusal_problem is not None:
            print(f"FAIL {kind}: {refusal_problem}")
    failed = sum(problem is not None for _, problem in refusals)
    print(f"{len(refusals)} unsupported inputs {dict(by_kind)}, {failed} not refused cleanly")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
