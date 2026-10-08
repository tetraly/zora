"""HT-SEL-01: the hint rooms' text selectors, per room (person code), not one value per table.

Regression: ZORA once wrote each level's selector over all eight entries of its family, so the
last level of each family won and every person in A levels (and in B levels) showed one text.
The corpus's tables vary (518 distinct A tables and 605 B tables in 1,000 finals)."""
import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.assign_hints_for_hint_type import HintAssignmentResult
from zora.generate.steps.hint_text import PRIMARY_SELECTORS, _build_selector_tables
from zora.model.enums import UnderworldPersonInit
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import load_rom, parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

MERCHANT_CODE = 0x11
BOMB_UPGRADE_CODE = 0x0F
FIRST_PERSON_CODE = 0x0B
LAST_PERSON_CODE = 0x12


def shipped(selector: int) -> int:
    return 0x4C if selector == 0x26 else selector


def test_corpus_seed_0001_tables() -> None:
    """Corpus final seed-0001's hint list, in PS-HINT-05's order (helpful levels 3, 4, 7, 8),
    gives its shipped tables exactly: A 4C 38 28 2E 32 30 3E 34, B 2A 2C 3E 42 3A 40 42 3C."""
    world = parse_rom(load_rom(verify_base_rom()))
    assignment = HintAssignmentResult(helpful={3, 4, 7, 8}, hint_ids=[
        (1, 0x0B), (6, 0x0C), (2, 0x0D), (5, 0x0E), (5, 0x10),     # levels 1-6 block
        (3, 0x0B), (4, 0x0C), (7, 0x0D), (8, 0x0E), (7, 0x0F), (8, 0x10),
    ])
    a, b = _build_selector_tables(world, assignment)
    assert a == bytes([0x4C, 0x38, 0x28, 0x2E, 0x32, 0x30, 0x3E, 0x34])
    assert b == bytes([0x2A, 0x2C, 0x3E, 0x42, 0x3A, 0x40, 0x42, 0x3C])


def hint_codes(world: GameWorld) -> dict[int, list[int]]:
    """Each level's listed hint codes (PS-HINT-01/02: no merchants, no kept $0F in A levels)."""
    codes: dict[int, list[int]] = {}
    for level in world.levels[:8]:
        family_a = world.person_inits[level.level_num - 1] == UnderworldPersonInit.A
        codes[level.level_num] = sorted(
            room.monster_list for room in level.rooms
            if room.has_monster_bit and FIRST_PERSON_CODE <= room.monster_list <= LAST_PERSON_CODE
            and room.monster_list != MERCHANT_CODE
            and not (family_a and room.monster_list == BOMB_UPGRADE_CODE))
    return codes


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_each_level_first_hint_room_shows_its_primary(seed: int) -> None:
    """In the finished ROM each level's first listed hint room (its lowest code) shows the
    level's primary selector (6,550 of 6,550 levels in the corpus), and neither table is one
    value repeated."""
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, load_rom(verify_base_rom())).rom)
    a, b = world.underworld_text_selectors_a or b"", world.underworld_text_selectors_b or b""
    for level, codes in hint_codes(world).items():
        if codes:
            table = a if world.person_inits[level - 1] == UnderworldPersonInit.A else b
            assert table[codes[0] - FIRST_PERSON_CODE] == shipped(PRIMARY_SELECTORS[level - 1]), level
    assert len(set(a[:8])) > 1 and len(set(b[:8])) > 1
