"""DeathLink (docs/design/archipelago-items.md piece 2; docs/reports/research-ap-item-codes-and-deathlink.md
section 2): client-only, in client_step.

On hand-made RAM: a death is sent once, the first poll in mode $11, with the level the status bar
shows; not sent back when this client applied it; the latch holds through the Continue screen. A
received death is applied with @HandleDied's stores and its guards, before any item; it waits through
a transition, a cave, the recorder, a whirlwind, the fanfare and a heart refill; several make one;
it is dropped with no file in play and while Link is already dying, never applied after the goal.

In the emulator (cynes), on PRG0 and PRG1 (the report's section 2.7 pass): a received death on the
overworld and in a level room ends in the Continue screen with the death counted, and is not sent
back; one received during a scroll waits for play; Continue afterward plays on; a real death (Zelda's
guard fire) is sent once, naming level 9 as the status bar shows it."""
import json
from collections.abc import Callable
from functools import cache

import pytest

from tests import test_progressive_emulator as hand_placed
from tests.emulator import CONTINUE_MODE, OBJ_X, OBJ_Y, Button, Mode
from tests.test_archipelago_client_ram import (
    FRAGILE_HEARTS,
    GUARD_FIRE_SLOT,
    LINK_INVINCIBILITY_TIMER,
    NEW_FILE_HEARTS,
    SETTLE_FRAMES,
    built,
    enter_zelda_room,
)
from tests.test_archipelago_client_step import (
    HEARTS,
    STARTING_HEARTS,
    TABLES,
    guarded_write,
    loaded,
    result,
    state_of,
    step,
)
from zora import archipelago
from zora.archipelago import (
    CUR_LEVEL,
    DEATH_MODE,
    HEART_PARTIAL,
    NO_MEMORY,
    ClientMemory,
    ClientTables,
    Decision,
    ReceivedItem,
    ServerView,
    client_step,
    death_cause,
    death_received,
)
from zora.generate.pipeline import finish
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

PENDING = death_received(NO_MEMORY)
DEATH_COUNTS = 0x0630                    # DeathCounts, one per save slot
LINK_DIR = 0x98
LEVEL_SHOWN = {1: 1, 3: 7, 9: 9}         # hand-made: CurLevel 3 shows as level 7
LEVEL_TABLES = ClientTables(TABLES.checks, TABLES.rules, TABLES.arrival_sound, LEVEL_SHOWN)


def dying(mode: int = DEATH_MODE, changes: dict[int, int] | None = None) -> dict[int, int]:
    return loaded({inventory.GAME_MODE: mode, inventory.IS_UPDATING_MODE: 1} | (changes or {}))


# --- hand-made RAM ------------------------------------------------------------------------------------

def test_the_state_bytes_cover_the_guards_and_the_level() -> None:
    assert {CUR_LEVEL, *archipelago.DEATH_STATE} <= set(archipelago.STATE_ADDRESSES)
    assert {archipelago.HEART_VALUES, HEART_PARTIAL} <= set(TABLES.addresses())


def test_a_death_is_sent_once_with_the_level_shown() -> None:
    ram = dying(changes={CUR_LEVEL: 3})
    first = client_step(ram, state_of(ram), ServerView(), LEVEL_TABLES, NO_MEMORY)
    assert first.send_death and first.death_level == 7 and first.writes == ()
    again = client_step(ram, state_of(ram), ServerView(), LEVEL_TABLES, first.memory)
    assert not again.send_death                                                # latched
    continuing = dying(CONTINUE_MODE)
    held = client_step(continuing, state_of(continuing), ServerView(), LEVEL_TABLES, again.memory)
    assert not held.send_death and held.memory.dead_latched                   # through the Continue screen
    played = step(loaded(), ServerView(), held.memory)
    assert not played.memory.dead_latched                                     # cleared in play
    later = client_step(ram, state_of(ram), ServerView(), LEVEL_TABLES, played.memory)
    assert later.send_death                                                   # the next death is sent


def test_the_cause_text() -> None:
    overworld = dying(changes={CUR_LEVEL: 0})
    assert client_step(overworld, state_of(overworld), ServerView(), LEVEL_TABLES).death_level is None
    assert death_cause("Gob", 7) == "Gob ran out of hearts in Level 7."
    assert death_cause("Gob", None) == "Gob ran out of hearts."
    unknown = dying(changes={CUR_LEVEL: 5})                                   # tables that predate the map
    assert client_step(unknown, state_of(unknown), ServerView(), LEVEL_TABLES).death_level is None


def test_a_received_death_is_applied_with_its_guards_and_not_sent_back() -> None:
    ram = loaded({HEARTS: 0x52, HEART_PARTIAL: 0x80, inventory.LINK_STATE: 0x01, LINK_DIR: 0x08})
    decision = step(ram, ServerView((ReceivedItem("Ladder"),)), PENDING)
    assert decision.applies_death and decision.gives is None                  # before the item
    assert decision.writes == ((HEARTS, 0x50), (inventory.IS_UPDATING_MODE, 0), (inventory.GAME_SUBMODE, 0),
                               (HEART_PARTIAL, 0), (inventory.LINK_STATE, 0), (inventory.GAME_MODE, DEATH_MODE),
                               (LINK_DIR, 0x04))
    guards = dict(decision.guards)
    assert set(guards) == {*archipelago.RECEIVE_STATE, *archipelago.DEATH_STATE, *archipelago.GOAL_STATE, HEARTS,
                           inventory.CUR_PPU_CONTROL}
    assert all(guards[address] == 0 for address in archipelago.DEATH_STATE) and guards[HEARTS] == 0x52
    assert not decision.memory.pending_death and decision.memory.death_applied
    assert guarded_write(ram, decision)
    echo = step(ram, ServerView(), decision.memory)
    assert not echo.send_death and echo.memory.dead_latched                   # its own death, never sent back


@pytest.mark.parametrize("waiting", [
    {inventory.GAME_MODE: 0x07}, {inventory.GAME_MODE: 0x0B}, {inventory.PAUSED: 1}, {inventory.MENU_STATE: 1},
    {archipelago.FLUTE_TIMER: 0x20}, {archipelago.WHIRLWIND_TELEPORTING: 1},
    {archipelago.TRIFORCE_FANFARE_ACTIVE: 1}, {archipelago.FILLING_HEARTS: 1}, {archipelago.BRIGHTENING_ROOM: 1},
    {inventory.ITEM_LIFT_TIMER: 0x10}, {inventory.LINK_STATE: inventory.HALTED},
    {inventory.CUR_PPU_CONTROL: 0x30}])                                      # a frame that lags
def test_a_received_death_waits(waiting: dict[int, int]) -> None:
    ram = loaded(waiting)
    decision = step(ram, ServerView(), PENDING)
    assert not decision.applies_death and decision.writes == ()
    assert decision.memory.pending_death                                      # still pending
    assert step(loaded(), ServerView(), decision.memory).applies_death


def test_a_failed_guard_keeps_it_pending() -> None:
    ram = loaded()
    decision = step(ram, ServerView(), PENDING)
    ram[archipelago.FLUTE_TIMER] = 1                                          # after the read, before the write
    assert not guarded_write(ram, decision)
    assert ram[HEARTS] == STARTING_HEARTS                                      # the wrapper keeps PENDING
    ram[archipelago.FLUTE_TIMER] = 0
    assert step(ram, ServerView(), PENDING).applies_death


def test_several_deaths_make_one() -> None:
    twice = death_received(death_received(NO_MEMORY))
    assert twice == PENDING
    ram = loaded()
    decision = step(ram, ServerView(), twice)
    assert guarded_write(ram, decision)
    assert not step(loaded(), ServerView(), decision.memory).applies_death


def test_no_file_in_play_drops_it_and_a_transition_does_not() -> None:
    title = dict.fromkeys(TABLES.addresses(), 0)
    dropped = step(title, ServerView(), PENDING)
    assert not dropped.readable and not dropped.memory.pending_death
    transition = loaded()
    after = state_of(loaded({inventory.GAME_MODE: 0x07}))                     # the mode changed between reads
    kept = step(transition, ServerView(), PENDING, after)
    assert not kept.readable and kept.memory.pending_death


@pytest.mark.parametrize("mode", [DEATH_MODE, CONTINUE_MODE])
def test_a_death_received_while_link_is_dying_is_dropped(mode: int) -> None:
    ram = dying(mode)
    decision = step(ram, ServerView(), replace_latched(PENDING))
    assert not decision.memory.pending_death and decision.writes == ()
    assert not step(loaded(), ServerView(), decision.memory).applies_death


def replace_latched(memory: ClientMemory) -> ClientMemory:
    return ClientMemory(memory.reported, memory.awaiting_count, memory.goal_sent, dead_latched=True,
                        death_applied=memory.death_applied, pending_death=memory.pending_death)


def test_never_after_the_goal() -> None:
    won = loaded({inventory.ZELDA_TYPE: inventory.ZELDA, inventory.ZELDA_STATE: 1})
    decision = step(won, ServerView(), PENDING)
    assert not decision.applies_death and decision.memory.pending_death


def test_the_level_numbers_travel_in_the_tables() -> None:
    data = json.loads(json.dumps(archipelago.client_tables_to_json(result())))
    tables = archipelago.client_tables_from_json(data)
    world = result().state.world
    assert dict(tables.level_numbers) == {level.level_num: level.rom_level_num for level in world.levels}
    older = {key: value for key, value in data.items() if key != "levelNumbers"}
    assert dict(archipelago.client_tables_from_json(older).level_numbers) == {}     # optional


# --- the emulator, PRG0 and PRG1 ----------------------------------------------------------------------

NO_BUTTONS = Button(0)
POLL_FRAMES = 8                          # the world polls every 0.125 s; more often here, to see each mode
DEATH_FRAMES = 900                       # mode $11 to the Continue screen, with room to spare
LEFT_EDGE, RIGHT_EDGE, TOP_EDGE, BOTTOM_EDGE = 0x00, 0xF0, 0x3D, 0xDD


def _base(revision: str) -> bytes:
    if revision == "prg0":
        return remember_repo_base_rom()
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"needs {PRG1_ROM_PATH.name}")
    remember_repo_base_rom()
    return PRG1_ROM_PATH.read_bytes()


@cache
def _rom(revision: str) -> bytes:
    return finish(built(), _base(revision))


@cache
def _tables() -> ClientTables:
    return archipelago.client_tables_of(result())


class Client:
    """The world's client on one console: client_step on a snapshot read in one frame, writes only
    through a guarded write, the memory kept only when it lands or there was nothing to write."""

    def __init__(self, game: hand_placed.Game, memory: ClientMemory = NO_MEMORY) -> None:
        self.game, self.memory = game, memory
        self.sent: list[str] = []
        self.applied = 0

    def poll(self) -> Decision:
        emu = self.game.emu
        tables = _tables()
        ram = {address: emu[address] for address in tables.addresses()}
        decision = client_step(ram, {address: ram[address] for address in tables.state_addresses},
                               ServerView(), tables, self.memory)
        if decision.send_death:
            self.sent.append(death_cause("Player", decision.death_level))
        if decision.writes:
            if any(emu[address] != value for address, value in decision.guards):
                return decision
            for address, value in decision.writes:
                emu[address] = value
            self.applied += decision.applies_death
        self.memory = decision.memory
        return decision

    def run(self, frames: int, buttons: Button = NO_BUTTONS) -> None:
        for frame in range(frames):
            self.game.emu.run(1, buttons)
            if frame % POLL_FRAMES == 0:
                self.poll()

    def run_until(self, until: Callable[[], bool], limit: int, buttons: Button = NO_BUTTONS) -> None:
        for frame in range(limit):
            if until():
                return
            self.game.emu.run(1, buttons)
            if frame % POLL_FRAMES == 0:
                self.poll()
        raise AssertionError("timed out")


def _game(revision: str) -> hand_placed.Game:
    game = hand_placed.Game(_rom(revision))
    game.emu[HEARTS] = NEW_FILE_HEARTS
    game.emu.run(SETTLE_FRAMES)
    return game


def _received_death_ends_in_continue(client: Client) -> None:
    emu = client.game.emu
    deaths = emu[DEATH_COUNTS + emu[inventory.CUR_SAVE_SLOT]]
    client.memory = death_received(client.memory)
    client.run_until(lambda: emu.mode == CONTINUE_MODE, DEATH_FRAMES)
    assert client.applied == 1 and client.sent == []                         # applied, never sent back
    assert emu[DEATH_COUNTS + emu[inventory.CUR_SAVE_SLOT]] == deaths + 1
    emu.run(20)
    while emu[inventory.GAME_SUBMODE] != hand_placed.CONTINUE_CHOICE:
        emu.press(Button.SELECT)
    emu.press(Button.START)
    client.game.wait_for_play()
    client.run(4 * POLL_FRAMES)
    assert emu.mode == Mode.PLAY and client.applied == 1 and client.sent == []
    assert not client.memory.dead_latched and not client.memory.death_applied


@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_received_death_on_the_overworld_and_in_a_room(revision: str) -> None:
    game = _game(revision)
    _received_death_ends_in_continue(Client(game))
    level = next(level for level in built().world.levels if level.level_num == 1)
    assert level.level_num == 1
    game.enter_level(1)
    game.emu.run(SETTLE_FRAMES)
    _received_death_ends_in_continue(Client(game))


SCROLL_WAIT = 60


def _start_a_scroll(game: hand_placed.Game) -> None:
    """Walk Link off an edge of the start screen, whichever edge opens, until the scroll begins."""
    start = game.emu.save()
    edges = ((OBJ_X, LEFT_EDGE, Button.LEFT), (OBJ_X, RIGHT_EDGE, Button.RIGHT), (OBJ_Y, TOP_EDGE, Button.UP),
             (OBJ_Y, BOTTOM_EDGE, Button.DOWN))
    for coordinate, edge, button in edges:
        game.emu.load(start)
        game.emu[coordinate] = edge
        try:
            game.emu.run_until(lambda: game.emu.mode != Mode.PLAY, limit=SCROLL_WAIT, buttons=button)
        except AssertionError:
            continue                                                          # a wall: try the next edge
        return
    raise AssertionError("no edge of the start screen scrolls")


@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_death_received_during_a_scroll_waits_for_play(revision: str) -> None:
    game = _game(revision)
    _start_a_scroll(game)
    client = Client(game, PENDING)
    waiting = client.poll()
    assert game.emu.mode != Mode.PLAY and client.applied == 0 and client.memory.pending_death, waiting
    client.run_until(lambda: game.emu.mode == CONTINUE_MODE, DEATH_FRAMES + 600)
    assert client.applied == 1 and client.sent == []


@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_real_death_is_sent_once(revision: str) -> None:
    game = _game(revision)
    frames: list[tuple[int, bool]] = []
    enter_zelda_room(game, frames)                                            # type: ignore[arg-type]
    client = Client(game)
    client.run(30)
    emu = game.emu
    emu[HEARTS] = FRAGILE_HEARTS
    emu[HEART_PARTIAL] = 0x01
    emu[LINK_INVINCIBILITY_TIMER] = 0
    fire = (emu[OBJ_X + GUARD_FIRE_SLOT], emu[OBJ_Y + GUARD_FIRE_SLOT])
    for _ in range(DEATH_FRAMES * 2):
        if emu.mode == CONTINUE_MODE:
            break
        if emu.mode == Mode.PLAY:
            emu[OBJ_X], emu[OBJ_Y] = fire
        client.run(1)
    assert emu.mode == CONTINUE_MODE
    client.run(4 * POLL_FRAMES)
    shown = next(level.rom_level_num for level in built().world.levels if level.level_num == 9)
    assert client.sent == [f"Player ran out of hearts in Level {shown}."] and client.applied == 0
