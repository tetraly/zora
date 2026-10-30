"""Mirror Overworld (B06; overworld-behavior.md OW-MIR-01 to OW-MIR-06, hints-behavior.md HT-MIR-01) on its
Check strings. ZORA flips the seed as made without B06 (OW-MIR-01's MAY: the model's part at FINISH, the
rest in the image, zora/rom/mirror_overworld.py), so a seed with B06 on is the same seed with it off,
flipped: the two differ only in the seed's code and in the hints, which state each place's region after
the flip. The emulator side is
tests/test_mirror_overworld_emulator.py."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_revision import prg1
from zora.flags import form
from zora.flags.codec import decode
from zora.flags.fields import MIRROR_OVERWORLD, ThreeState
from zora.flags.support import POSTPONED_TOGGLES, unsupported_fields
from zora.generate.pipeline import build, generate_rom, plan
from zora.generate.steps.hint_text import REGION_TABLE, level_location_sentence
from zora.generate.steps.mixed_overworld_quest import door_screen
from zora.generate.steps.randomize_mazes import DEAD_WOODS, LOST_HILLS, maze_hint
from zora.model.enums import OverworldDirection
from zora.rom import mirror_overworld as mirror
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.layout import EXT_HINT_DATA_ROM_END, EXT_HINT_DATA_ROM_START, QUOTE_DATA_ADDRESS, REFUSAL_TEXT_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.revision import Revision, finished_in_prg0_layout, layout_of

pytestmark = needs_base_rom

CP5 = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
B06_ON = "8hq4BeR1JXo89c2WXnefpphDg!UJ3A"            # OW-MIR-01's Check strings
B06_POSSIBLE = "8hq4BeR1JXo8A1m!572WBFNOTrUJ3A"
SEEDS = (1, 2, 3)
SEED_CODE = range(0x0AFB0, 0x0AFB4)                  # FP-HASH-01's code, which follows the flag string
# Bank 1's text pointers and texts: the old text area after its pointer table, then the extended bank
HINT_TEXT = (range(QUOTE_DATA_ADDRESS, REFUSAL_TEXT_ADDRESS), range(EXT_HINT_DATA_ROM_START, EXT_HINT_DATA_ROM_END))
# An old Uphill Battle string from an out-of-date document: B06 on and five out-of-range option
# slots, each clamped to its last option (FL-ENC-03 rule 3); tests/test_tournament_presets.py too.
OLD_UPHILL_BATTLE = "143oNtDD4Pw3Yw6SRryTCXlqTsN20hHVl8gF"


@cache
def rom(flags: str, seed: int, on_prg1: bool = False) -> bytes:
    return generate_rom(flags, seed, prg1() if on_prg1 else remember_repo_base_rom()).rom


def test_b06_is_produced_with_no_notice() -> None:
    assert not POSTPONED_TOGGLES
    for flags in (B06_ON, B06_POSSIBLE, OLD_UPHILL_BATTLE):
        assert unsupported_fields(decode(flags)) == [] and plan(flags, 1).notices == ()
    assert plan(B06_ON, 1).config.mirror_overworld and not plan(CP5, 1).config.mirror_overworld
    assert {plan(B06_POSSIBLE, seed).config.mirror_overworld for seed in range(1, 9)} == {True, False}
    assert form.supported_values(MIRROR_OVERWORLD) == tuple(int(state) for state in ThreeState)


PRG1_MARK = pytest.param(True, id="PRG1", marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(),
                                                                   reason="no PRG1 ROM beside the base"))


@pytest.mark.parametrize("on_prg1", [pytest.param(False, id="PRG0"), PRG1_MARK])
@pytest.mark.parametrize("seed", SEEDS)
def test_a_mirrored_seed_is_its_unmirrored_seed_flipped(seed: int, on_prg1: bool) -> None:
    """On PRG1 too: the finished ROMs keep PRG1's layout and compare in PRG0's."""
    unmirrored, mirrored = rom(CP5, seed, on_prg1), rom(B06_ON, seed, on_prg1)
    assert layout_of(mirrored) is layout_of(unmirrored) is (Revision.PRG1 if on_prg1 else Revision.PRG0)
    flipped = bytearray(finished_in_prg0_layout(unmirrored))
    mirror.mirror_overworld(flipped)
    differing = {i for i, (a, b) in enumerate(zip(flipped, finished_in_prg0_layout(mirrored), strict=True))
                 if a != b}
    allowed = {i for area in (SEED_CODE, *HINT_TEXT) for i in area}
    assert differing <= allowed, sorted(f"0x{i:05X}" for i in differing - allowed)[:10]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_flip_s_bytes(seed: int) -> None:
    """OW-MIR-02 and OW-MIR-03's Checks: the cave rooms keep PRG0's rows, every other row is PRG0's
    flipped (B05, B87, B88 and B89 off), table E stays, the recorder's list is PRG0's flipped."""
    base, image = remember_repo_base_rom(), rom(B06_ON, seed)
    expected = bytearray(base)
    mirror._flip_layouts(expected)
    layouts = slice(mirror.ROOM_LAYOUTS_OW, mirror.ROOM_LAYOUTS_OW + mirror.LAYOUT_ROWS * mirror.LAYOUT_WIDTH)
    assert image[layouts] == expected[layouts]
    for row in mirror.CAVE_ROOM_ROWS:
        start = mirror.ROOM_LAYOUTS_OW + row * mirror.LAYOUT_WIDTH
        assert image[start:start + mirror.LAYOUT_WIDTH] == base[start:start + mirror.LAYOUT_WIDTH]
    flute = slice(mirror.RECORDER_SECRET_SCREENS.start, mirror.RECORDER_SECRET_SCREENS.stop)
    assert image[flute] == bytes(screen ^ mirror.MIRROR_SCREEN for screen in base[flute])
    cave_table = mirror.SCREEN_TABLES + mirror.CAVE_TABLE * mirror.SCREENS
    unmirrored = rom(CP5, seed)
    assert image[cave_table:cave_table + mirror.SCREENS] == unmirrored[cave_table:cave_table + mirror.SCREENS]
    assert image[mirror.SPAWN_CALL:mirror.SPAWN_CALL + 3] == mirror.SPAWN_CALL_BYTES
    assert image[mirror.SPAWN_COPIES:mirror.SPAWN_COPIES + 36] == mirror.mirrored_spawn_lists(base)
    assert image[mirror.CAPTION_POINTER:mirror.CAPTION_POINTER + 2] == mirror.CAPTION_POINTER_BYTES


def test_spawn_copies_exchange_lists_0_and_1_and_flip_each_column() -> None:
    base = remember_repo_base_rom()
    copies = mirror.mirrored_spawn_lists(base)
    lists = [base[mirror.SPAWN_LISTS + 9 * index:mirror.SPAWN_LISTS + 9 * (index + 1)] for index in range(4)]
    flipped = (lists[1], lists[0], lists[2], lists[3])
    assert copies == b"".join(bytes(spot ^ 0x0F for spot in spots) for spots in flipped)


def sentences(image: bytes) -> set[str]:
    """Every text of the ROM's hint block, its padding and line breaks as single spaces."""
    return {" ".join(quote.text.replace("~", " ").replace("|", " ").split())
            for quote in parse_rom(image).quotes if quote.text}


def stated(level: int, region: int) -> str:
    return " ".join(level_location_sentence(level, region).replace("|", " ").split())


@pytest.mark.parametrize("seed", SEEDS)
def test_the_level_hints_name_the_door_s_region_after_the_flip(seed: int) -> None:
    """HT-MIR-01: each level's door stands on m(s) in the finished ROM, and wherever the unmirrored
    seed's hint names its door's region (mixed hints may deceive, the same way in both), the mirrored
    seed's names the region of m(s)."""
    off, on = parse_rom(rom(CP5, seed)), parse_rom(rom(B06_ON, seed))
    said_off, said_on = sentences(rom(CP5, seed)), sentences(rom(B06_ON, seed))
    true_hints = 0
    for level in range(1, 10):
        door_off, door_on = door_screen(off.overworld, level), door_screen(on.overworld, level)
        assert door_off is not None and door_on == door_off ^ mirror.MIRROR_SCREEN
        told = any(stated(level, REGION_TABLE[door_off]) in text for text in said_off)
        assert told == any(stated(level, REGION_TABLE[door_on]) in text for text in said_on), level
        true_hints += told
    assert true_hints


def test_a_mirrored_maze_hint_names_each_step_s_mirror() -> None:
    """ZORA's rule (docs/deviations.md): PRG0's Dead Woods path, north, west, south, west, is walked north,
    east, south, east on the flipped overworld (OW-MIR-04), and its hint says so; Lost Hills' right becomes left."""
    up, down, left, right = (OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                             OverworldDirection.LEFT_WEST, OverworldDirection.RIGHT_EAST)
    assert " ".join(maze_hint(DEAD_WOODS, [up, left, down, left], mirrored=True)) == \
        "GO NORTH, EAST, SOUTH, EAST TO THE FOREST OF MAZE"
    assert maze_hint(LOST_HILLS, [up, right, down, up], mirrored=True)[0] == "GO UP, LEFT,"


def test_the_unrandomized_dead_woods_hint_is_mirrored() -> None:
    """With the mazes left as they are, the offer showing PRG0's Dead Woods path names it mirrored, at
    its own price."""
    built = build(plan(B06_ON, 1), remember_repo_base_rom())
    offers = built.result.maze_offers
    assert DEAD_WOODS.hint_shop_offer in offers and offers[DEAD_WOODS.hint_shop_offer].price is None
    assert LOST_HILLS.hint_shop_offer not in offers          # PRG0's Lost Hills path goes up only
