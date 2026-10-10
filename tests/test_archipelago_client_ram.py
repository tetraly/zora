"""Archipelago Phase 4c, items 2 and 3, in the emulator (zora/rom/inventory.py; docs/archipelago.md
"Interface", docs/rom-map.md "RAM"), on a ZORA-mode ROM with every ZORA flag on (fp-prog-01's
bought bits at $0677-$0679 and fp-hot-01's $067A beside it):
  - the received count, RECEIVED_COUNT ($067B, Items+$24): 0 in a new file (also one registered
    after another file saved a count); saved with the file and restored after save, reset and
    reload; kept on Continue; back to the saved value after a reset without saving; and nothing in
    play writes it (a sentinel survives the overworld, a level, a room item, a shop, the item
    screen, a death and the continue screen);
  - the client's loop (docs/archipelago.md): give item `count` and write count + 1 in the same
    writes, whenever may_receive; across saves, resets without saving and Continue, every
    received item is given exactly once;
  - goal_reached: false from power-on through the title, file select and play, in Zelda's room
    before Link reaches her and through a death there; true from the frame Link reaches her
    (Zelda's object leaves state 0) and through the ending (mode $13); false again on the title
    and file-select screens after a reset."""
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from tests import test_progressive_emulator as hand_placed
from tests.archipelago_cases import FLAG_CASES
from tests.emulator import (
    CONTINUE_MODE,
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    OBJ_STATE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    Button,
    Emulator,
    Mode,
)
from tests.test_assignment_emulator import Console, floor_room
from zora import archipelago
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.places import PlaceKind
from zora.model.enums import Enemy
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

REPO = Path(__file__).resolve().parent.parent
CASE = "every ZORA flag on"
SEED = 1
COUNT = archipelago.RECEIVED_COUNT
SENTINEL = 0xA5
LINK_INVINCIBILITY_TIMER = 0x4F0                 # ObjInvincibilityTimer, slot 0 (Link)
INVINCIBLE = 0xFF
DEATH_MODE = 0x11
WIN_GAME_MODE = 0x13
ZELDA_X, ZELDA_Y = 0x78, 0x95                    # UpdateZelda: X $70-$80 and Y $95 reach her
GUARD_FIRE_SLOT = 2
FRAGILE_HEARTS = 0x00                            # one container, no full heart: the next hit kills
HEART_PARTIAL = 0x670
NEW_FILE_HEARTS = 0x22                           # three containers, full
SETTLE_FRAMES = 30
CONTAINER_SHIFT = 4
CONTINUE_SCREEN_FRAMES = 20                      # as Emulator.save_and_reload waits
INVENTORY = range(inventory.ITEMS, inventory.MAX_BOMBS + 1)
# The server's list of this player's items, in order (the pool's own items, a heart container
# twice: one container and one heart each).
RECEIVED = ("Raft", "Book", "Heart Container", "Ladder", "Recorder", "Heart Container", "Magical Key")
HELD = {"Raft": 0x09, "Book": 0x0A, "Ladder": 0x0C, "Recorder": 0x05, "Magical Key": 0x0D}


@cache
def built() -> Built:
    flag_string, zora_flag_string = FLAG_CASES[CASE]
    return build(plan(flag_string, SEED, zora_flag_string), remember_repo_base_rom())


@cache
def zora_rom() -> bytes:
    return finish(built(), remember_repo_base_rom())


def ram(emu: Emulator, addresses: tuple[int, ...] | range) -> dict[int, int]:
    return {address: emu[address] for address in addresses}


class Game(hand_placed.Game):
    """hand_placed.Game on the ZORA-mode ROM."""

    def __init__(self) -> None:
        super().__init__(zora_rom())
        self.emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = NEW_FILE_HEARTS
        self.emu.run(SETTLE_FRAMES)                 # the item screen opens only after these

    def reset_and_reload(self) -> None:
        """The console's reset, then the saved file again."""
        self.emu.reset()
        self.emu.boot_to_file_select()
        self.emu.start_game()

    def continue_play(self) -> None:
        """The continue screen's Continue: from play by the item screen and Up+A, or from the
        continue screen a death leads to."""
        if self.emu.mode == CONTINUE_MODE:
            self.emu.run(CONTINUE_SCREEN_FRAMES)
            while self.emu[GAME_SUBMODE] != hand_placed.CONTINUE_CHOICE:
                self.emu.press(Button.SELECT)
            self.emu.press(Button.START)
        else:
            self.emu.run(SETTLE_FRAMES)
            self.continue_screen(hand_placed.CONTINUE_CHOICE)
        self.wait_for_play()


# --- the received count ------------------------------------------------------------------------

def test_a_new_file_starts_at_zero_also_after_another_file_saved_a_count() -> None:
    game = Game()
    assert game.emu[COUNT] == 0
    game.emu[COUNT] = 9
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    assert game.emu[COUNT] == 9
    game.emu.reset()
    game.emu.boot_to_file_select()
    game.emu.register_file()
    game.emu.start_game(1)
    assert game.emu[COUNT] == 0


def test_the_count_is_saved_and_restored() -> None:
    game = Game()
    game.emu[COUNT] = 3
    game.emu.open_item_screen()
    game.emu.save_and_reload()                   # save, reset, reload
    assert game.emu[COUNT] == 3
    game.emu[COUNT] = 5
    game.continue_play()                         # Continue keeps play's RAM
    assert game.emu[COUNT] == 5
    game.reset_and_reload()                      # unsaved: back to the saved count
    assert game.emu[COUNT] == 3


def test_nothing_in_play_writes_the_count() -> None:
    console = Console(zora_rom())
    console.emu[COUNT] = SENTINEL
    console.start = console.emu.save()
    seen: list[tuple[str, int]] = []

    def check(step: str) -> None:
        seen.append((step, console.emu[COUNT]))

    console.emu.play_recorder(0x01)                               # the overworld, the whirlwind
    check("recorder")
    room = floor_room(built())
    assert room.level is not None and room.room_num is not None
    console.enter_room(room.level, room.room_num)
    check("level")
    console.clear_monsters()
    console.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
    console.take_room_item()
    check("room item")
    ware = next(place for place in built().places if place.kind == PlaceKind.SHOP_WARE)
    console.enter_cave(ware.screens[0])
    console.take_ware(ware.position or 0)
    check("shop ware")
    console.emu.open_item_screen()
    console.emu.close_item_screen()
    check("item screen")
    game = Game()
    game.emu[COUNT] = SENTINEL
    die(game)
    check_game = game.emu[COUNT]
    game.continue_play()
    seen += [("death", check_game), ("continue", game.emu[COUNT])]
    assert all(value == SENTINEL for _step, value in seen), seen


def test_no_item_slot_and_no_zora_patch_reaches_the_count() -> None:
    """TakeItem's slots top out at $1F (Items+$24 is past them), and none of ZORA's patch sources
    names $067B (the disassembly has no label or literal there either: docs/rom-map.md)."""
    assert max(inventory.item_slots()) < COUNT - inventory.ITEMS
    named = re.compile(r"\$0?67B\b|Items\s*\+\s*\$24\b", re.IGNORECASE)
    sources = [path for path in (REPO / "asm").rglob("*") if path.suffix in {".s", ".asm", ".inc", ".py"}]
    if not sources:
        pytest.skip("asm/ is not in this tree")
    assert not [path for path in sources if named.search(path.read_text(errors="replace"))]


# --- the client's loop -------------------------------------------------------------------------

def client_frame(emu: Emulator, available: int) -> None:
    """One frame of the client (docs/archipelago.md "Interface"): when it may receive and the
    server has an item numbered `count`, give it and write count + 1 with the same writes."""
    if not archipelago.may_receive(ram(emu, archipelago.RECEIVE_STATE)):
        return
    count = emu[COUNT]
    if count >= available:
        return
    writes = archipelago.receive(RECEIVED[count], ram(emu, INVENTORY), archipelago.give_rules(
        archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom())))
    writes[COUNT] = count + 1
    for address, value in writes.items():
        emu[address] = value


def run_client(game: Game, available: int, frames: int = 120) -> None:
    for _ in range(frames):
        client_frame(game.emu, available)
        game.emu.run(1)


def expected(start: dict[str, int], given: int) -> dict[str, int]:
    held = dict(start)
    for name in RECEIVED[:given]:
        held[name] = held[name] + 1 if name == "Heart Container" else 1
    return held


def owned(emu: Emulator) -> dict[str, int]:
    """The received items held: each one's inventory byte, and the heart containers (the high
    nibble of HeartValues; its low nibble, the hearts filled, moves with damage)."""
    held = {name: emu[inventory.ITEMS + slot] for name, slot in HELD.items()}
    held["Heart Container"] = emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] >> CONTAINER_SHIFT
    return held


def test_every_item_is_given_exactly_once() -> None:
    game = Game()
    start = owned(game.emu)
    run_client(game, 3)
    assert (game.emu[COUNT], owned(game.emu)) == (3, expected(start, 3))
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    run_client(game, 3)
    assert (game.emu[COUNT], owned(game.emu)) == (3, expected(start, 3))
    run_client(game, 5)                          # two more, then a reset without saving
    assert (game.emu[COUNT], owned(game.emu)) == (5, expected(start, 5))
    game.reset_and_reload()
    assert (game.emu[COUNT], owned(game.emu)) == (3, expected(start, 3))
    run_client(game, len(RECEIVED))              # given again, once, in this save
    assert (game.emu[COUNT], owned(game.emu)) == (len(RECEIVED), expected(start, len(RECEIVED)))
    game.continue_play()
    run_client(game, len(RECEIVED))
    game.emu.open_item_screen()
    game.emu.save_and_reload()
    run_client(game, len(RECEIVED))
    assert (game.emu[COUNT], owned(game.emu)) == (len(RECEIVED), expected(start, len(RECEIVED)))


# --- the goal ----------------------------------------------------------------------------------

def goal(emu: Emulator) -> bool:
    return archipelago.goal_reached(ram(emu, archipelago.GOAL_STATE))


def zelda_room() -> int:
    level9 = next(level for level in built().world.levels if level.level_num == 9)
    return next(room.room_num for room in level9.rooms if room.enemy == Enemy.THE_KIDNAPPED)


def run_watching(emu: Emulator, until: Callable[[], bool], limit: int, frames: list[tuple[int, bool]]) -> None:
    """Run frame by frame until `until`, recording (game mode, goal) for each frame."""
    for _ in range(limit):
        if until():
            return
        emu.run(1)
        frames.append((emu[GAME_MODE], goal(emu)))
    raise AssertionError("timed out")


def run_frames(emu: Emulator, count: int, frames: list[tuple[int, bool]]) -> None:
    for _ in range(count):
        emu.run(1)
        frames.append((emu[GAME_MODE], goal(emu)))


def in_play(emu: Emulator) -> Callable[[], bool]:
    return lambda: emu.mode == Mode.PLAY and emu[hand_placed.IS_UPDATING_MODE] == 1


def enter_zelda_room(game: Game, frames: list[tuple[int, bool]]) -> None:
    game.emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = hand_placed.MANY_HEARTS
    game.emu[CUR_LEVEL] = 9
    game.start_mode(Mode.LOAD_LEVEL)
    run_watching(game.emu, in_play(game.emu), 900, frames)
    game.emu[ROOM_ID] = zelda_room()
    game.start_mode(hand_placed.ENTER_ROOM_MODE)
    run_watching(game.emu, in_play(game.emu), 900, frames)
    run_frames(game.emu, 5, frames)
    assert game.emu[inventory.ZELDA_TYPE] == inventory.ZELDA


def die(game: Game) -> list[tuple[int, bool]]:
    """Link killed by a guard fire in Zelda's room, to the continue screen."""
    frames: list[tuple[int, bool]] = []
    enter_zelda_room(game, frames)
    run_frames(game.emu, 30, frames)
    game.emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = FRAGILE_HEARTS
    game.emu[HEART_PARTIAL] = 0x01
    game.emu[LINK_INVINCIBILITY_TIMER] = 0
    fire = (game.emu[OBJ_X + GUARD_FIRE_SLOT], game.emu[OBJ_Y + GUARD_FIRE_SLOT])

    def touch_fire() -> bool:
        if game.emu.mode == Mode.PLAY:
            game.emu[OBJ_X], game.emu[OBJ_Y] = fire
        return game.emu.mode == CONTINUE_MODE
    run_watching(game.emu, touch_fire, 1500, frames)
    assert DEATH_MODE in {mode for mode, _ in frames}
    return frames


def test_the_goal_is_reached_when_zelda_is_rescued_and_never_before() -> None:
    frames: list[tuple[int, bool]] = []
    emu = Emulator(zora_rom())
    run_frames(emu, 120, frames)
    emu.boot_to_file_select()
    frames.append((emu[GAME_MODE], goal(emu)))
    emu.register_file()
    emu.start_game()
    game = Game.__new__(Game)
    game.emu, game.zora_flags = emu, ""
    run_frames(emu, 900, frames)                                         # play on the overworld
    enter_zelda_room(game, frames)
    game.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
    run_frames(emu, 120, frames)                                         # waiting in her room
    assert emu[OBJ_STATE + inventory.ZELDA_SLOT] == 0
    assert not any(reached for _mode, reached in frames)
    assert {Mode.TITLE, Mode.FILE_SELECT, Mode.PLAY} <= {mode for mode, _ in frames}

    rescue: list[tuple[int, bool]] = []
    emu[OBJ_X], emu[OBJ_Y] = ZELDA_X, ZELDA_Y
    run_watching(emu, lambda: emu[OBJ_STATE + inventory.ZELDA_SLOT] != 0, 10, rescue)
    assert goal(emu) and emu.mode == Mode.PLAY                  # from the moment she is reached
    run_watching(emu, lambda: emu.mode == WIN_GAME_MODE and len(rescue) > 400, 1200, rescue)
    assert all(reached for _mode, reached in rescue[1:])
    assert {Mode.PLAY, WIN_GAME_MODE} <= {mode for mode, _ in rescue}

    # After a reset: the first frame still holds the ending's RAM (the same won game) until the
    # reset routine clears it; the title and file-select screens never read as reached.
    after: list[tuple[int, bool]] = []
    emu.reset()
    run_frames(emu, 120, after)
    emu.boot_to_file_select()
    after.append((emu[GAME_MODE], goal(emu)))
    assert {Mode.TITLE, Mode.FILE_SELECT} <= {mode for mode, _ in after}
    assert not any(reached for mode, reached in after if mode != WIN_GAME_MODE)
    assert {mode for mode, reached in after if reached} <= {WIN_GAME_MODE}


def test_the_goal_is_not_reached_through_a_death_in_zeldas_room() -> None:
    game = Game()
    frames = die(game)
    game.continue_play()
    frames.append((game.emu[GAME_MODE], goal(game.emu)))
    assert not any(reached for _mode, reached in frames)
    assert {DEATH_MODE, CONTINUE_MODE} <= {mode for mode, _ in frames}
