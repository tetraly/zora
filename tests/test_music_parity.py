"""Input-replay parity of single-player ROMs (docs/reports/plan-mmc3-single-player.md section 2.7): the
same inputs, game frame by game frame, on today's MMC1 ROM, on lozft2 playing the original music and on
lozft2 playing custom music, comparing the game's state after every frame the game runs.

Three ROM kinds of one seed, on PRG0 and PRG1:
  mmc1      today's ROM (Music: On, no lozft);
  original  lozft2 from source with no song placed (every song table entry the game's own);
  custom    Music: Random (the standard library) through lozft2 (randomize_music(from_source=True)).

Each segment is set up on each kind (a new file, then the segment's own setup: a room entered, a ware
in reach, the win mode), then the MMC1 ROM's game state is copied into the others (CPU RAM and cartridge
RAM outside the music's own bytes and the code bank 1 copies to RAM), so the boot's lag, which differs
(lozft2 drops fewer frames), does not matter. Then each kind gets the same input for each frame the game
runs (FrameCounter advances), and after each the state is compared: RAM but the music's bytes (the two
sound engines', lozft's) and the display queues (the OAM shadow, where lozft2 hides sprites with $FF
and the game with $F8, and the tile transfer buffer), the random-number bytes included.

A dropped frame changes what the game does next, so the kinds must be identical up to the first game
frame whose work runs past its video frame (the one before a dropped frame) in either, and that is
asserted for both pairs (mmc1 against original,
original against custom). After it they may part: where, and each kind's lag frames, go to
temp/music-parity/REVISION.json and the test's output. Exact parity of custom music is deferred
(the plan's section 1.3), and lozft2 lags less than the MMC1 ROM by design.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import FRAME_COUNTER, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, Button, Emulator
from tests.needs import needs_base_rom
from tests.test_bait_in_pool import IS_UPDATING_MODE
from zora.rom.revision import Revision

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parent.parent
REPORT = REPO / "temp" / "music-parity"
SEED = 1
KINDS = ("mmc1", "original", "custom")
PAIRS = (("mmc1", "original"), ("original", "custom"))
# RAM (aldonunez Variables.inc)
HEART_VALUES, ITEMS = 0x66F, 0x657
SONG = 0x609
WIN_MODE = 0x13
MANY_HEARTS, WHITE_SWORD = 0xFF, 2
LOW_HEARTS = 0x40
# The music's own bytes, never copied or compared: scratch $00-$0F, the game's sound engine
# (SongScriptPtrLo-NoteCounterTune1 $66-$6F, CurNoteLowPeriodTrg-NoteLengthTableBase $05F0-$05F5, the
# $0600-$061F page; Variables.inc), lozft's (the stack page and Mmc3BankTemp $4F, $E4).
MUSIC_RAM = (set(range(0x00, 0x10)) | set(range(0x66, 0x70)) | set(range(0x100, 0x200))
             | set(range(0x5F0, 0x5F6)) | set(range(0x600, 0x620)) | {0x4F, 0xE4})
DISPLAY_QUEUES = set(range(0x200, 0x340))          # the OAM shadow and DynTileBuf
CPU_RAM = [address for address in range(0x800) if address not in MUSIC_RAM]
COMPARED = [address for address in CPU_RAM if address not in DISPLAY_QUEUES]
CART_RAM = list(range(0x6000, 0x6C90)) + list(range(0x7F00, 0x7F40))   # bank 1's RAM code aside
GAME_FRAME_LIMIT = 8                                # video frames for one game frame before it is a hang
BUSY_ROOMS = 4
OVERWORLD_FRAMES, DUNGEON_WALK_FRAMES, ROOM_FRAMES, TAKE_FRAMES, ENDING_FRAMES = 2400, 1200, 600, 300, 2400


@dataclass(frozen=True)
class Segment:
    name: str
    frames: int
    level: int | None = None        # a room entered first (Console.enter_room)
    room: int | None = None
    cave: int | None = None         # a cave's screen entered first, Link at its first ware
    ending: bool = False            # the win mode, the rescue fanfare over (Song 0)
    hold: tuple[int, int] = (8, 31)


def inputs(segment: Segment) -> list[int]:
    """The segment's input for each game frame: d-pad directions held a while, A and B taps."""
    if segment.ending:
        return [0] * segment.frames
    rng = random.Random(f"{SEED}:{segment.name}")
    pads = [Button.UP, Button.DOWN, Button.LEFT, Button.RIGHT, Button(0)]
    out: list[int] = []
    while len(out) < segment.frames:
        pad = int(rng.choice(pads))
        for index in range(rng.randrange(*segment.hold)):
            extra = int(Button.A) if rng.random() < 0.15 and index % 2 == 0 else 0
            extra |= int(Button.B) if rng.random() < 0.05 and index % 2 == 0 else 0
            out.append(pad | extra)
    return out[:segment.frames]


@cache
def roms(revision: Revision) -> dict[str, bytes]:
    from tests.test_cave_takes_emulator import _music_assets
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom import base_rom
    from zora.rom.music.lozft import with_lozft_from_source
    from zora.rom.music.randomize import randomize_music
    from zora.rom.player_settings import Music, PlayerSettings
    base_rom.remember_repo_base_rom()
    base = (base_rom.verify_base_rom() if revision is Revision.PRG0 else base_rom.verify_prg1_rom()).read_bytes()
    plain = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings()).rom
    music = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=Music.RANDOM_STANDARD)).rom
    return {"mmc1": plain, "original": bytes(with_lozft_from_source(music, base)),
            "custom": randomize_music(music, base, _music_assets(), SEED, from_source=True).rom}


@cache
def segments(revision: Revision) -> tuple[Segment, ...]:
    """The overworld, a walk through level 1's doors, the busiest rooms, every boss, two cave takes and
    the ending, from the seed's own world."""
    from zora.model.enums import Destination
    from zora.rom.parse.rom_file import parse_rom
    world = parse_rom(roms(revision)["mmc1"])
    level_1 = world.levels[0]
    busy = sorted(((level.enemy_quantity(level.block.room(number)), level.level_num, number)
                   for level in world.levels for number in level.room_nums), reverse=True)[:BUSY_ROOMS]
    caves = [next(screen.screen_num for screen in world.overworld.screens if screen.destination == destination)
             for destination in (Destination.WOOD_SWORD_CAVE, Destination.SHOP_1)]
    return (Segment("overworld", OVERWORLD_FRAMES),
            Segment("level 1's doors", DUNGEON_WALK_FRAMES, 1, level_1.entrance_room, hold=(30, 91)),
            *(Segment(f"busy level {level} ${room:02X}", ROOM_FRAMES, level, room) for _quantity, level, room in busy),
            *(Segment(f"boss level {level.level_num} ${level.boss_room:02X}", ROOM_FRAMES, level.level_num,
                      level.boss_room) for level in world.levels),
            *(Segment(f"cave take ${screen:02X}", TAKE_FRAMES, cave=screen) for screen in caves),
            Segment("ending", ENDING_FRAMES, ending=True))


def set_up(rom: bytes, segment: Segment) -> Emulator:
    from tests.test_bait_in_pool import CAVE_ITEM_IDS, CAVE_WARE_XS, CAVE_WARE_Y, ITEM_INACTIVE, Console
    console = Console(rom)
    emu = console.emu
    emu[ITEMS] = WHITE_SWORD
    if segment.room is not None:
        assert segment.level is not None
        console.enter_room(segment.level, segment.room)
    if segment.cave is not None:
        console.enter_cave(segment.cave)
        ware = next(position for position in range(3) if emu[CAVE_ITEM_IDS + position] != ITEM_INACTIVE)
        emu[OBJ_X], emu[OBJ_Y] = CAVE_WARE_XS[ware], CAVE_WARE_Y
    if segment.ending:
        emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = WIN_MODE, 0, 0
    return emu


def game_frame(emu: Emulator, buttons: int) -> int:
    """Run until the game has run one frame with `buttons` held; the lag frames on the way."""
    before = emu[FRAME_COUNTER]
    emu.nes.controller = buttons
    for lag in range(GAME_FRAME_LIMIT):
        emu.nes.step(1)
        if emu[FRAME_COUNTER] != before:
            return lag
    raise AssertionError("the game ran no frame")


def replay(revision: Revision, segment: Segment) -> dict[str, list[tuple[bytes, int]]]:
    """Each kind's (state, lag frames so far) after each game frame of the segment."""
    built = roms(revision)
    emus = {kind: set_up(built[kind], segment) for kind in KINDS}
    reference = emus["mmc1"]
    for kind in KINDS[1:]:
        for address in CPU_RAM + CART_RAM:
            emus[kind][address] = reference[address]
    if segment.ending:
        for emu in emus.values():
            emu[SONG] = 0               # UpdateEndGameCurtainEffect waits for the game's own song to end
    runs: dict[str, list[tuple[bytes, int]]] = {kind: [] for kind in KINDS}
    lags = dict.fromkeys(KINDS, 0)
    for buttons in inputs(segment):
        for kind, emu in emus.items():
            lags[kind] += game_frame(emu, buttons)
            if not segment.ending and emu[HEART_VALUES] < LOW_HEARTS:
                emu[HEART_VALUES] = MANY_HEARTS     # the same on every kind, at the same game frame
            runs[kind].append((bytes(emu[address] for address in COMPARED), lags[kind]))
    for kind, emu in emus.items():
        assert not emu.nes.has_crashed, (revision.value, segment.name, kind)
    return runs


def first_difference(left: list[tuple[bytes, int]], right: list[tuple[bytes, int]]) -> int | None:
    return next((index for index, (a, b) in enumerate(zip(left, right, strict=True)) if a[0] != b[0]), None)


def first_overrun(*runs: list[tuple[bytes, int]]) -> int:
    """The first game frame whose work ran past its video frame in any of the runs (len when none
    did): the one before the first frame reached after a lag frame. The state is read at the end of
    each video frame, so an overrunning frame's is read part-way through its work."""
    return min((next((max(index - 1, 0) for index, (_state, lag) in enumerate(run) if lag), len(run))
                for run in runs))


@needs_base_rom
@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1])
def test_the_same_inputs_play_the_same_until_a_frame_is_dropped(revision: Revision) -> None:
    report = {}
    for segment in segments(revision):
        runs = replay(revision, segment)
        row: dict[str, object] = {"game frames": segment.frames,
                                  "lag frames": {kind: runs[kind][-1][1] for kind in KINDS}}
        for left, right in PAIRS:
            parted = first_difference(runs[left], runs[right])
            lag_free = first_overrun(runs[left], runs[right])
            row[f"{left} vs {right}"] = {"first difference": parted, "first overrun": lag_free}
            assert parted is None or parted >= lag_free, (revision.value, segment.name, left, right, parted)
        report[segment.name] = row
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / f"{revision.value}.json").write_text(json.dumps(report, indent=1))
    for name, row in report.items():
        print(f"{revision.value} {name}: {row}")
