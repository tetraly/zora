"""The player-setting patches of asm/settings/ (docs/player-settings-patches.md)
in the emulator: Select swap's swap-only choice (FP-HOT-01), music off
(FP-SET-04), the death-warp mapping (FP-RESET-01) and reduce flashing
(FP-FIX-02).

The settings are not wired into the serializer yet. Each test takes the
current ZORA output (PRG0's world serialized with ZORA's code patches) and
writes the chosen setting's bytes over it with asm/settings/build.py's
`apply_settings`; the control is the same ROM at the setting's default (the
current ZORA output itself) and, where the spec names it, PRG0."""
import importlib.util
import shutil
from functools import cache
from itertools import pairwise
from pathlib import Path
from types import ModuleType

import pytest

from tests.emulator import (
    CONTINUE_MODE,
    CONTROLLER_2_SHIFT,
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    INV_BOMBS,
    INV_BOOMERANG,
    INV_RECORDER,
    LEVEL_1_MOUTH_X,
    LEVEL_1_TRIFORCE,
    MENU_OPEN,
    MENU_STATE,
    OBJ_STATE,
    OBJ_X,
    PAUSED,
    ROOM_ITEM_SLOT,
    SELECTED_ITEM_SLOT,
    TRIFORCE_FANFARE_ACTIVE,
    Button,
    Emulator,
    Mode,
)
from tests.test_feature_patches import (
    BOMB_SLOT,
    BOOMERANG_SLOT,
    CYCLING_LABEL,
    HOT_KEY_LABEL,
    HOT_KEY_MODE,
    INVENTORY_HEADING,
    ITEM_SPOT_ON_LINKS_PATH,
    LEVEL_1_START_ROOM,
    PAUSING_LABEL,
    RECORDER_SLOT,
    _door_redraw_during_fanfare,
    vanilla,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.feature_data import write_fixed_feature_data
from zora.model.enums import Item, RoomAction
from zora.rom.base_rom import Piece, piece_length
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

REPO = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _module("player_settings_build", REPO / "asm" / "settings" / "build.py")
data = build.load_data()

# CPU RAM (src/Variables.inc)
IS_UPDATING_MODE = 0x11
TILE_BUF_SELECTOR = 0x14
CUR_PPU_MASK = 0xFE
GRAYSCALE = 0x01                     # CurPpuMask_2001 bit
ENDING_BACKGROUND_COLOUR = 0x315     # DynTileBuf+19
ITEM_TYPE_TO_LIFT = 0x505
ITEM_LIFT_TIMER = 0x506
SONG_REQUEST = 0x600
TUNE0, EFFECT, TUNE1, SAMPLE, SONG = 0x605, 0x606, 0x607, 0x608, 0x609
HOT_KEY_LABEL_RECORD = range(0x6C7F, 0x6C88)   # FP-HOT-01's WRAM record (docs/rom-map.md)

# Songs (SongRequest / Song values)
OVERWORLD_SONG, UNDERWORLD_SONG, LEVEL_9_SONG = 0x01, 0x40, 0x20
AREA_SONGS = {OVERWORLD_SONG, UNDERWORLD_SONG, LEVEL_9_SONG}
TITLE_SONG = 0x80
ITEM_SONG = 0x08

WIN_GAME_MODE = 0x13
END_LEVEL_MODE = 0x12
LEVEL_PALETTE, WHITE_PALETTE = 0x18, 0x78        # TileBufSelector values of the flashes
ENDING_FLASH_START = 0x40                        # ItemLiftTimer value the flash waits for
ENDING_FLASH_END = 0xC0
PRG0_ENDING_COLOURS = {0x0F, 0x12, 0x16, 0x2A}
BLACK = 0x0F
WHITE_PIXEL_LEVEL = 230
FLASH_PIXELS = 10_000                # white pixels in a frame of the white palette (PRG0: about 42,000)
LIFT_FRAMES = 0x80
NONE = Button(0)
WOODEN_SWORD_ITEM = 0x01             # any liftable item type
CONTROL_SEED = 1                     # the title's seed number in the control ROMs


# --- ROMs -----------------------------------------------------------------------

@cache
def zora_rom(start_room_item: Item | None = None) -> bytes:
    """The current ZORA output on PRG0's world (code patches and the B10
    data that comes with them, as generate_rom writes it), optionally with
    an item on Link's path in level 1's start room; the Triforce of Power
    comes with the last-boss trigger, as Ganon leaves it."""
    world = parse_rom(vanilla())
    if start_room_item is not None:
        room = next(level for level in world.levels if level.level_num == 1).block.room(LEVEL_1_START_ROOM)
        room.item = start_room_item
        room.item_position = ITEM_SPOT_ON_LINKS_PATH
        if start_room_item == Item.TRIFORCE_OF_POWER:
            room.room_action = RoomAction.LAST_BOSS
    write_fixed_feature_data(world, CONTROL_SEED)
    return serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=True))


def with_settings(rom: bytes, **chosen: str) -> bytes:
    return bytes(build.apply_settings(rom, chosen, data.SETTINGS))


@cache
def finished(seed: int) -> bytes:
    """ZORA's output for the MVP baseline flags and `seed`."""
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, vanilla()).rom


def _setting_bytes(name: str) -> set[int]:
    runs = next(iter(data.SETTINGS[name].values()))
    return written(runs)


def written(runs: tuple[tuple[int, Piece], ...]) -> set[int]:
    """The file offsets a choice's (file offset, piece) writes cover."""
    return {offset + i for offset, piece in runs for i in range(piece_length(piece))}


def _hold(emu: Emulator, controller_1: Button, controller_2: Button = NONE, frames: int = 2) -> None:
    """Hold buttons on both controllers for `frames` frames, then release."""
    emu.nes.controller = int(controller_2) << CONTROLLER_2_SHIFT | int(controller_1)
    for _ in range(frames):
        emu.nes.step(1)
    emu.frames += frames
    emu.nes.controller = 0


# --- the build and its bytes -------------------------------------------------------

def test_data_matches_a_fresh_build() -> None:
    """asm/settings/player_settings_data.py is what the choice folders assemble to,
    on top of the whole of asm/series.txt."""
    if not (shutil.which("ca65") and shutil.which("ld65") and build.tool.DISASSEMBLY_REPO.is_dir()):
        pytest.skip("ca65/ld65 or the pinned disassembly missing")
    vanilla()
    _, writes = build.build_all()
    assert build.render(writes) == build.OUTPUT.read_text()


def test_every_choice_writes_the_same_bytes_and_settings_never_share_one() -> None:
    """Each choice of a setting writes the same offsets (so any choice can
    replace any other), and no two settings write the same byte, so they
    combine freely."""
    claimed: set[int] = set()
    for name, choices in data.SETTINGS.items():
        layouts = {frozenset(written(runs)) for runs in choices.values()}
        assert len(layouts) == 1, name
        assert not _setting_bytes(name) & claimed, name
        claimed |= _setting_bytes(name)


def test_zora_output_holds_every_default() -> None:
    """FP-SET-01: at the defaults the settings' bytes equal ZORA's current
    output (three finished seeds), so wiring them in at the defaults changes
    nothing, and no seed-varying write lands on them."""
    for seed in (1, 2, 3):
        rom = finished(seed)
        for name, default in data.DEFAULTS.items():
            assert build.held_choices(rom, name, data.SETTINGS) == [default], (seed, name)


def test_music_off_code_sits_in_free_space() -> None:
    """Music off's routine goes in bank 0 at $A000 (0x02010), which is $FF
    in PRG0 and in ZORA's output (docs/player-settings-patches.md)."""
    for rom in (vanilla(), finished(1)):
        assert build.music_off_space_is_blank(rom, data.SETTINGS)


def test_ported_bytes_are_written_as_given() -> None:
    """The ported byte lists: the death-warp test at 0x140EA-0x140F1 per
    choice, and reduce flashing's sites 1 to 3; PRG0's site-4 store (ZORA's
    FP-FIX-02 JMP) is not touched, since site 4 goes inside ZORA's own
    FP-FIX-02 code (tested in the emulator)."""
    death_warp_test = {
        "controller2_up_a": "a5fb2988c988d011",
        "controller1_up_a": "a5fa2988c988d011",
        "controller1_up_select": "a5fa2928c928d011",
    }
    for choice, test_bytes in death_warp_test.items():
        sites = build.ported_sites(with_settings(zora_rom(), death_warp=choice))
        assert sites["death-warp test"] == test_bytes
    prg0 = build.ported_sites(vanilla())
    assert prg0["death-warp test"] == death_warp_test["controller2_up_a"]
    flash_sites = {"flash site 1": ("8414", "eaea"),
                   "flash site 2": ("0f12162a", "0f0f0f0f"),
                   "flash site 3": ("85fe", "eaea")}
    off = build.ported_sites(with_settings(zora_rom(), reduce_flashing="off"))
    on = build.ported_sites(with_settings(zora_rom(), reduce_flashing="on"))
    for site, (off_bytes, on_bytes) in flash_sites.items():
        assert (prg0[site], off[site], on[site]) == (off_bytes, off_bytes, on_bytes), site
    zora = build.ported_sites(zora_rom())
    assert on["flash site 4 in PRG0"] == zora["flash site 4 in PRG0"] != prg0["flash site 4 in PRG0"]


# --- Select swap, swap-only (FP-HOT-01) ------------------------------------------------

def _armed_start(rom: bytes) -> Emulator:
    """A new file holding the boomerang, bombs and the recorder, facing up."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(8, Button.UP)
    emu[INV_BOOMERANG] = 1
    emu[INV_BOMBS] = 4
    emu[INV_RECORDER] = 1
    emu.run(5)
    return emu


def _select_presses(emu: Emulator, count: int) -> list[tuple[int, int]]:
    """(SelectedItemSlot, the highest Paused seen) after each Select press."""
    states = []
    for _ in range(count):
        paused = 0
        for buttons, frames in ((Button.SELECT, 2), (Button(0), 6)):
            for _ in range(frames):
                emu.run(1, buttons)
                paused = max(paused, emu[PAUSED])
        states.append((emu[SELECTED_ITEM_SLOT], paused))
    return states


SWAP_CYCLE = [(BOMB_SLOT, 0), (RECORDER_SLOT, 0), (BOOMERANG_SLOT, 0)]


def test_swap_only_select_cycles_and_never_pauses() -> None:
    """Swap-only: each new Select press in play selects the next owned B
    item in slot order and wraps after the last, and Paused stays 0 on
    every frame. Controls: PRG0 pauses and unpauses; ZORA's toggle choice
    cycles the same way in a new file."""
    assert _select_presses(_armed_start(vanilla()), 2) == [(BOOMERANG_SLOT, 1), (BOOMERANG_SLOT, 0)]
    assert _select_presses(_armed_start(zora_rom()), 3) == SWAP_CYCLE
    swap = _armed_start(with_settings(zora_rom(), select_swap="swap_only"))
    assert _select_presses(swap, 6) == SWAP_CYCLE * 2


def test_swap_only_item_screen_is_prg0s() -> None:
    """Swap-only: the item screen draws PRG0's nine-tile heading, and a
    Select press there changes nothing (heading, saved mode byte, B item);
    the WRAM label record of the toggle choice is never written. Control:
    the toggle choice shows its label and toggles."""
    toggle = _armed_start(zora_rom())
    toggle.open_item_screen()
    assert toggle.nametable(*HOT_KEY_LABEL) == CYCLING_LABEL
    toggle.press(Button.SELECT, after=10)
    assert toggle.nametable(*HOT_KEY_LABEL) == PAUSING_LABEL

    swap = _armed_start(with_settings(zora_rom(), select_swap="swap_only"))
    record_before = [swap[address] for address in HOT_KEY_LABEL_RECORD]
    swap.open_item_screen()
    assert swap.nametable(*HOT_KEY_LABEL) == INVENTORY_HEADING
    before = (swap[HOT_KEY_MODE], swap[SELECTED_ITEM_SLOT])
    swap.press(Button.SELECT, after=10)
    assert swap.nametable(*HOT_KEY_LABEL) == INVENTORY_HEADING
    assert (swap[HOT_KEY_MODE], swap[SELECTED_ITEM_SLOT]) == before
    assert [swap[address] for address in HOT_KEY_LABEL_RECORD] == record_before


def test_swap_only_keeps_no_state_across_save_and_reload() -> None:
    """Swap-only: after SAVE, a reset and a reload Select still cycles
    without pausing, even for a file the toggle choice saved in its
    pausing mode (the mode byte is ignored, so old and new files behave
    the same)."""
    swap_rom = with_settings(zora_rom(), select_swap="swap_only")
    swap = _armed_start(swap_rom)
    swap.open_item_screen()
    swap.save_and_reload()
    swap.run(8, Button.UP)
    assert _select_presses(swap, 3) == SWAP_CYCLE

    toggle = _armed_start(zora_rom())
    toggle.open_item_screen()
    toggle.press(Button.SELECT, after=10)          # the pausing mode, saved
    toggle.save_and_reload()
    assert toggle[HOT_KEY_MODE] == 1
    old_file = Emulator(swap_rom)
    old_file.load(toggle.save())
    old_file.reset()
    old_file.boot_to_file_select()
    old_file.start_game()
    old_file.run(8, Button.UP)
    assert old_file[HOT_KEY_MODE] == 1
    assert _select_presses(old_file, 3) == SWAP_CYCLE


# --- Music off (FP-SET-04) -------------------------------------------------------------

def _music_tour(music: str) -> dict[str, list[tuple[int, ...]]]:
    """One script, per scene the per-frame (Song, Tune0, Effect, Tune1,
    Sample): the title screen; the overworld; level 1 (entered by the
    recorder: its tune and the whirlwind); an item lift with the item song,
    to its end (PRG0 restarts the level's song); the Triforce of Power taken,
    through its fanfare (PRG0 restarts level 9's song); walking out to the
    overworld; and level 9 loaded."""
    emu = Emulator(with_settings(zora_rom(Item.TRIFORCE_OF_POWER), music=music))
    tour: dict[str, list[tuple[int, ...]]] = {}

    def watch(scene: str, frames: int, buttons: Button = NONE) -> None:
        for _ in range(frames):
            emu.run(1, buttons)
            tour.setdefault(scene, []).append(tuple(emu[a] for a in (SONG, TUNE0, EFFECT, TUNE1, SAMPLE)))

    watch("title", 120)
    emu.boot_to_file_select()
    emu.register_file()
    emu.start_game()
    watch("overworld", 60)
    emu.walk_into_level_1()
    watch("level 1", 30)
    emu[ITEM_TYPE_TO_LIFT] = WOODEN_SWORD_ITEM
    emu[ITEM_LIFT_TIMER] = LIFT_FRAMES
    emu[SONG_REQUEST] = ITEM_SONG                # as TakeItem does in a cellar
    watch("item lift", LIFT_FRAMES + 60)
    emu[OBJ_STATE + ROOM_ITEM_SLOT] = 0          # Ganon_ActivateRoomItem
    for _ in range(300):
        if emu[TRIFORCE_FANFARE_ACTIVE]:
            break
        watch("power fanfare", 1, Button.UP)
    watch("power fanfare", 400)
    watch("back to the overworld", 400, Button.DOWN)
    emu.play_recorder(LEVEL_1_TRIFORCE)
    emu.run_until(lambda: emu[OBJ_X] <= LEVEL_1_MOUTH_X, buttons=Button.LEFT)
    emu.run_until(lambda: emu.mode == Mode.LOAD_LEVEL, buttons=Button.UP, limit=1000)
    emu[CUR_LEVEL] = 9
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=1000)
    watch("level 9", 60)
    return tour


def test_music_off_silences_only_the_area_songs() -> None:
    """Music off: Song (RAM $0609) is never an area song ($01, $40, $20) on
    any frame: not on the overworld, in level 1 or level 9, nor where PRG0
    restarts one (after the item song, after the Triforce of Power fanfare,
    on leaving the level). The title song ($80) and the item song ($08)
    still play, and the item song ends in silence. Every other sound
    channel (Tune0, Effect, Tune1, Sample) runs frame for frame as with
    music on. Control: music on (ZORA's output) plays each area song."""
    on, off = _music_tour("on"), _music_tour("off")
    songs_on = {scene: {frame[0] for frame in frames} for scene, frames in on.items()}
    songs_off = {scene: {frame[0] for frame in frames} for scene, frames in off.items()}
    assert TITLE_SONG in songs_on["title"] and TITLE_SONG in songs_off["title"]
    assert songs_on["overworld"] == {OVERWORLD_SONG}
    assert songs_on["level 1"] == {UNDERWORLD_SONG}
    assert {ITEM_SONG, UNDERWORLD_SONG} <= songs_on["item lift"]
    assert on["item lift"][-1][0] == UNDERWORLD_SONG
    assert on["power fanfare"][-1][0] == LEVEL_9_SONG
    assert on["back to the overworld"][-1][0] == OVERWORLD_SONG
    assert songs_on["level 9"] == {LEVEL_9_SONG}

    for scene, songs in songs_off.items():
        assert not songs & AREA_SONGS, scene
    assert ITEM_SONG in songs_off["item lift"] and off["item lift"][-1][0] == 0
    for scene in ("overworld", "level 1", "power fanfare", "back to the overworld", "level 9"):
        assert songs_off[scene] == {0}, scene
    for scene in on:
        assert [frame[1:] for frame in on[scene]] == [frame[1:] for frame in off[scene]], scene


# --- Death-warp mapping (FP-RESET-01) ------------------------------------------------

UP_A = Button.UP | Button.A
UP_SELECT = Button.UP | Button.SELECT
INPUTS = {                                    # (controller 1, controller 2)
    "controller 2 Up+A": (NONE, UP_A),
    "controller 1 Up+A": (UP_A, NONE),
    "controller 1 Up+Select": (UP_SELECT, NONE),
    "Up alone": (Button.UP, NONE),
    "A alone": (Button.A, NONE),
    "Select alone": (Button.SELECT, NONE),
}
WARP_INPUT = {
    "controller2_up_a": "controller 2 Up+A",
    "controller1_up_a": "controller 1 Up+A",
    "controller1_up_select": "controller 1 Up+Select",
}


def _warps(rom: bytes, item_screen: bool) -> dict[str, bool]:
    """For each input: does holding it two frames (item screen open and at
    rest, or in play) end the game mode? Ending checks GameMode 8 (the
    Continue question); not ending checks GameMode 5 and, on the item
    screen, MenuState still 8."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(8, Button.UP)
    if item_screen:
        emu.open_item_screen()
        assert emu[MENU_STATE] == MENU_OPEN
    start = emu.save()
    result = {}
    for name, (controller_1, controller_2) in INPUTS.items():
        emu.load(start)
        _hold(emu, controller_1, controller_2)
        emu.run(10)
        if emu.mode == CONTINUE_MODE:
            result[name] = True
        else:
            assert emu.mode == Mode.PLAY, name
            assert not item_screen or emu[MENU_STATE] == MENU_OPEN, name
            result[name] = False
    return result


def test_death_warp_each_choice_answers_only_its_combination() -> None:
    """Each choice ends the game from the open item screen on exactly its
    own combination (controller 2 Up+A, controller 1 Up+A, controller 1
    Up+Select), and on no other input; during play no input ends it.
    Control: PRG0 answers controller 2 Up+A, as choice 0."""
    assert _warps(vanilla(), item_screen=True) == {name: name == "controller 2 Up+A" for name in INPUTS}
    for choice, combination in WARP_INPUT.items():
        rom = with_settings(zora_rom(), death_warp=choice)
        assert _warps(rom, item_screen=True) == {name: name == combination for name in INPUTS}, choice
        assert not any(_warps(rom, item_screen=False).values()), choice


def test_death_warp_silences_the_music() -> None:
    """The warp silences the music, as PRG0's: Song is 0 on the Continue
    screen (controller 1 Up+A, the default)."""
    emu = Emulator(with_settings(zora_rom(), death_warp="controller1_up_a"))
    emu.new_game()
    emu.run(8, Button.UP)
    assert emu[SONG] == OVERWORLD_SONG
    emu.open_item_screen()
    _hold(emu, UP_A)
    emu.run(10)
    assert (emu.mode, emu[SONG]) == (CONTINUE_MODE, 0)


def _up_then_select(rom: bytes) -> tuple[int, int, int]:
    """Item screen of a new file: press Select alone, then hold Up and
    press Select. Return the hot-key mode after the first press, and
    GameMode and the mode after the second."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(8, Button.UP)
    emu.open_item_screen()
    emu.press(Button.SELECT, after=10)
    first = emu[HOT_KEY_MODE]
    _hold(emu, Button.UP, frames=3)
    _hold(emu, UP_SELECT)
    emu.run(10)
    return first, emu.mode, emu[HOT_KEY_MODE]


def test_death_warp_up_select_takes_precedence_over_the_toggle() -> None:
    """Choice 2 with the toggle choice of Select swap: Select alone toggles
    the mode (0 to 1); Select with Up held ends the game and leaves the mode
    at 1. Control: the three ported bytes alone (without ZORA's precedence
    check in its FP-HOT-01 item-screen code) end the game and toggle the
    mode back to 0."""
    ported_only = build.apply_ported_bytes_only(zora_rom(), data.SETTINGS)
    assert _up_then_select(ported_only) == (1, CONTINUE_MODE, 0)
    rom = with_settings(zora_rom(), death_warp="controller1_up_select")
    assert _up_then_select(rom) == (1, CONTINUE_MODE, 1)


# --- Reduce flashing (FP-FIX-02) --------------------------------------------------------

def _white_pixels(emu: Emulator) -> int:
    return int((emu.last_frame > WHITE_PIXEL_LEVEL).all(axis=2).sum())


def _fanfare(rom: bytes, active: int, mode: int | None) -> tuple[set[int], int]:
    """Walk up level 1's start room to the item on Link's path and take it;
    while the sequence runs (GameMode `mode`, or TriforceFanfareActive set),
    return the TileBufSelector values seen and the most white pixels in a
    frame."""
    emu = Emulator(rom)
    emu.new_game()
    emu.walk_into_level_1()
    emu[OBJ_STATE + ROOM_ITEM_SLOT] = 0          # activate the item (a last-boss trigger)
    def running() -> bool:
        return emu.mode == mode if mode is not None else emu[TRIFORCE_FANFARE_ACTIVE] == active

    selectors, white = set(), 0
    for _ in range(600):
        emu.run(1, Button.UP if emu.mode == Mode.PLAY and not running() else Button(0))
        if running():
            selectors.add(emu[TILE_BUF_SELECTOR])
            white = max(white, _white_pixels(emu))
    return selectors, white


def test_reduce_flashing_level_end() -> None:
    """Site 1: taking a Triforce piece starts the end-of-level sequence
    (GameMode $12). Off: TileBufSelector receives the white palette ($78)
    and frames turn white. On: it never does, and no frame is white."""
    off = _fanfare(with_settings(zora_rom(Item.TRIFORCE), reduce_flashing="off"), 0, END_LEVEL_MODE)
    on = _fanfare(with_settings(zora_rom(Item.TRIFORCE), reduce_flashing="on"), 0, END_LEVEL_MODE)
    assert WHITE_PALETTE in off[0] and off[1] > FLASH_PIXELS
    assert WHITE_PALETTE not in on[0] and LEVEL_PALETTE not in on[0] and on[1] < FLASH_PIXELS


def test_reduce_flashing_power_triforce_fanfare() -> None:
    """Site 4 (in ZORA's own FP-FIX-02 code): during the Triforce of Power
    fanfare. Off: TileBufSelector receives $18 and $78 and frames turn
    white. On: neither is ever selected and no frame is white."""
    rom = zora_rom(Item.TRIFORCE_OF_POWER)
    off = _fanfare(with_settings(rom, reduce_flashing="off"), 1, None)
    on = _fanfare(with_settings(rom, reduce_flashing="on"), 1, None)
    assert {LEVEL_PALETTE, WHITE_PALETTE} <= off[0] and off[1] > FLASH_PIXELS
    assert not on[0] & {LEVEL_PALETTE, WHITE_PALETTE} and on[1] < FLASH_PIXELS


def _ending_colours(rom: bytes) -> list[int]:
    """Run the win sequence's flash (GameMode $13, submode 0, entered at its
    update) and return the background colour entry ($0315) on each frame
    from $40 frames on."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(10)
    emu[GAME_MODE] = WIN_GAME_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = 0
    emu[ITEM_LIFT_TIMER] = 0
    colours = []
    for _ in range(ENDING_FLASH_END - 1):
        emu.run(1)
        if emu[ITEM_LIFT_TIMER] >= ENDING_FLASH_START:
            colours.append(emu[ENDING_BACKGROUND_COLOUR])
    return colours


def test_reduce_flashing_ending() -> None:
    """Site 2: off, the ending's background colour cycles $0F, $12, $16,
    $2A one per frame; on, it stays black ($0F)."""
    off = _ending_colours(with_settings(zora_rom(), reduce_flashing="off"))
    on = _ending_colours(with_settings(zora_rom(), reduce_flashing="on"))
    assert set(off) == PRG0_ENDING_COLOURS and off[:4] == [0x0F, 0x12, 0x16, 0x2A]
    assert set(on) == {BLACK}


def _bomb_grayscale_changes(rom: bytes) -> int:
    """Place a bomb in play and count the changes of the grayscale bit of
    CurPpuMask_2001 through the explosion."""
    emu = Emulator(rom)
    emu.new_game()
    emu.run(8, Button.UP)
    emu[INV_BOMBS] = 4
    emu[SELECTED_ITEM_SLOT] = BOMB_SLOT
    emu.run(5)
    emu.press(Button.B, after=0)
    masks = []
    for _ in range(120):
        emu.run(1)
        masks.append(emu[CUR_PPU_MASK] & GRAYSCALE)
    return sum(1 for before, after in pairwise(masks) if before != after)


def test_reduce_flashing_bomb() -> None:
    """Site 3: off, the explosion toggles grayscale four times; on, never."""
    assert _bomb_grayscale_changes(with_settings(zora_rom(), reduce_flashing="off")) == 4
    assert _bomb_grayscale_changes(with_settings(zora_rom(), reduce_flashing="on")) == 0


def test_reduce_flashing_keeps_fp_fix_02_door_redraw() -> None:
    """With the setting on, FP-FIX-02's purpose holds: a door opened during
    the Triforce of Power fanfare is drawn, as without the fanfare."""
    rom = with_settings(zora_rom(), reduce_flashing="on")
    before, opened = _door_redraw_during_fanfare(rom, fanfare=False)
    assert before != opened
    assert _door_redraw_during_fanfare(rom, fanfare=True)[1] == opened
