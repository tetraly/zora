"""Randomize Lost Hills' own layouts for $0B in the ROM as finished (asm/flags2/lost-hills,
zora/rom/extra_layouts.py; 2.0.0's bug: a fountain on $0B cut $0C and $0D off): $0B shows $7C (the
second quest's look) or $7D (the first's), which are its shared layout's column codes with the right edge
open, while $3C keeps its layout and the layouts themselves stay PRG0's; on PRG0 and PRG1, at the same
offsets; nothing of it without the flag. The finished-ROM walk (zora_measure/overworld_walk.py, which
qa_sweep runs) reaches every cave, mirrored or not, and finds $0C and $0D cut off with $0B on the layout it
shares. In the emulator: tests/test_lost_hills_layouts_emulator.py; the maze sets:
tests/test_overworld_gates.py test_the_maze_sets_hold_with_0b_s_own_layout."""
from functools import cache

import pytest

from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import MIRROR_OVERWORLD, OVERWORLD_QUEST, OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate import pipeline
from zora.generate.steps.overworld_gates import OverworldGates
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, verify_base_rom, verify_prg1_rom
from zora.rom.extra_layouts import EAST_EDGE_COLUMN, OPEN_EAST_EDGE, OWN_LAYOUTS
from zora.rom.flags2_patch_data import PATCHES as FLAGS2_PATCHES
from zora.rom.mirror_overworld import mirror_screen
from zora.rom.parse.rom_file import parse_rom
from zora.rom.revision import Revision, layout_of
from zora.rom.vanilla_overworld.layouts import screen_layout_codes
from zora.rom.vanilla_overworld.tables import ATTRIBUTE_TABLE_SIZE, EXTRA_LAYOUTS, LEVEL_BLOCK_OW
from zora.rom.vanilla_overworld.walkability import LAYOUT_MASK, LAYOUT_TABLE
from zora_measure.overworld_walk import unreached_caves

pytestmark = pytest.mark.skipif(not (BASE_ROM_PATH.exists() and PRG1_ROM_PATH.exists()),
                                reason="needs the PRG0 and PRG1 base ROMs")

SCREEN_11, SCREEN_60 = 0x0B, 0x3C
FOUNTAIN, DOORWAY = 0x7B, 0x0A
# Level encoding off, so the screen table reads plain; 2nd Quest (C01 = 1) shows the fountain on $0B
LOOKS = {"2nd Quest": (OverworldQuest.SECOND_QUEST, FOUNTAIN), "1st Quest": (OverworldQuest.FIRST_QUEST, DOORWAY)}
LOST_HILLS = zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON))
CUT_OFF = {0x0C, 0x0D}
BLANK = 0xFF
HOOK = range(0x16A04, 0x16A0E)          # LayoutRoomOW's pointer load, the routine's call


def flags(look: str, mirrored: bool = False) -> str:
    settings = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={OVERWORLD_QUEST.id: LOOKS[look][0]})
    if mirrored:
        settings = settings.updated(toggles={MIRROR_OVERWORLD.id: ThreeState.ON})
    return encode(settings)


@cache
def base(revision: Revision) -> bytes:
    return (verify_base_rom() if revision is Revision.PRG0 else verify_prg1_rom()).read_bytes()


@cache
def finished(revision: Revision, zora_flag_string: str, flag_string: str) -> bytes:
    rom = pipeline.generate_rom(flag_string, 7, base(revision), zora_flag_string=zora_flag_string).rom
    assert layout_of(rom) is revision
    return rom


def layout_number(rom: bytes, screen: int) -> int:
    return rom[LEVEL_BLOCK_OW.file_offset + LAYOUT_TABLE * ATTRIBUTE_TABLE_SIZE + screen] & LAYOUT_MASK


@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
@pytest.mark.parametrize("look", list(LOOKS))
def test_0b_shows_its_own_copy_with_lost_hills(revision: Revision, look: str) -> None:
    rom, original = finished(revision, LOST_HILLS, flags(look)), base(revision)
    shared = LOOKS[look][1]
    own = OWN_LAYOUTS[shared]
    assert (layout_number(rom, SCREEN_11), layout_number(rom, SCREEN_60)) == (own, shared)
    copy = screen_layout_codes(rom, own)
    assert screen_layout_codes(rom, shared) == screen_layout_codes(original, shared)
    assert copy[:EAST_EDGE_COLUMN] == screen_layout_codes(original, shared)[:EAST_EDGE_COLUMN]
    assert copy[EAST_EDGE_COLUMN] == OPEN_EAST_EDGE != screen_layout_codes(original, shared)[EAST_EDGE_COLUMN]
    assert rom[HOOK.start:HOOK.stop] == dict(FLAGS2_PATCHES["lost-hills"])[HOOK.start]


@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
@pytest.mark.parametrize("look", list(LOOKS))
def test_nothing_of_it_without_lost_hills(revision: Revision, look: str) -> None:
    rom, original = finished(revision, "", flags(look)), base(revision)
    assert layout_number(rom, SCREEN_11) == LOOKS[look][1]
    assert set(EXTRA_LAYOUTS.read(rom)) == {BLANK}
    assert rom[HOOK.start:HOOK.stop] == original[HOOK.start:HOOK.stop]


def test_prg1_has_prg0_s_bytes_where_the_patch_goes() -> None:
    """The hook's code and the extra layouts' space are the same bytes at the same offsets in both releases
    (revision.PRG1_MOVES end before them), and the space is blank."""
    prg0, prg1 = base(Revision.PRG0), base(Revision.PRG1)
    assert prg0[HOOK.start:HOOK.stop] == prg1[HOOK.start:HOOK.stop]
    assert set(EXTRA_LAYOUTS.read(prg0)) == set(EXTRA_LAYOUTS.read(prg1)) == {BLANK}


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("look", list(LOOKS))
def test_the_walk_reaches_every_cave_and_catches_the_shared_layout(look: str, mirrored: bool) -> None:
    """With $0B's layout number set back to the layout it shares with $3C, $0C and $0D (or their mirrored
    screens) are cut off."""
    rom = finished(Revision.PRG0, LOST_HILLS, flags(look, mirrored))
    world = parse_rom(rom)
    assert world.overworld_mirrored is mirrored
    gates = OverworldGates(lost_hills=True)
    assert unreached_caves(rom, world, gates) == {}
    screen_11 = mirror_screen(SCREEN_11) if mirrored else SCREEN_11
    at = LEVEL_BLOCK_OW.file_offset + LAYOUT_TABLE * ATTRIBUTE_TABLE_SIZE + screen_11
    shared = bytearray(rom)
    shared[at] = shared[at] & ~LAYOUT_MASK | LOOKS[look][1]
    cut = {mirror_screen(screen) if mirrored else screen for screen in CUT_OFF}
    assert set(unreached_caves(bytes(shared), world, gates)) == cut
