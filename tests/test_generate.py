"""Generation from a flag string and a seed (zora/generate/pipeline.py): the MVP
baseline gives the same output as the settings it stands for, and every
string the MVP cannot produce is refused with its reasons."""
import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import COAST_PIN, PinnedItem
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.rom import level_encoding
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.flags.dependencies import RESOLVED_TOGGLES
from zora.flags.fields import TOGGLE_FIELDS, ThreeState
from zora.flags.support import ENCODE_LEVEL_DATA_NOT_RANDOM
from zora.rom.game_config import GameConfig, HintMode
from zora.generate.pipeline import SEED_LIMIT, FlagsRefused, SeedRefused, generate_rom, plan
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions


def _base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return load_rom(verify_base_rom())


def test_baseline_flags_give_the_preset_output() -> None:
    """The MVP baseline with level encoding off is the settings every script
    used before flag strings: Consternation hints, B10 on, default shapes."""
    base = _base()
    seed = 4
    world = parse_rom(base)
    generate_shapes(world, Rng(seed), ShapeOptions(), feature_data=True, seed=seed)
    expected = serialize_to_rom(world, base, config=GameConfig(hint_mode=HintMode.CONSTERNATION,
                                                               features_b10=True))
    result = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, base)
    assert result.rom == expected
    assert result.flag_string == MVP_BASELINE_LEVEL_ENCODING_OFF and not result.encode_level_data


def test_plan_derives_settings_from_the_flags() -> None:
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 7)
    assert chosen.config == GameConfig(hint_mode=HintMode.CONSTERNATION, features_b10=True)
    assert chosen.shape_options == ShapeOptions() and chosen.post_shapes
    # FL-DEP-05: B14 and B16 stay in the shown string but not in the settings
    assert not chosen.settings.is_on("B14") and decode(chosen.flag_string).is_on("B14")


def test_canonical_string_in_the_result() -> None:
    """A non-canonical spelling (a leading 0, FL-ENC-03) comes back canonical."""
    assert plan("0" + MVP_BASELINE_LEVEL_ENCODING_OFF, 0).flag_string == MVP_BASELINE_LEVEL_ENCODING_OFF


def test_unsupported_fields_are_refused_by_name() -> None:
    with pytest.raises(FlagsRefused) as refused:
        plan("0", 0)
    assert "not produced" in str(refused.value) and "C02 (Dungeon layout source)" in str(refused.value)
    possible = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B32": ThreeState.POSSIBLE})
    with pytest.raises(FlagsRefused, match="B32"):
        plan(encode(possible), 0)


def test_dependency_refusals_and_bad_strings() -> None:
    ladder = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={COAST_PIN: PinnedItem.LADDER})
    with pytest.raises(FlagsRefused, match="FL-DEP-01 rule 1"):
        plan(encode(ladder), 0)
    with pytest.raises(FlagsRefused, match="invalid character"):
        plan("not a flag string", 0)


@pytest.mark.parametrize("flags", [MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF])
def test_an_out_of_range_seed_is_refused_by_name(flags: str) -> None:
    """FL-SEED-01: the page's seed field takes any digits; a number past eight bytes (or below
    0) is refused with a message, never an OverflowError from deep in the encoding's key or the
    "?" stream (found by scripts/qa_sweep.py, level encoding on)."""
    question = encode(decode(flags).updated(toggles={"B27": ThreeState.POSSIBLE}))
    for flag_string in (flags, question):
        for seed in (-1, SEED_LIMIT, 10 ** 30):
            with pytest.raises(SeedRefused, match="seed number"):
                plan(flag_string, seed)
    if flags == MVP_BASELINE and not level_encoding.is_available():
        return      # the baseline encodes level data: without the private module plan refuses it
    assert plan(flags, SEED_LIMIT - 1).seed == SEED_LIMIT - 1


def test_level_encoding_text() -> None:
    assert level_encoding.LABEL == "Encode level data"
    assert level_encoding.HELP_TEXT == (
        "Encodes most dungeon and overworld data so ROM editors and map viewers (like the Z1R Visualizer) "
        "can't read it. Gameplay is exactly the same. This isn't cheat-proof: a determined person can still "
        "decode the data.")


@pytest.mark.skipif(level_encoding.is_available(), reason="level encoding is installed")
def test_level_encoding_refused_when_unavailable() -> None:
    """No silent plain build: the baseline (encoding on) is refused."""
    with pytest.raises(level_encoding.LevelEncodingUnavailable):
        plan(MVP_BASELINE, 0)


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
def test_level_encoding_keeps_the_guarantees() -> None:
    """With the private module: the encoded ROM has the plain twin's size,
    differs only in the level data, the two edit sites and the seed's code, and its
    level data decodes back to the twin's; FP-Q2R-01's byte is omitted."""
    base = _base()
    seed = 5
    on = plan(MVP_BASELINE, seed)
    assert on.flag_string == MVP_BASELINE and on.config.level_encoding is not None
    world = parse_rom(base)
    generate_shapes(world, Rng(on.generation_seed), on.shape_options, feature_data=True, seed=seed)
    off_config = GameConfig(hint_mode=HintMode.CONSTERNATION, features_b10=True)
    plain = serialize_to_rom(world, base, config=off_config)
    encoded = serialize_to_rom(world, base, config=on.config)
    assert encoded == generate_rom(MVP_BASELINE, seed, base).rom
    assert len(encoded) == len(plain)
    allowed = level_encoding.changed_ranges_allowed()
    from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
    allowed.append((SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH))    # FP-HASH-01 hashes the ROM
    outside = [i for i, (a, b) in enumerate(zip(plain, encoded))
               if a != b and not any(lo <= i < hi for lo, hi in allowed)]
    assert not outside, [hex(i) for i in outside[:8]]
    assert level_encoding.decode_level_data(encoded, on.config.level_encoding) \
        == level_encoding.plain_level_data(plain)


# --- "?" values (FL-DEP-04; owner rulings 2026-10-04) ------------------------------------------------

def _cp5_with(**toggles: ThreeState) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles=toggles))


def test_a_question_mark_whose_off_is_not_supported_is_refused_up_front() -> None:
    for field_id, label in (("B32", "B32 (Shuffle dungeon monsters within each level): ?"),
                            ("B23", "B23 (Re-draw the merchants' toll): ?")):
        with pytest.raises(FlagsRefused) as refused:
            plan(_cp5_with(**{field_id: ThreeState.POSSIBLE}), 1)
        assert refused.value.reasons == ["not produced: " + label]
    with pytest.raises(FlagsRefused) as refused:
        plan(encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C14": 3})), 1)
    assert refused.value.reasons == ["not produced: C14 (Dungeon room shuffle): ?"]


def test_question_marks_resolve_from_their_own_stream() -> None:
    """The resolved value depends only on the seed and the canonical string, and the main
    generation is untouched: a "?" string's ROM is the ROM of its resolved string (level
    encoding off, so the string reaches no byte)."""
    rom = load_rom(BASE_ROM_PATH)
    question = _cp5_with(B27=ThreeState.POSSIBLE)
    outcomes = {}
    for seed in range(1, 7):
        resolved = plan(question, seed).settings.toggle("B27")
        assert resolved is plan(question, seed).settings.toggle("B27")       # reproducible
        assert resolved in (ThreeState.OFF, ThreeState.ON)
        outcomes[seed] = resolved
        assert generate_rom(question, seed, rom).rom == generate_rom(_cp5_with(B27=resolved), seed, rom).rom
    assert set(outcomes.values()) == {ThreeState.OFF, ThreeState.ON}


def test_question_mark_odds_are_even() -> None:
    """FL-DEP-04: a possible field is on or off with equal chance; a random index is uniform."""
    question = _cp5_with(B08=ThreeState.POSSIBLE)
    ons = sum(plan(question, seed).settings.is_on("B08") for seed in range(2000))
    assert abs(ons - 1000) < 4 * 22                       # 4 standard deviations
    limit = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C17": 22}))
    picked = {plan(limit, seed).settings.option("C17") for seed in range(400)}
    assert picked == set(range(1, 22))


def test_resolved_values_are_not_returned() -> None:
    """The result carries the canonical unresolved string and the level encoding as asked."""
    rom = load_rom(BASE_ROM_PATH)
    question = _cp5_with(B27=ThreeState.POSSIBLE)
    result = generate_rom(question, 3, rom)
    assert result.flag_string == question and result.encode_level_data is False


@pytest.mark.parametrize("flags", [MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF])
def test_a_question_mark_on_level_encoding_is_refused(flags: str) -> None:
    """Owner ruling (2026-10-06): Encode level data (B82) is on or off and never "?". The
    refusal says so in the owner's words, before anything is resolved or generated, and
    names no other field when the rest of the string is supported."""
    question = encode(decode(flags).updated(toggles={"B82": ThreeState.POSSIBLE}))
    with pytest.raises(FlagsRefused) as refused:
        plan(question, 1)
    assert refused.value.reasons == [ENCODE_LEVEL_DATA_NOT_RANDOM]
    assert ENCODE_LEVEL_DATA_NOT_RANDOM == "Encode level data is on or off; it cannot be random"


def test_level_encoding_question_mark_is_refused_beside_other_reasons() -> None:
    """With another unsupported field too, both reasons are given, B82's first."""
    question = _cp5_with(B82=ThreeState.POSSIBLE, B03=ThreeState.ON)
    with pytest.raises(FlagsRefused) as refused:
        plan(question, 1)
    first, second = refused.value.reasons
    assert first == ENCODE_LEVEL_DATA_NOT_RANDOM and "B03" in second and "B82" not in second


def test_resolve_never_draws_for_level_encoding() -> None:
    """FL-DEP-04's resolver skips B82: its "?" is refused before resolving."""
    assert "B82" not in {toggle.id for toggle in RESOLVED_TOGGLES}
    assert len(RESOLVED_TOGGLES) == len(TOGGLE_FIELDS) - 1


def test_merchants_question_mark_takes_the_toll_with_it() -> None:
    """FL-DEP-06 after resolving: a B22 coin that comes up off turns B23 off."""
    question = _cp5_with(B22=ThreeState.POSSIBLE)
    for seed in range(1, 20):
        settings = plan(question, seed).settings
        assert settings.is_on("B23") == settings.is_on("B22")


# --- level encoding changes the whole generation (owner requirement, 2026-10-04) ----------------

def test_encoding_mixes_the_generation_seed_and_plain_seeds_stay() -> None:
    for seed in (0, 1, 12345):
        plain = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed)
        assert plain.generation_seed == seed
        if level_encoding.is_available():
            encoded = plan(MVP_BASELINE, seed)
            assert encoded.generation_seed != seed and encoded.generation_seed == plan(MVP_BASELINE, seed).generation_seed


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(10))
def test_encoded_and_plain_generations_differ_in_every_dungeon(seed: int) -> None:
    """The figure over seeds 0-199 is 200 of 200 (owner's bar: 99%)."""
    if not level_encoding.is_available():
        pytest.skip("level encoding not installed")
    from zora.generate.pipeline import generate_world
    rom = load_rom(BASE_ROM_PATH)

    def layouts(flags: str) -> list[list[tuple[int, object, bool]]]:
        world, _ = generate_world(plan(flags, seed), rom)
        return [[(room.room_num, room.room_type, room.movable_block) for room in level.rooms]
                for level in world.levels]
    assert all(a != b for a, b in zip(layouts(MVP_BASELINE), layouts(MVP_BASELINE_LEVEL_ENCODING_OFF), strict=True))


def test_the_result_carries_the_seeds_code_as_item_names() -> None:
    """FP-HASH-01: the seed's code, the four items the file-select screen shows, by name."""
    from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH, SEED_CODE_NAMES
    rom = load_rom(BASE_ROM_PATH)
    result = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 7, rom)
    items = result.rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH]
    assert result.code == tuple(SEED_CODE_NAMES[item] for item in items) and len(result.code) == 4
    assert generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 7, rom).code == result.code
