"""client_step, the Archipelago client's decisions as one pure function (zora/archipelago.py,
docs/archipelago.md "client_step", docs/design/archipelago-client-step.md).

On hand-made RAM: the read plan, the JSON tables, the bracket (both reads of the state bytes must
hold the loaded file, with the same save slot and game mode), reports, the goal, one received item
per poll with its guards, the "already held" rule, receivable() and an item it cannot give
(counted, never raised), the awaited count, and a guarded write refused on purpose (the wrapper
keeps its memory, and the next poll gives the item exactly once).

In the emulator (cynes), a wrapper polls as the world does, about every 30 frames, reading the state
bytes, then each range, then the state bytes again, one read per frame, so a snapshot spans frames.
It applies writes only through a guarded write. Powered on with garbage RAM and a battery of two
files, it plays the first file (a room's item taken, a level loaded and left), saves, switches to
the second file and plays it: every report is a place the loaded file has taken, every write is
made in play, and each file gets each server item once, its own items found in it counted, not
given again."""
import json
from dataclasses import dataclass, field
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import Button, Emulator
from tests.test_archipelago_beta_smoke import back_to_the_overworld, take_floor_item
from tests.test_archipelago_checks_readable import (
    FILE_COUNTS,
    FILE_STRIDE,
    FILLS,
    PLAY_FRAMES,
    RAM_SIZE,
    SAVE_RAM,
    Watched,
    battery,
)
from tests.test_archipelago_checks_readable import checks as battery_checks
from tests.test_archipelago_client_ram import CASE, SEED, built, zora_rom
from tests.test_assignment_emulator import floor_room
from zora import archipelago
from zora.archipelago import (
    NO_MEMORY,
    NOT_RECEIVABLE,
    READ_RANGES,
    STATE_ADDRESSES,
    ClientMemory,
    ClientTables,
    ClientTablesRefused,
    Decision,
    NotReceivable,
    RamCheck,
    ReceivedItem,
    ServerView,
    client_step,
    receivable,
)
from zora.model.item_names import ITEM_NAMES
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.player_settings import PlayerSettingError

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

COUNT = archipelago.RECEIVED_COUNT
HEARTS = inventory.ITEMS + inventory.HEART_VALUES_SLOT
LADDER = inventory.ITEMS + 0x0C
RAFT = inventory.ITEMS + 0x09
MAX_WRITES, MAX_GUARDS = 2, 11
POLL_FRAMES = 30                      # the world polls every 0.125 s
NO_BUTTONS = Button(0)


# --- hand-made RAM ------------------------------------------------------------------------------------

PLACE_A, PLACE_B = "Place A", "Place B"
FLAG_A, FLAG_B = inventory.WORLD_FLAGS + 0x81, inventory.WORLD_FLAGS + 0x82     # two level rooms' flags
TABLES = ClientTables({PLACE_A: RamCheck(FLAG_A, inventory.ITEM_TAKEN),
                       PLACE_B: RamCheck(FLAG_B, inventory.ITEM_TAKEN)}, inventory.GiveRules())
IN_PLAY = {inventory.GAME_MODE: inventory.PLAY_MODE, inventory.IS_UPDATING_MODE: 1, inventory.CUR_SAVE_SLOT: 0,
           inventory.TRANSFERRED_COMMON_PATTERNS: inventory.SET_UP, inventory.SKIPPED_DEMO: inventory.SET_UP}
STARTING_HEARTS = 0x22                # three containers, three hearts


def loaded(changes: dict[int, int] | None = None) -> dict[int, int]:
    """Every byte the tables read, a file loaded and in play (may_receive), three hearts."""
    return dict.fromkeys(TABLES.addresses(), 0) | IN_PLAY | {HEARTS: STARTING_HEARTS} | (changes or {})


def state_of(ram: dict[int, int]) -> dict[int, int]:
    return {address: ram[address] for address in STATE_ADDRESSES}


def step(ram: dict[int, int], server: ServerView, memory: ClientMemory = NO_MEMORY,
         after: dict[int, int] | None = None) -> Decision:
    return client_step(ram, state_of(ram) if after is None else after, server, TABLES, memory)


def guarded_write(ram: dict[int, int], decision: Decision) -> bool:
    """Archipelago's guarded_write: every guard's byte as expected, or nothing is written."""
    if any(ram[address] != value for address, value in decision.guards):
        return False
    ram.update(decision.writes)
    return True


@pytest.fixture(scope="module", autouse=True)
def prg0() -> None:
    remember_repo_base_rom()


@cache
def result() -> archipelago.BuildResult:
    """The emulator seed (tests/test_archipelago_client_ram's case and seed) as Archipelago builds it."""
    return archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom())


def test_the_read_plan() -> None:
    """The state bytes in one scattered read, then $0657-$0752 and $0753-$07FE: every read at most
    252 bytes, covering the inventory, the received count and every pickup flag."""
    assert READ_RANGES == ((0x0657, 252), (0x0753, 172))
    assert all(length <= archipelago.MAX_READ_LENGTH for _start, length in READ_RANGES)
    assert len(STATE_ADDRESSES) <= archipelago.MAX_READ_LENGTH
    assert set(STATE_ADDRESSES) == {*archipelago.CHECKS_STATE, *archipelago.RECEIVE_STATE, *archipelago.GOAL_STATE}
    covered = set(ClientTables({}, inventory.GiveRules()).addresses())
    assert set(range(inventory.ITEMS, inventory.WORLD_FLAGS + 3 * inventory.WORLD_FLAGS_SIZE)) <= covered
    assert all(check.address in covered for check in archipelago.client_tables_of(result()).checks.values())


def test_the_json_tables_round_trip() -> None:
    data = archipelago.client_tables_to_json(result())
    text = json.dumps(data)
    assert archipelago.client_tables_from_json(json.loads(text)) == archipelago.client_tables_of(result())
    assert data["format"] == archipelago.CLIENT_TABLES_FORMAT and data["version"] == archipelago.CLIENT_TABLES_VERSION
    for refused in ({**data, "version": 2}, {**data, "format": "other"}, {**data, "checks": [["x", 1]]},
                    {key: value for key, value in data.items() if key != "rules"}):
        with pytest.raises(ClientTablesRefused):
            archipelago.client_tables_from_json(refused)


def test_the_tables_of_a_recipe() -> None:
    built_result = result()
    made = archipelago.recipe(built_result, dict(zip((place.name for place in built_result.places), built_result.pool,
                                                     strict=True)))
    assert archipelago.client_tables(made) == archipelago.client_tables_of(built_result)


@pytest.mark.parametrize("fill", list(FILLS))
def test_garbage_ram_decides_nothing(fill: str) -> None:
    ram = {address: FILLS[fill](address % 0x800) for address in TABLES.addresses()}
    server = ServerView((ReceivedItem("Heart Container"),))
    decision = step(ram, server, ClientMemory(awaiting_count=3))
    assert decision == Decision(readable=False, memory=ClientMemory())


def test_the_bracket() -> None:
    """Both reads of the state bytes must hold the loaded file, the same slot and the same mode."""
    ram = loaded({FLAG_A: inventory.ITEM_TAKEN})
    server = ServerView((ReceivedItem("Heart Container"),))
    assert step(ram, server).readable
    for changed in ({inventory.CUR_SAVE_SLOT: 1}, {inventory.GAME_MODE: 0x07}, {inventory.SKIPPED_DEMO: 0},
                    {inventory.GAME_MODE: 0x01}):
        decision = step(ram, server, after=state_of(ram) | changed)
        assert not decision.readable and not decision.report and not decision.writes and not decision.goal


def test_reports_once_until_the_server_has_them() -> None:
    ram = loaded({FLAG_A: inventory.ITEM_TAKEN})
    first = step(ram, ServerView())
    assert first.report == (PLACE_A,) and first.memory.reported == {PLACE_A}
    assert step(ram, ServerView(), first.memory).report == ()                  # sent, awaiting the server
    acknowledged = step(ram, ServerView(checked=frozenset({PLACE_A})), first.memory)
    assert acknowledged.report == () and acknowledged.memory.reported == frozenset()
    assert step(ram, ServerView(), NO_MEMORY).report == (PLACE_A,)            # a restarted client sends again


def test_one_item_per_poll_with_its_guards() -> None:
    ram = loaded()
    server = ServerView((ReceivedItem("Heart Container"), ReceivedItem("Ladder")))
    decision = step(ram, server)
    assert decision.gives == "Heart Container" and decision.skips is None
    assert decision.writes == ((HEARTS, STARTING_HEARTS + 0x11), (COUNT, 1))     # the count last
    guards = dict(decision.guards)
    assert set(guards) == {*archipelago.RECEIVE_STATE, COUNT, HEARTS} and guards[COUNT] == 0
    assert len(decision.writes) <= MAX_WRITES and len(decision.guards) <= MAX_GUARDS
    assert decision.memory.awaiting_count == 1
    assert guarded_write(ram, decision)
    second = step(ram, server, decision.memory)
    assert second.gives == "Ladder" and second.writes == ((LADDER, 1), (COUNT, 2))
    assert guarded_write(ram, second)
    assert step(ram, server, second.memory).writes == ()                        # nothing more to give


def test_an_item_found_in_this_file_is_counted_not_given() -> None:
    """items_handling 0b111: the server sends this slot's own items back. One whose place's pickup
    flag is set in the loaded file was given by the game: only the count goes up."""
    ram = loaded({FLAG_B: inventory.ITEM_TAKEN})
    server = ServerView((ReceivedItem("Heart Container", PLACE_B),))
    decision = step(ram, server)
    assert decision.skips == "Heart Container" and decision.gives is None
    assert decision.writes == ((COUNT, 1),) and dict(decision.guards)[FLAG_B] == inventory.ITEM_TAKEN
    not_taken = step(loaded(), server)                                          # e.g. after a reset without saving
    assert not_taken.gives == "Heart Container"


def test_receivable() -> None:
    """Owner rulings: rupees, regular hearts, fairies, maps, compasses, regular Triforce pieces and
    the clock are never Archipelago items, nor the Triforce of Power (the goal). receive() gives
    every other item name and refuses those."""
    assert NOT_RECEIVABLE == {"Rupee", "5 Rupees", "Heart", "Fairy", "Map", "Compass", "Triforce",
                              "Triforce of Power", "Clock"}
    assert len(archipelago.RECEIVABLE_ITEMS) == len(ITEM_NAMES) - len(NOT_RECEIVABLE) == 27
    assert not receivable("Fishing Rod")                                         # no item of the seed format
    ram = loaded()
    for name in ITEM_NAMES.values():
        if receivable(name):
            archipelago.receive(name, ram)
        else:
            with pytest.raises(NotReceivable):
                archipelago.receive(name, ram)
    assert {name for name in ITEM_NAMES.values() if not receivable(name)} == NOT_RECEIVABLE


def test_an_item_it_cannot_give_is_counted_not_raised() -> None:
    """A received item ZORA cannot give (not receivable(), or no item name) never raises: only the
    count goes up (cannot_give) and the next item follows, given exactly once."""
    ram = loaded()
    server = ServerView((ReceivedItem("Rupee"), ReceivedItem("Clock"), ReceivedItem("Fishing Rod"),
                         ReceivedItem("Raft")))
    memory, decisions = NO_MEMORY, []
    for _ in range(8):
        decision = step(ram, server, memory)
        if not decision.writes:
            break
        assert guarded_write(ram, decision)
        memory = decision.memory
        decisions.append(decision)
    assert [(d.cannot_give, d.gives) for d in decisions] == [
        ("Rupee", None), ("Clock", None), ("Fishing Rod", None), (None, "Raft")]
    assert decisions[0].writes == ((COUNT, 1),)
    assert set(dict(decisions[0].guards)) == {*archipelago.RECEIVE_STATE, COUNT}
    assert (ram[RAFT], ram[COUNT]) == (1, 4)


def test_the_awaited_count_waits_one_poll() -> None:
    ram = loaded()
    server = ServerView((ReceivedItem("Heart Container"),))
    waiting = step(ram, server, ClientMemory(awaiting_count=1))
    assert waiting.writes == () and waiting.memory.awaiting_count is None
    assert step(ram, server, waiting.memory).gives == "Heart Container"


def test_no_writes_outside_play() -> None:
    server = ServerView((ReceivedItem("Heart Container"),))
    for changed in ({inventory.MENU_STATE: 1}, {inventory.ITEM_LIFT_TIMER: 4}, {inventory.GAME_SUBMODE: 1}):
        ram = loaded(changed)                                                   # item screen, lifting, a submode
        assert step(ram, server).writes == ()
        assert step(loaded(), server, after=state_of(ram)).writes == ()


def test_the_goal() -> None:
    won = loaded({inventory.GAME_MODE: inventory.WIN_GAME_MODE, inventory.ZELDA_TYPE: inventory.ZELDA})
    decision = step(won, ServerView())
    assert decision.goal and decision.memory.goal_sent
    assert step(won, ServerView(), decision.memory).goal                          # again while not known: harmless
    assert not step(won, ServerView(goal_known=True), decision.memory).goal
    assert not step(loaded(), ServerView()).goal


def test_a_refused_write_keeps_the_memory_and_gives_once() -> None:
    """The wrapper keeps decision.memory only when the guarded write succeeded or there was nothing
    to write. A guard refused on purpose (Link's state changed between the read and the write):
    nothing is written, the old memory is kept, and the next poll gives the item exactly once."""
    ram = loaded()
    server = ServerView((ReceivedItem("Heart Container"),))
    memory = NO_MEMORY
    decision = step(ram, server, memory)
    ram[inventory.LINK_STATE] = 1                                             # after the read, before the write
    assert not guarded_write(ram, decision)
    assert ram[HEARTS] == STARTING_HEARTS and ram[COUNT] == 0                  # memory stays NO_MEMORY
    decision = step(ram, server, memory)
    assert guarded_write(ram, decision)
    memory = decision.memory
    assert step(ram, server, memory).writes == ()
    assert (ram[HEARTS], ram[COUNT]) == (STARTING_HEARTS + 0x11, 1)


def test_player_setting_checks() -> None:
    assert archipelago.player_setting_problem("music", "off") is None
    assert archipelago.player_setting_problem("death_warp", "p1_up_a") is None
    assert archipelago.player_setting_problem("greenTunic", 0x29) is None
    for key, value in (("greenTunic", 0x0D), ("selectButton", "sideways"), ("level_word", 7), ("nope", 1)):
        assert archipelago.player_setting_problem(key, value)
    archipelago.check_player_settings({"select_button": "toggle", "hearts": "0x16", "levelWord": "palace"})
    with pytest.raises(PlayerSettingError):
        archipelago.check_player_settings({"music": "off", "statistics_screen": "maybe"})
    with pytest.raises(PlayerSettingError):
        archipelago.check_player_settings({"music": "off", "Music": "off"})


# --- the emulator -------------------------------------------------------------------------------------

SERVER_ITEMS = ("Heart Container", "Ladder", "Heart Container", "Blue Ring", "Heart Container", "Raft",
                "Heart Container")
ACKNOWLEDGE_POLLS = 2                  # the server answers a report two polls later


@dataclass
class FakeServer:
    """A server for this slot: the received list, the checked set (reports acknowledged after
    ACKNOWLEDGE_POLLS polls), the goal."""
    received: list[ReceivedItem]
    checked: set[str] = field(default_factory=set)
    pending: list[tuple[int, str]] = field(default_factory=list)
    reports: list[tuple[int, str]] = field(default_factory=list)       # (slot, place), every report

    def view(self) -> ServerView:
        return ServerView(tuple(self.received), frozenset(self.checked))

    def report(self, poll: int, slot: int, places: tuple[str, ...]) -> None:
        self.pending += [(poll + ACKNOWLEDGE_POLLS, place) for place in places]
        self.reports += [(slot, place) for place in places]

    def answer(self, poll: int) -> None:
        self.checked |= {place for due, place in self.pending if due <= poll}
        self.pending = [(due, place) for due, place in self.pending if due > poll]


class Polled(Watched):
    """A console with the world's client: every POLL_FRAMES frames it reads the state bytes, then
    each range, then the state bytes again, one read per frame, and then acts on client_step's
    decision through a guarded write (refusing the first `refusals` writes on purpose)."""

    def __init__(self, rom: bytes, tables: ClientTables, server: FakeServer, refusals: int = 0) -> None:
        super().__init__(rom)
        self.tables, self.server, self.refusals = tables, server, refusals
        self.memory = NO_MEMORY
        self.phase = 0
        self.polls = 0
        self.snapshot: dict[int, int] = {}
        self.written: list[tuple[int, str]] = []          # (slot, item) for every applied give or skip
        self.bad_writes: list[int] = []                   # frames where a write was applied outside play

    def read(self, addresses: range | tuple[int, ...]) -> dict[int, int]:
        return {address: self[address] for address in addresses}

    def client_frame(self) -> None:
        """One frame of the client's poll cycle."""
        ranges = self.tables.ranges
        if self.phase == 0:
            self.snapshot = self.read(self.tables.state_addresses)
        elif self.phase <= len(ranges):
            start, length = ranges[self.phase - 1]
            self.snapshot |= self.read(range(start, start + length))
        elif self.phase == len(ranges) + 1:
            self.act(self.read(self.tables.state_addresses))
        self.phase = (self.phase + 1) % POLL_FRAMES

    def act(self, after: dict[int, int]) -> None:
        self.polls += 1
        self.server.answer(self.polls)
        decision = client_step(self.snapshot, after, self.server.view(), self.tables, self.memory)
        slot = self[inventory.CUR_SAVE_SLOT]
        if decision.report:
            self.server.report(self.polls, slot, decision.report)
        if not decision.writes:
            self.memory = decision.memory
            return
        if self.refusals:
            self.refusals -= 1                             # refused on purpose: memory kept
            return
        if any(self[address] != value for address, value in decision.guards):
            return                                         # refused: memory kept, retried next poll
        if not archipelago.may_receive(self.read(archipelago.RECEIVE_STATE)):
            self.bad_writes.append(self.frames)
        for address, value in decision.writes:
            self[address] = value
        self.written.append((slot, decision.gives or f"skipped {decision.skips}"))
        self.memory = decision.memory

    def run(self, frames: int, buttons: Button = NO_BUTTONS) -> None:
        for _ in range(frames):
            super().run(1, buttons)
            self.client_frame()


@cache
def tables() -> ClientTables:
    return archipelago.client_tables_of(result())


def checks() -> dict[str, RamCheck]:
    return dict(tables().checks)


def taken(emu: Emulator) -> set[str]:
    return {name for name, check in checks().items() if emu[check.address] & check.mask}


def battery_places(slot: int) -> set[str]:
    """The places the battery's file has taken: every FILE_STRIDE-th place from the slot's own
    (tests/test_archipelago_checks_readable.battery)."""
    return set(list(battery_checks())[slot::FILE_STRIDE])


def powered_on(fill: str, server: FakeServer, refusals: int = 0) -> Polled:
    """The client's console switched on with the battery and RAM holding `fill`'s pattern."""
    emu = Polled(zora_rom(), tables(), server, refusals)
    for address, value in zip(SAVE_RAM, battery().save_ram, strict=True):
        emu[address] = value
    for address in range(RAM_SIZE):
        emu[address] = FILLS[fill](address)
    return emu


def containers(emu: Emulator) -> int:
    return emu[HEARTS] >> 4


def play(emu: Polled, frames: int = 3 * PLAY_FRAMES) -> None:
    emu.run(frames)


@pytest.mark.parametrize(("fill", "refusals"), [("random 1", 0), ("$FF", 2)])
def test_a_client_polling_across_files_and_transitions(fill: str, refusals: int) -> None:
    server = FakeServer([ReceivedItem(name) for name in SERVER_ITEMS])
    emu = powered_on(fill, server, refusals)
    emu.run(20)
    emu.boot_to_file_select()
    emu.start_game(0)
    start = containers(emu)
    play(emu)
    place = floor_room(built())
    take_floor_item(emu, place)                                    # mode jumps: transitions between polls
    play(emu)
    own = ReceivedItem(result().pool[[info.name for info in result().places].index(place.name)], place.name)
    server.received.append(own)                                    # this slot's own item, back from the server
    play(emu)
    back_to_the_overworld(emu)
    play(emu)
    file_0 = (emu[COUNT], containers(emu) - start)
    emu.save_to_menu()
    emu.run(POLL_FRAMES * 3)                                       # the file-select screen, polled
    emu.start_game(1)
    start_1 = containers(emu)
    play(emu, 6 * PLAY_FRAMES)
    file_1 = (emu[COUNT], containers(emu) - start_1)

    assert emu.bad_writes == []
    everything = len(SERVER_ITEMS) + 1
    own_is_container = int(own.name == "Heart Container")
    # file 0: the server's items from its count on, its own item found in play counted, not given
    assert [item for slot, item in emu.written if slot == 0] == [*SERVER_ITEMS[FILE_COUNTS[0]:], f"skipped {own.name}"]
    assert file_0 == (everything, SERVER_ITEMS[FILE_COUNTS[0]:].count("Heart Container") + own_is_container)
    # file 1: given, unless its battery holds that place taken too (then counted, as in file 0)
    held_in_1 = place.name in battery_places(1)
    assert [item for slot, item in emu.written if slot == 1] == \
        [*SERVER_ITEMS[FILE_COUNTS[1]:], f"skipped {own.name}" if held_in_1 else own.name]
    assert file_1 == (everything, SERVER_ITEMS[FILE_COUNTS[1]:].count("Heart Container")
                      + (0 if held_in_1 else own_is_container))
    # every report is a place the loaded file had taken, and every such place is reported
    file_places = {0: battery_places(0) | {place.name}, 1: battery_places(1)}
    assert all(reported in file_places[slot] for slot, reported in server.reports), server.reports
    # (file 1 leaves out what the server already holds from file 0)
    assert {reported for at, reported in server.reports if at == 0} == file_places[0]
    assert {reported for at, reported in server.reports if at == 1} == file_places[1] - file_places[0]
