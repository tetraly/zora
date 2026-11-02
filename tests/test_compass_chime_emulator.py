"""Compass Chime (ZORA flag compass_chime; asm/flags2/compass-chime/) in the emulator.

ZORA's level 1 is not the original game's, so each case sets its room up in RAM, where the game reads
it: the level block's attributes, the level's cellar list and its world flags are RAM copies that
loading the level fills. A new game loads level 1, the case writes the target room's conditions, and
the enter-room mode takes Link into it (making its objects as play starts, mode 5, as a door does);
the monsters are stopped by the clock.

The chime played when Tune1 holds its request ($06), TunePtr1 reaches the last note (offset 14) and
Tune1 then returns to 0, having started exactly once. The cases are numbered as in the feature's
plan; case 19, Music: Random, is checked separately with lozft."""
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Emulator,
    Mode,
)
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import MONSTER_SLOTS
from tests.test_half_speed_beep_emulator import BEEP_FRAMES, HEART_WARNING, LOW_HEARTS, PARTIAL, TUNE_0
from tests.test_progressive_emulator import ENTER_ROOM_MODE, IS_UPDATING_MODE
from tests.test_revision import prg1
from tests.test_stats_screen import HEART_PARTIAL, HEART_VALUES
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.model.enums import Enemy, Item
from zora.rom import layout
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.flags2_patch_data import PATCHES
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import LowHealthBeep, Music, PlayerSettings
from zora.rom.revision import NES_HEADER_SIZE

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 1
ON = zora_flags.ZoraFlags(compass_chime=ThreeState.ON)
# Randomize Magical Sword moves the no-item code to $0E (DungeonNothingCode.ZORA_REMAP), the Triforce of Power's
# (with the magical-sword cave's hearts capped, which the baseline's Change Sword Hearts needs)
REMAP = zora_flags.ZoraFlags(compass_chime=ThreeState.ON, randomize_magical_sword=True,
                             magical_sword_hearts_highest=12)
OFF = zora_flags.ZoraFlags()

# RAM (the pinned disassembly's src/Variables.inc)
TUNE_1 = 0x607
TUNE_PTR_1 = 0x618
INV_CLOCK = 0x66C
INV_COMPASS = ITEMS + 0x10            # one bit per level 1-8
INV_COMPASS_9 = 0x669
FULL_HEARTS = 0xFF
LEVEL_BLOCK_ATTRS = dict(zip("ABCDEF", (0x687E, 0x68FE, 0x697E, 0x69FE, 0x6A7E, 0x6AFE), strict=True))
WORLD_FLAGS_ADDRESS = 0x6BAF          # LevelInfo_WorldFlagsAddr: a pointer
CELLAR_LIST = 0x6BB2                  # LevelInfo_CellarRoomIdArray
CELLAR_LIST_LENGTH = 10
CELLAR_LIST_END = 0xFF

CHIME_REQUEST = 0x06
LAST_NOTE = 14                        # TunePtr1 of the E, the script's last note
ITEM_TAKEN = 0x10
SECRET_TRIGGER = 0x07                 # attribute F
TRIGGER_FOES, TRIGGER_LAST_BOSS, TRIGGER_PUSH_BLOCK, TRIGGER_NONE = 7, 3, 5, 0
ITEM_BITS = 0x1F                      # attribute E
ROOM_TYPE_BITS = 0x3F                 # attribute D
ITEM_CELLAR, TUNNEL = 0x3F, 0x3E
ENEMY_BITS, ENEMY_HIGH_BIT, GANON_CODE = 0x3F, 0x80, 0x3E
PRG0_NOTHING_CODE = 0x03
WATCH_FRAMES = 240
PICKUP_FRAMES = 300
NO_BUTTONS_FRAMES = 30
BANK_SIZE, SWITCHED_BASE, ROOM_CHECK_BANK = 0x4000, 0x8000, 5
CMP_ABSOLUTE = 0xCD


# --- ROMs --------------------------------------------------------------------------------------------

@cache
def rom(flags: zora_flags.ZoraFlags = ON, on_prg1: bool = False,
        settings: PlayerSettings | None = None) -> bytes:
    base = prg1() if on_prg1 else remember_repo_base_rom()
    zora_string = zora_flags.encode(flags) if flags != OFF else ""
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, zora_string), base)
    return finish(built, base, player_settings=settings or PlayerSettings())


@cache
def ganon_room(flags: zora_flags.ZoraFlags) -> int:
    world = parse_rom(rom(flags))
    level_9 = next(level for level in world.levels if level.level_num == 9)
    return next(room.room_num for room in level_9.rooms if room.enemy == Enemy.THE_BEAST)


# --- setting a room up ---------------------------------------------------------------------------------

def attribute(emu: Emulator, which: str, room: int) -> int:
    return emu[LEVEL_BLOCK_ATTRS[which] + room]


def set_bits(emu: Emulator, which: str, room: int, mask: int, value: int) -> None:
    address = LEVEL_BLOCK_ATTRS[which] + room
    emu[address] = emu[address] & ~mask & 0xFF | value


def world_flag(emu: Emulator, room: int) -> int:
    """The address of the room's world flags."""
    return (emu[WORLD_FLAGS_ADDRESS] | emu[WORLD_FLAGS_ADDRESS + 1] << 8) + room


def set_taken(emu: Emulator, room: int, taken: bool) -> None:
    address = world_flag(emu, room)
    emu[address] = emu[address] | ITEM_TAKEN if taken else emu[address] & ~ITEM_TAKEN & 0xFF


def give_compass(emu: Emulator) -> None:
    level = emu[CUR_LEVEL]
    if level == 9:
        emu[INV_COMPASS_9] = 1
    else:
        emu[INV_COMPASS] |= 1 << (level - 1)


def take_compass(emu: Emulator) -> None:
    emu[INV_COMPASS], emu[INV_COMPASS_9] = 0, 0


def first_cellar(emu: Emulator) -> int:
    cellars = [emu[CELLAR_LIST + index] for index in range(CELLAR_LIST_LENGTH)]
    cellars = cellars[:cellars.index(CELLAR_LIST_END)] if CELLAR_LIST_END in cellars else cellars
    assert cellars, "level 1 has no cellar"
    return cellars[0]


def other_cellars_away(emu: Emulator, room: int) -> None:
    """No cellar but the one a case points at leads to the room (ZORA's level 1 may have stairs there)."""
    for index in range(CELLAR_LIST_LENGTH):
        cellar = emu[CELLAR_LIST + index]
        if cellar == CELLAR_LIST_END:
            break
        for which in "AB":
            if attribute(emu, which, cellar) == room:
                emu[LEVEL_BLOCK_ATTRS[which] + cellar] = CELLAR_LIST_END


Setup = Callable[[Emulator, int], None]


def hidden_item(trigger: int = TRIGGER_FOES, item: int = Item.KEY.value, taken: bool = False,
                compass: bool = True) -> Setup:
    """The room holds `item` back until `trigger`; no stairs lead from it."""
    def setup(emu: Emulator, room: int) -> None:
        other_cellars_away(emu, room)
        set_bits(emu, "F", room, SECRET_TRIGGER, trigger)
        set_bits(emu, "E", room, ITEM_BITS, item)
        set_taken(emu, room, taken)
        if compass:
            give_compass(emu)
    return setup


def stairway(trigger: int = TRIGGER_PUSH_BLOCK, room_type: int = ITEM_CELLAR, cellar_taken: bool = False,
             compass: bool = True, hidden_taken: bool | None = None) -> Setup:
    """Level 1's first cellar leads from the room (its destination A) and holds a key; the room's own
    trigger is `trigger` (with hidden_taken set, a hidden key there, taken or not)."""
    def setup(emu: Emulator, room: int) -> None:
        other_cellars_away(emu, room)
        cellar = first_cellar(emu)
        emu[LEVEL_BLOCK_ATTRS["A"] + cellar] = room
        set_bits(emu, "D", cellar, ROOM_TYPE_BITS, room_type)
        set_bits(emu, "E", cellar, ITEM_BITS, Item.KEY.value)
        set_taken(emu, cellar, cellar_taken)
        set_bits(emu, "F", room, SECRET_TRIGGER, trigger)
        if hidden_taken is not None:
            set_bits(emu, "E", room, ITEM_BITS, Item.KEY.value)
            set_taken(emu, room, hidden_taken)
        if compass:
            give_compass(emu)
    return setup


def ganon(item: int = Item.TRIFORCE_OF_POWER.value, trigger: int = TRIGGER_LAST_BOSS, taken: bool = False,
          compass: bool = True) -> Setup:
    """Ganon is the room's enemy, with `item` behind `trigger`."""
    def setup(emu: Emulator, room: int) -> None:
        set_bits(emu, "C", room, ENEMY_BITS, GANON_CODE)
        set_bits(emu, "D", room, ENEMY_HIGH_BIT, 0)
        hidden_item(trigger, item, taken, compass)(emu, room)
    return setup


def not_ganon_0e(emu: Emulator, room: int) -> None:
    """Item $0E in an ordinary room behind the foes: under the remap, the no-item code."""
    hidden_item(TRIGGER_FOES, Item.TRIFORCE_OF_POWER.value)(emu, room)


# --- playing -----------------------------------------------------------------------------------------

@dataclass
class Heard:
    starts: int = 0
    furthest: int = 0
    ended: bool = False
    beeps: int = 0

    @property
    def chimed(self) -> bool:
        return self.furthest >= LAST_NOTE and self.ended


def listen(emu: Emulator, frames: int = WATCH_FRAMES) -> Heard:
    heard, playing, beeping = Heard(), False, emu[TUNE_0] == HEART_WARNING
    for _ in range(frames):
        emu.run(1)
        now = emu[TUNE_1] == CHIME_REQUEST
        heard.starts += now and not playing
        if now:
            heard.furthest = max(heard.furthest, emu[TUNE_PTR_1])
        if playing and not now:
            heard.ended = emu[TUNE_1] == 0
        playing = now
        beep = emu[TUNE_0] == HEART_WARNING
        heard.beeps += beep and not beeping
        beeping = beep
    return heard


def start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def in_level(rom_bytes: bytes, level: int, hearts: int = FULL_HEARTS, partial: int = 0xFF) -> Emulator:
    emu = Emulator(rom_bytes)
    emu.new_game()
    emu[INV_CLOCK] = 1
    emu[HEART_VALUES], emu[HEART_PARTIAL] = hearts, partial
    emu[CUR_LEVEL] = level
    start_mode(emu, Mode.LOAD_LEVEL)
    wait_for_play(emu)
    emu.run(NO_BUTTONS_FRAMES)
    return emu


def enter(emu: Emulator, room: int) -> Heard:
    emu[ROOM_ID] = room
    start_mode(emu, ENTER_ROOM_MODE)
    return listen(emu)


def target_room(emu: Emulator) -> int:
    """A level-1 room beside the start room (the room above it)."""
    return (emu[ROOM_ID] - 0x10) & 0x7F


def heard_in(setup: Setup, rom_bytes: bytes) -> Heard:
    emu = in_level(rom_bytes, 1)
    room = target_room(emu)
    setup(emu, room)
    heard = enter(emu, room)
    assert emu[ROOM_ID] == room
    return heard


def chimed(setup: Setup, rom_bytes: bytes) -> bool:
    heard = heard_in(setup, rom_bytes)
    if heard.starts:
        assert heard.starts == 1, heard
    return heard.chimed


# --- the cases -----------------------------------------------------------------------------------------

PRG1 = pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM beside the base")

CASES: list[tuple[str, Setup, Callable[[], bytes], bool]] = [
    ("1 hidden item (trigger 7), compass", hidden_item(), rom, True),
    ("2 same, no compass", hidden_item(compass=False), rom, False),
    ("3 same, item taken", hidden_item(taken=True), rom, False),
    ("4 push-block stairs (trigger 5) to an item cellar", stairway(), rom, True),
    ("5 open stairs (trigger 0) to an item cellar", stairway(TRIGGER_NONE), rom, True),
    ("6 hidden item taken, stairway item waiting", stairway(TRIGGER_FOES, hidden_taken=True), rom, True),
    ("7 open stairs, no compass", stairway(TRIGGER_NONE, compass=False), rom, False),
    ("8 stairs, cellar item taken", stairway(cellar_taken=True), rom, False),
    ("9 stairs to a tunnel", stairway(room_type=TUNNEL), rom, False),
    ("10 case 1 with the flag off", hidden_item(), lambda: rom(OFF), False),
    ("11 Ganon's room, item $0E, trigger 3", ganon(), rom, True),
    ("12 same, taken", ganon(taken=True), rom, False),
    ("13 remap: Ganon's room, $0E, trigger 0", ganon(trigger=TRIGGER_NONE), lambda: rom(REMAP), True),
    ("14 remap: same, taken", ganon(trigger=TRIGGER_NONE, taken=True), lambda: rom(REMAP), False),
    ("15 remap: same, no compass", ganon(trigger=TRIGGER_NONE, compass=False), lambda: rom(REMAP), False),
    ("16 remap: not Ganon's room, $0E, trigger 7", not_ganon_0e, lambda: rom(REMAP), False),
    ("17 remap: case 1", hidden_item(), lambda: rom(REMAP), True),
    ("20 case 1 with Music: Off", hidden_item(), lambda: rom(settings=PlayerSettings(music=Music.OFF)), True),
]


@pytest.mark.parametrize(("setup", "made", "wanted"), [pytest.param(*case[1:], id=case[0]) for case in CASES])
def test_the_chime_plays_where_an_item_waits(setup: Setup, made: Callable[[], bytes], wanted: bool) -> None:
    assert chimed(setup, made()) == wanted


def test_the_remap_roms_no_item_code_is_the_triforce_of_powers() -> None:
    assert rom(REMAP)[layout.ASM_NOTHING_CODE_PATCH_OFFSET] == Item.TRIFORCE_OF_POWER.value
    assert rom(ON)[layout.ASM_NOTHING_CODE_PATCH_OFFSET] == PRG0_NOTHING_CODE


@PRG1
def test_case_18_prg1() -> None:
    assert chimed(hidden_item(), rom(on_prg1=True))


# lozft's RAM (the pinned source, 44b1bb5: lozft.s and its link map, lozft.dbg). Each frame lozft runs the
# game's DriveAudio, then sets PrevSfxChanMask from the game's sound channels (bit 1, pulse 2, while
# Tune1, its CurSquare2Sfx, is not 0), muting bhop's pulse 2 for it, then plays its song.
PREV_SFX_CHAN_MASK = 0x152
MUSIC_STATE = 0x153
PULSE_2_SFX = 0x02
PLAYING_FT = 2
BANK_7_FILE, BANK_15_FILE = NES_HEADER_SIZE + 7 * BANK_SIZE, NES_HEADER_SIZE + 15 * BANK_SIZE


@cache
def music_rom(from_source: bool) -> bytes:
    """Case 1's ROM with Music: Random (the standard library): lozft from the pinned lozft.bps, which
    players get, or built from its pinned source (lozft2, randomize_music's from_source)."""
    from scripts.music_assets import assets_available, pinned_assets
    from zora.rom.music.randomize import randomize_music
    if not assets_available():
        pytest.skip("needs the music clone (scripts/music_assets.py)")
    base = remember_repo_base_rom()
    finished = rom(settings=PlayerSettings(music=Music.RANDOM_STANDARD))
    return randomize_music(finished, base, pinned_assets(), SEED, from_source=from_source).rom


MUSIC_BUILDS = pytest.mark.parametrize("from_source", [False, True], ids=["lozft.bps", "lozft from source"])


@MUSIC_BUILDS
def test_case_19_music_random_mutes_its_pulse_2_for_the_chime(from_source: bool) -> None:
    """Case 1 with Music: Random: the chime plays all four notes; lozft's song keeps playing, with its
    pulse 2 muted on exactly the frames Tune1 is not 0 (the chime's), and given back after."""
    emu = in_level(music_rom(from_source), 1)
    room = target_room(emu)
    hidden_item()(emu, room)
    emu[ROOM_ID] = room
    start_mode(emu, ENTER_ROOM_MODE)
    heard, playing, frames, mismatched = Heard(), False, 0, []
    for frame in range(WATCH_FRAMES):
        emu.run(1)
        now = emu[TUNE_1] == CHIME_REQUEST
        heard.starts += now and not playing
        if now:
            heard.furthest = max(heard.furthest, emu[TUNE_PTR_1])
            frames += 1
        if playing and not now:
            heard.ended = emu[TUNE_1] == 0
        playing = now
        assert emu[MUSIC_STATE] == PLAYING_FT, frame
        if bool(emu[PREV_SFX_CHAN_MASK] & PULSE_2_SFX) != (emu[TUNE_1] != 0):
            mismatched.append(frame)
    assert heard.chimed and heard.starts == 1, heard
    assert frames and not mismatched, mismatched


@MUSIC_BUILDS
def test_case_19_the_chimes_bytes_survive_the_music(from_source: bool) -> None:
    """lozft writes none of the chime's bytes (its bank-0 song table and code are reserved,
    asm/rom_space.toml); the bank-7 hook is in the fixed bank, which a music ROM moves to bank 15."""
    made = music_rom(from_source)
    for offset, piece in PATCHES["compass-chime"]:
        if not isinstance(piece, bytes):
            continue
        at = offset - BANK_7_FILE + BANK_15_FILE if offset >= BANK_7_FILE else offset
        assert made[at:at + len(piece)] == piece, hex(offset)


def test_case_21_the_low_health_beep_keeps_going() -> None:
    """Case 1 with the half-speed low-health beep, at low health: both play, tune channels 1 and 0."""
    made = rom(settings=PlayerSettings(low_health_beep=LowHealthBeep.HALF_SPEED))
    emu = in_level(made, 1, LOW_HEARTS, PARTIAL)
    room = target_room(emu)
    hidden_item()(emu, room)
    heard = enter(emu, room)
    assert heard.chimed and heard.starts == 1, heard
    assert heard.beeps >= WATCH_FRAMES // (2 * BEEP_FRAMES) - 1, heard


def test_case_22_taking_the_triforce_of_power_ends_the_chime() -> None:
    """In level 9's Ganon's room, with the compass: the chime plays; the Triforce of Power, once Ganon is
    gone, is taken (the room's item-taken bit set), and entering again plays no chime."""
    made = rom()
    room = ganon_room(ON)
    emu = in_level(made, 9)
    give_compass(emu)
    first = enter(emu, room)
    assert first.chimed and first.starts == 1, first
    for slot in MONSTER_SLOTS:
        emu[OBJ_TYPE + slot] = 0
    emu[OBJ_STATE + ROOM_ITEM_SLOT] = 0           # Ganon_ActivateRoomItem
    emu.run(NO_BUTTONS_FRAMES)
    for _ in range(PICKUP_FRAMES):
        emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
        emu.run(1)
        if emu[world_flag(emu, room)] & ITEM_TAKEN:
            break
    assert emu[world_flag(emu, room)] & ITEM_TAKEN
    emu.run(PICKUP_FRAMES)
    again = enter(emu, room)
    assert not again.chimed and again.starts == 0, again


def test_the_room_check_reads_the_no_item_code_where_zora_writes_it() -> None:
    """IsRoomItemWaiting compares with CreateRoomObjects' no-item operand (fp-prog-02's
    RoomItemNothingCode, CreateRoomObjects + 21): CMP $B84F, file 0x1785F."""
    operand = layout.ASM_NOTHING_CODE_PATCH_OFFSET - NES_HEADER_SIZE - ROOM_CHECK_BANK * BANK_SIZE + SWITCHED_BASE
    compare = bytes([CMP_ABSOLUTE, operand & 0xFF, operand >> 8])
    assert sum(piece.count(compare) for _, piece in PATCHES["compass-chime"] if isinstance(piece, bytes)) == 1
