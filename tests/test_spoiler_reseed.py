"""The spoiler log's re-seed (owner rulings 3 and 4, 2026-11-06; FP-SPOIL-01, FP-HASH-01): Print Quest Info
(B51), Detailed Spoiler Log and Encode level data (B82) each change the whole generation and the icons, so one
seed number gives eight different seeds; B51's "?" resolves to Basic, Medium or Full first (2026-11-07)."""
from collections import Counter

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA, PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import SpoilerLevel, ZoraFlags
from zora.flags.zora_flags import encode as encode_zora
from zora.generate.pipeline import generate_rom, plan
from zora.rom import level_encoding
from zora.rom.base_rom import remember_repo_base_rom

ON, OFF, POSSIBLE = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
BASELINE = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
DETAILED = encode_zora(ZoraFlags(detailed_spoiler_log=True))
SEED = 3


def strings(b51: ThreeState, detailed: bool, b82: ThreeState = OFF) -> tuple[str, str]:
    return (encode(BASELINE.updated(toggles={PRINT_QUEST_INFO.id: b51, ENCODE_LEVEL_DATA.id: b82})),
            DETAILED if detailed else "")


def combinations(encodings: tuple[ThreeState, ...]) -> list[tuple[ThreeState, ThreeState, bool]]:
    return [(b82, b51, detailed) for b82 in encodings for b51 in (OFF, ON) for detailed in (False, True)]


def test_no_log_keeps_the_seed_number() -> None:
    """Level None adds nothing to the key, so a seed with B51, Detailed Spoiler Log and B82 off is as before."""
    chosen = plan(strings(OFF, False)[0], SEED)
    assert chosen.spoiler_level is SpoilerLevel.NONE
    assert chosen.generation_seed == SEED


def test_each_pair_of_encoding_and_level_has_its_own_key() -> None:
    encodings = (OFF, ON) if level_encoding.is_available() else (OFF,)
    keys = {}
    for b82, b51, detailed in combinations(encodings):
        flags, zora = strings(b51, detailed, b82)
        chosen = plan(flags, SEED, zora)
        assert chosen.spoiler_level == int(b51 is ON) + 2 * detailed
        keys[b82, b51, detailed] = chosen.generation_seed
    assert len(set(keys.values())) == len(keys) == 4 * len(encodings)


def test_random_print_quest_info_always_gives_a_log() -> None:
    """2026-11-07: B51's "?" picks Basic, Medium or Full per seed, never None, whatever Detailed Spoiler Log says
    in the ZORA string; the resolved B51 is the level's bit (on for Basic and Full, off for Medium)."""
    for detailed in (False, True):
        flags, zora = strings(POSSIBLE, detailed)
        levels: Counter[SpoilerLevel] = Counter()
        for seed in range(90):
            chosen = plan(flags, seed, zora)
            assert (chosen.spoiler_level & SpoilerLevel.BASIC != 0) == chosen.settings.is_on(PRINT_QUEST_INFO.id)
            levels[chosen.spoiler_level] += 1
        assert set(levels) == {SpoilerLevel.BASIC, SpoilerLevel.MEDIUM, SpoilerLevel.FULL}
        assert min(levels.values()) >= 18          # about a third each: 30 of 90 expected
    flags, zora = strings(POSSIBLE, True)
    assert ([plan(flags, seed).spoiler_level for seed in range(20)]
            == [plan(flags, seed, zora).spoiler_level for seed in range(20)])


@needs_base_rom
def test_each_combination_shows_its_own_icons() -> None:
    """FP-HASH-01: log-on and log-off ROMs show different icon rows except by chance; so do the levels and
    the encoded ROMs."""
    base = remember_repo_base_rom()
    encodings = (OFF, ON) if level_encoding.is_available() else (OFF,)
    codes = {}
    for b82, b51, detailed in combinations(encodings):
        flags, zora = strings(b51, detailed, b82)
        codes[b82, b51, detailed] = generate_rom(flags, SEED, base, zora_flag_string=zora).code
    assert len(set(codes.values())) == len(codes)

