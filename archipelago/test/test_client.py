"""The BizHawk client's wrapper around ZORA's client_step, on hand-made RAM with a stand-in for the
connector's read and guarded_write (which, like the connector, writes only if every guard byte
still holds what the read saw). ZORA's own tests cover client_step itself; these cover what the
wrapper adds: the reads, the reports, the writes through guarded_write, the memory kept only on a
landed write, and never stopping on an error."""
import asyncio
import sys
import types
import unittest
from collections.abc import Callable
from typing import Any
from unittest import mock

from NetUtils import NetworkItem

from .. import client as client_module
from ..names import ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID
from ..rom import rom_file_bytes
from ..zora import archipelago as zora_ap
from ..zora.rom import inventory

RAM_SIZE = 0x800
SLOT = 1
PLACE_A, PLACE_B = "Level 4 Room 05 Floor", "Level 1 Room 1C Floor"
FLAG_A, FLAG_B = inventory.WORLD_FLAGS + 0x81, inventory.WORLD_FLAGS + 0x82
TABLES = {"format": zora_ap.CLIENT_TABLES_FORMAT, "version": zora_ap.CLIENT_TABLES_VERSION,
          "checks": [[PLACE_A, FLAG_A, inventory.ITEM_TAKEN], [PLACE_B, FLAG_B, inventory.ITEM_TAKEN]],
          "rules": {"progressiveItems": False, "l4Sword": False, "fourPotions": False,
                    "arrivalSound": inventory.ITEM_APPEARS_SOUND}}
IN_PLAY = {inventory.GAME_MODE: inventory.PLAY_MODE, inventory.IS_UPDATING_MODE: 1, inventory.CUR_SAVE_SLOT: 0,
           inventory.TRANSFERRED_COMMON_PATTERNS: inventory.SET_UP, inventory.SKIPPED_DEMO: inventory.SET_UP}
HEARTS = inventory.ITEMS + inventory.HEART_VALUES_SLOT
STARTING_HEARTS = 0x22                  # three containers, three hearts
BOMBS = inventory.ITEMS + 0x01
SWORD = inventory.ITEMS + inventory.SWORD_SLOT
RAFT = inventory.ITEMS + 0x09
ITEM_ID_TO_NAME = {item_id: name for name, item_id in ITEM_NAME_TO_ID.items()}


def in_play() -> list[int]:
    ram = [0] * RAM_SIZE
    for address, value in {**IN_PLAY, HEARTS: STARTING_HEARTS}.items():
        ram[address] = value
    return ram


class Console:
    """The connector's side: the RAM, one read (all of a tick's ranges, as in one frame) and a
    guarded write. `between` runs once, after the next read: the game moving on before the write."""

    def __init__(self, ram: list[int]) -> None:
        self.ram = ram
        self.between: Callable[[list[int]], Any] | None = None
        self.writes = self.refused = 0
        self.errors: list[Exception | None] = []    # for the next requests, one each (None: no error)

    def error(self) -> None:
        error = self.errors.pop(0) if self.errors else None
        if error is not None:
            raise error

    async def read(self, _ctx: Any, reads: list[tuple[int, int, str]]) -> list[bytes]:
        self.error()
        data = [bytes(self.ram[address:address + length]) for address, length, _domain in reads]
        if self.between is not None:
            self.between(self.ram)
            self.between = None
        return data

    async def guarded_write(self, _ctx: Any, writes: list[tuple[int, list[int], str]],
                            guards: list[tuple[int, list[int], str]]) -> bool:
        self.error()
        if any(self.ram[address:address + len(values)] != list(values) for address, values, _domain in guards):
            self.refused += 1
            return False
        for address, values, _domain in writes:
            self.ram[address:address + len(values)] = values
        self.writes += 1
        return True


class TestClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            rom = rom_file_bytes()
        except Exception as missing:
            raise unittest.SkipTest(f"no ROM in host.yaml (zora_options rom_file): {missing}") from missing
        zora_ap.client_ready(rom)

    def setUp(self) -> None:
        self.console = Console(in_play())
        self.sent: list[int] = []
        self.client = client_module.ZoraClient()
        self.ctx = self.make_ctx()
        import tempfile
        seen = tempfile.mktemp(suffix=".json")      # the HUD's record of announced items, not the real one
        patches = (mock.patch("worlds._bizhawk.read", self.console.read),
                   mock.patch("worlds._bizhawk.guarded_write", self.console.guarded_write),
                   mock.patch.object(client_module.ZoraClient, "hud_seen_path", lambda _self: seen))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def make_ctx(self, items: tuple[NetworkItem, ...] = ()) -> types.SimpleNamespace:
        async def send_msgs(messages: list[dict[str, Any]]) -> None:
            for message in messages:
                if message["cmd"] == "LocationChecks":
                    self.sent.extend(message["locations"])
                    self.ctx.checked_locations |= set(message["locations"])

        names = types.SimpleNamespace(lookup_in_game=lambda item: ITEM_ID_TO_NAME.get(item, f"Unknown item {item}"))
        return types.SimpleNamespace(server=object(), slot=SLOT, bizhawk_ctx=None, finished_game=False,
                                     send_msgs=send_msgs, slot_data={"client_tables": TABLES},
                                     checked_locations=set(), items_received=list(items), item_names=names)

    def tick(self, times: int = 1) -> None:
        for _ in range(times):
            asyncio.run(self.client.game_watcher(self.ctx))

    def test_a_pickup_is_reported_once(self) -> None:
        self.tick()
        self.assertEqual(self.sent, [])
        self.console.ram[FLAG_A] |= inventory.ITEM_TAKEN
        self.tick(3)
        self.assertEqual(self.sent, [LOCATION_NAME_TO_ID[PLACE_A]])

    def test_an_item_is_given_once(self) -> None:
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        self.tick(4)
        self.assertEqual(self.console.ram[RAFT], 1)
        self.assertEqual(self.console.ram[zora_ap.RECEIVED_COUNT], 1)
        self.assertEqual(self.console.writes, 1)

    def test_a_refused_write_is_decided_again_and_gives_once(self) -> None:
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Bombs"], -2, SLOT))
        self.console.between = lambda ram: ram.__setitem__(BOMBS, ram[BOMBS] + 1)
        self.tick()
        self.assertEqual((self.console.writes, self.console.refused), (0, 1))
        self.assertEqual(self.console.ram[zora_ap.RECEIVED_COUNT], 0)
        self.tick(4)
        self.assertEqual((self.console.writes, self.console.refused), (1, 1))
        self.assertEqual(self.console.ram[zora_ap.RECEIVED_COUNT], 1)

    def test_nothing_happens_outside_play(self) -> None:
        self.console.ram[inventory.GAME_MODE] = 0
        self.console.ram[FLAG_A] |= inventory.ITEM_TAKEN
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        self.tick(3)
        self.assertEqual((self.sent, self.console.writes), ([], 0))

    def test_an_item_it_cannot_give_is_counted(self) -> None:
        self.ctx.items_received.append(NetworkItem(9999, -2, SLOT))
        self.tick(3)
        self.assertEqual(self.console.ram[zora_ap.RECEIVED_COUNT], 1)
        self.assertEqual(self.console.ram[RAFT], 0)

    def test_slot_data_from_another_version_does_nothing(self) -> None:
        self.ctx.slot_data = {"pickup_checks": {}}
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        with self.assertLogs("Client", "ERROR"):
            self.tick(2)
        self.assertEqual((self.sent, self.console.writes), ([], 0))

    def test_an_error_in_client_step_never_stops_the_client(self) -> None:
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        with mock.patch.object(zora_ap, "client_step", side_effect=RuntimeError("a bug")), \
                self.assertLogs("Client", "ERROR"):
            self.tick(2)
        self.tick(3)
        self.assertEqual(self.console.ram[RAFT], 1)

    def test_a_connector_error_skips_the_tick(self) -> None:
        """z1rr-coop's console bridge answers ERROR while the console can't be read: as Archipelago's
        send_requests raises it (an ExceptionGroup on Python 3.11+), on a read and on a write."""
        from worlds._bizhawk import ConnectorError

        def raised(message: str) -> Exception:
            error = ConnectorError(message)
            return ExceptionGroup("Connector script returned errors", [error]) if sys.version_info >= (3, 11) else error

        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        self.console.errors = [raised("EverDrive did not answer"), raised("EverDrive did not answer")]
        with self.assertLogs("Client", "INFO") as logged:
            self.tick(2)
        self.assertEqual(len(logged.records), 1)                # the same message, logged once
        self.assertEqual((self.console.writes, self.console.ram[RAFT]), (0, 0))
        self.console.errors = [None, raised("no answer to a guarded write")]
        self.tick()                                             # read works, the write errs
        self.assertEqual(self.console.writes, 0)
        self.tick(4)
        self.assertEqual((self.console.writes, self.console.ram[RAFT]), (1, 1))

    def test_other_errors_still_stop_the_tick(self) -> None:
        self.console.errors = [ValueError("not the connector")]
        with self.assertRaises(ValueError):
            self.tick()

    def test_an_upgrade_is_given_as_its_line_s_next_level(self) -> None:
        self.ctx.slot_data = {"client_tables": {**TABLES, "rules": {**TABLES["rules"], "progressiveItems": True}}}
        self.console.ram[SWORD] = 1                         # the wooden sword
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Sword Upgrade"], -2, SLOT))
        with self.assertLogs("Client", "INFO") as logs:
            self.tick(4)
        self.assertEqual(self.console.ram[SWORD], 2)        # the white sword
        self.assertIn("gave received item #1, Sword Upgrade", "\n".join(logs.output))

    def test_the_client_reads_the_recipe_format_zora_makes(self) -> None:
        self.assertEqual(client_module.RECIPE_FORMAT, tuple(zora_ap.FORMAT_VERSION_NUMBERS))

    def test_a_give_plays_the_arrival_sound(self) -> None:
        """Through the same guarded write: the client tables' sound (item appears) at Tune1Request."""
        self.ctx.items_received.append(NetworkItem(ITEM_NAME_TO_ID["Raft"], -2, SLOT))
        self.tick(4)
        self.assertEqual(self.console.ram[RAFT], 1)
        self.assertEqual(self.console.ram[inventory.TUNE1_REQUEST], inventory.ITEM_APPEARS_SOUND)
        self.assertEqual(self.console.writes, 1)


class TestHudMessages(unittest.TestCase):
    """The HUD lines the client builds, on a stand-in context (no emulator)."""

    def setUp(self) -> None:
        import os
        import tempfile
        self.client = client_module.ZoraClient()
        handle, self.path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.remove(self.path)
        patch = mock.patch.object(client_module.ZoraClient, "hud_seen_path", lambda _self: self.path)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))
        names = {1: "Heart Container", 2: "Magical Boomerang", 3: "Raft", 4: "éé"}
        self.ctx = types.SimpleNamespace(
            slot=SLOT, seed_name="seed", bizhawk_ctx=None, player_names={SLOT: "Gob-ZORA", 2: "Gob-Z2R", 3: "Someone Else Long"},
            item_names=types.SimpleNamespace(lookup_in_game=names.get, lookup_in_slot=lambda i, _s: names[i]))

    def texts(self) -> list:
        return [text for text, _ in self.client.hud_messages]

    def got(self, item: int, player: int, count: int, location: int = 5) -> None:
        self.client.hud_got(self.ctx, NetworkItem(item, location, player), count)

    def test_full_names_when_they_fit_and_no_got_on_lines_from_others(self) -> None:
        self.got(1, SLOT, 1)
        self.got(1, 2, 2)                      # prefix "Gob-" left off the sender
        self.got(2, 3, 3)                      # too long for the room: short name
        self.assertEqual(self.texts(), ["GOT HEART CONTAINER", "HEART CONTAINER FROM Z2R",
                                        "M BOOMER FROM SOMEONE ELS"])
        self.assertTrue(all(len(text) <= 28 for text in self.texts()))

    def test_starting_items_are_not_announced(self) -> None:
        self.got(3, SLOT, 1, location=-2)
        self.assertEqual(self.texts(), [])

    def test_an_item_with_no_showable_characters_is_called_item(self) -> None:
        self.got(4, SLOT, 1)
        self.assertEqual(self.texts(), ["GOT ITEM"])

    def test_items_given_again_get_one_burst_line_even_after_a_restart(self) -> None:
        for count in (1, 2, 3):
            self.got(3, SLOT, count)
        self.client = client_module.ZoraClient()       # a switch restarts the client
        self.ctx.items_received = []
        for count in (1, 2, 3, 4):
            self.got(3, SLOT, count)
        # the new item (4) goes ahead of the burst
        self.assertEqual(self.texts(), ["GOT RAFT", "3 ITEMS GIVEN BACK", "GOT RAFT", "GOT RAFT", "GOT RAFT"])

    def test_the_burst_line_comes_first_then_each_item_of_the_burst(self) -> None:
        for count in (1, 2):
            self.got(1, SLOT, count)
        self.client = client_module.ZoraClient()       # a switch restarts the client
        self.ctx.items_received = []
        self.got(1, SLOT, 1)                           # given again
        self.got(1, 2, 2)                              # given again, from another player
        self.got(3, SLOT, 3)                           # new
        self.assertEqual(self.texts(), ["GOT RAFT", "2 ITEMS GIVEN BACK", "GOT HEART CONTAINER",
                                        "HEART CONTAINER FROM Z2R"])

    def test_one_burst_line_with_the_full_count_when_lines_show_between_gives(self) -> None:
        for count in (1, 2, 3):
            self.got(3, SLOT, count)
        self.client = client_module.ZoraClient()
        shown = []
        for count in (1, 2, 3):                        # hud_tick shows the first line after each give
            self.got(3, SLOT, count)
            shown.append(self.client.hud_messages.pop(0)[0])
        self.assertEqual(shown + self.texts(), ["3 ITEMS GIVEN BACK", "GOT RAFT", "GOT RAFT", "GOT RAFT"])

    def test_a_new_seed_does_not_count_items_of_an_old_one(self) -> None:
        self.ctx.seed_name = None                      # as Archipelago leaves it
        self.ctx.server_seed_name = "old"
        for count in (1, 2, 3):
            self.got(3, SLOT, count)
        self.client.hud_messages.clear()
        self.ctx.server_seed_name = "new"
        self.got(3, SLOT, 1)
        self.assertEqual(self.texts(), ["GOT RAFT"])

    def test_with_no_seed_name_no_item_counts_as_given_again(self) -> None:
        self.ctx.seed_name = None
        self.got(3, SLOT, 1)
        self.got(3, SLOT, 1)
        self.assertEqual(self.texts(), ["GOT RAFT", "GOT RAFT"])

    def test_a_burst_counts_no_more_items_than_the_server_sent(self) -> None:
        for count in (1, 2, 3, 4, 5):
            self.got(3, SLOT, count)
        self.client.hud_messages.clear()
        self.ctx.items_received = [NetworkItem(3, 5, SLOT)] * 2
        self.got(3, SLOT, 1)
        self.assertEqual(self.texts()[0], "2 ITEMS GIVEN BACK")

    def test_a_later_burst_counts_from_its_own_first_item(self) -> None:
        for count in (1, 2, 3):
            self.got(3, SLOT, count)
        self.client = client_module.ZoraClient()
        self.got(3, SLOT, 3)                           # one item given again
        self.got(3, SLOT, 4)                           # then a new one ends the burst
        self.client.hud_messages.clear()
        self.got(3, SLOT, 4)                           # a new file: item 4 given again
        self.assertEqual(self.texts()[0], "1 ITEM GIVEN BACK")

    def test_a_sent_line_goes_ahead_of_received_lines_that_wait(self) -> None:
        self.got(3, 2, 1)
        self.got(3, 2, 2)
        item = NetworkItem(1, 9, SLOT)
        self.client.on_package(self.ctx, "PrintJSON", {"type": "ItemSend", "item": item, "receiving": 2})
        self.assertEqual(self.texts()[0], "SENT HEART CONTAINER TO Z2R")
        self.assertEqual(len(self.texts()), 3)

    def test_a_cut_name_never_ends_on_a_small_word(self) -> None:
        self.assertEqual(client_module.ZoraClient.hud_item("Piece of Heart", 13), "HEART PIECE")
        self.assertEqual(client_module.ZoraClient.hud_fit("Book of Mudora", 10), "BOOK")

    def test_a_short_name_too_long_for_the_room_uses_its_tiny_name(self) -> None:
        self.assertEqual(client_module.ZoraClient.hud_item("Piece of Heart", 8), "HEART PC")
        self.assertEqual(client_module.ZoraClient.hud_item("Piece of Heart", 13), "HEART PIECE")

    def test_the_written_row_is_centered(self) -> None:
        written = []

        async def guarded_write(_ctx, writes, _guards):
            written.append(writes)
            return True
        fake = types.SimpleNamespace(guarded_write=guarded_write)
        with mock.patch.dict(sys.modules, {"worlds._bizhawk": fake}):
            asyncio.run(self.client.hud_write(self.ctx, "GOT RAFT"))
        record = written[0][0][1]
        self.assertEqual(record[:3], [0x20, 0x22, 0x1C])
        self.assertEqual(len(record), 32)
        self.assertEqual(record[-1], 0xFF)
        tiles = record[3:-1]
        blank = tiles[0]
        lead = next(i for i, tile in enumerate(tiles) if tile != blank)
        self.assertEqual(lead, (28 - len("GOT RAFT")) // 2)


# The game's status-bar redraw as FCEUX shows it in $0302, sent every second frame in play, caves
# and cellars into an empty buffer, with $0301 left at 0: the row above the hearts, the hearts,
# rupees, keys, bombs and -LIFE-.
STATUS_REDRAW = [0x20, 0xB6, 0x08] + [0x24] * 8 + [
    0x20, 0xD6, 0x08, 0xF2, 0xF2, 0xF2, 0x66, 0x66, 0x66, 0x24, 0x24,
    0x20, 0x6C, 0x03, 0x21, 0x09, 0x09, 0x20, 0xAC, 0x03, 0x21, 0x0A, 0x24, 0x20, 0xCC, 0x03, 0x21, 0x04, 0x24,
    0x20, 0x76, 0x09, 0x24, 0x2F, 0x15, 0x12, 0x0F, 0x0E, 0x2F, 0x24, 0x24, 0xFF]
CAVE_TYPING = [0x21, 0xA9, 0x01, 0x15, 0xFF]     # one character of the old man's text, $0301 left at 0


def hud_ram(mode: int, submode: int = 0, updating: int = 1, buffer: list[int] | None = None,
            index: int = 0, selector: int = 0) -> list[int]:
    """RAM with GameMode $12, GameSubmode $13, IsUpdatingMode $11, TileBufSelector $14 and the tile
    buffer at $0302 with $0301 (the index of its $FF end, which the game's whole-buffer records
    leave at 0)."""
    ram = [0] * RAM_SIZE
    ram[0x12], ram[0x13], ram[0x11], ram[0x14] = mode, submode, updating, selector
    buffer = [0xFF] if buffer is None else buffer
    ram[0x0302:0x0302 + len(buffer)] = buffer
    ram[0x0301] = index
    return ram


class TestHudWrite(unittest.TestCase):
    """hud_write's guards: the 32-byte record goes into the tile buffer only in the states where the
    NMI copies it without losing one of the game's own records."""

    def setUp(self) -> None:
        self.client = client_module.ZoraClient()
        self.ctx = types.SimpleNamespace(bizhawk_ctx=None)

    def write(self, ram: list[int], text: str = "GOT RAFT") -> tuple[bool, Console]:
        console = Console(ram)
        with mock.patch("worlds._bizhawk.guarded_write", console.guarded_write):
            done = asyncio.run(self.client.hud_write(self.ctx, text))
        return done, console

    def assert_written(self, ram: list[int]) -> None:
        done, console = self.write(ram)
        self.assertTrue(done)
        self.assertEqual(console.ram[0x0302:0x0305], [0x20, 0x22, 28])
        self.assertEqual(console.ram[0x0302 + 31], 0xFF)          # the record's end
        self.assertEqual(console.ram[0x0301], 31)                  # index of that end

    def assert_refused(self, ram: list[int]) -> None:
        before = list(ram)
        done, console = self.write(ram)
        self.assertFalse(done)
        self.assertEqual(console.ram, before)

    def test_play_with_an_empty_buffer(self) -> None:
        self.assert_written(hud_ram(5))

    def test_play_with_the_status_bar_redraw_replaces_it(self) -> None:
        self.assert_written(hud_ram(5, buffer=STATUS_REDRAW))

    def test_play_with_another_record_waits(self) -> None:
        for buffer in ([0x21, 0x00, 0x04, 1, 2, 3, 4, 0xFF],
                       [0x20, 0xE4, 0x04, 1, 2, 3, 4, 0xFF]):     # starts $20, but not the redraw
            with self.subTest(buffer=buffer[:3]):
                self.assert_refused(hud_ram(5, buffer=buffer, index=len(buffer) - 1))

    def test_not_updating_waits(self) -> None:
        """$11=0 while a mode sets itself up (cave and cellar entry and exit), in every guard."""
        for mode, buffer in ((5, None), (5, STATUS_REDRAW), (0x09, None), (0x0A, None),
                             (0x0B, STATUS_REDRAW), (0x0C, STATUS_REDRAW)):
            with self.subTest(mode=mode, redraw=buffer is not None):
                self.assert_refused(hud_ram(mode, updating=0, buffer=buffer))

    def test_a_fixed_buffer_send_waits(self) -> None:
        """$14 (TileBufSelector) nonzero: the NMI sends one of the game's fixed buffers instead of
        $0302, then resets both, so a record written now would be lost."""
        for mode, buffer in ((5, None), (5, STATUS_REDRAW), (0x09, None), (0x0B, STATUS_REDRAW)):
            with self.subTest(mode=mode, redraw=buffer is not None):
                self.assert_refused(hud_ram(mode, buffer=buffer, selector=0x44))

    def test_cellars_with_their_submode_left_at_9(self) -> None:
        self.assert_written(hud_ram(0x09, submode=9))
        self.assert_refused(hud_ram(0x0A, submode=9))        # leaving the cellar: no write

    def test_cellars_replace_the_status_bar_redraw(self) -> None:
        # with the Item Counter on, the buffer is never empty in a cellar: the redraw frames are the way in
        self.assert_written(hud_ram(0x09, submode=9, buffer=STATUS_REDRAW))

    def test_cellars_leave_the_item_counter_record_alone(self) -> None:
        self.assert_refused(hud_ram(0x09, submode=9, buffer=[0x20, 0x8B, 0x04, 0, 0, 0, 0, 0xFF]))

    def test_caves_replace_the_status_bar_redraw(self) -> None:
        for mode in (0x0B, 0x0C):
            with self.subTest(mode=mode):
                self.assert_written(hud_ram(mode, buffer=STATUS_REDRAW))

    def test_caves_leave_typing_text_alone(self) -> None:
        self.assert_refused(hud_ram(0x0B, buffer=CAVE_TYPING))

    def test_no_write_outside_play(self) -> None:
        """Title and file screens, scrolls (6, 7), stairs ($10), death ($11) and continue (8)."""
        for mode in (0x00, 0x01, 0x04, 0x06, 0x07, 0x08, 0x10, 0x11):
            with self.subTest(mode=mode):
                self.assert_refused(hud_ram(mode))

    def test_the_blank_row_is_all_spaces(self) -> None:
        from ..zora.rom.text_encoding import CHAR_TO_BYTE
        done, console = self.write(hud_ram(5), "")
        self.assertTrue(done)
        self.assertEqual(console.ram[0x0305:0x0305 + 28], [CHAR_TO_BYTE[" "]] * 28)

    def test_a_long_line_is_cut_to_the_row(self) -> None:
        done, console = self.write(hud_ram(5), "X" * 40)
        self.assertTrue(done)
        self.assertEqual(console.ram[0x0302 + 31], 0xFF)


class TestHudTiming(unittest.TestCase):
    """hud_tick: how long each line stays, the redraw while shown, the blank after, and retries."""

    def setUp(self) -> None:
        self.client = client_module.ZoraClient()
        self.ctx = types.SimpleNamespace(bizhawk_ctx=None)
        self.console = Console(hud_ram(5))
        self.now = 100.0
        patches = (mock.patch("worlds._bizhawk.guarded_write", self.console.guarded_write),
                   mock.patch("time.monotonic", lambda: self.now))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tick_at(self, offset: float) -> None:
        self.now = 100.0 + offset
        self.console.ram[0x0302], self.console.ram[0x0301] = 0xFF, 0    # the NMI emptied the buffer
        asyncio.run(self.client.hud_tick(self.ctx))

    def queue(self, *texts: str) -> None:
        self.client.hud_queue().extend((text, "got") for text in texts)

    def test_a_line_shows_10_s_then_the_row_is_blanked(self) -> None:
        self.queue("GOT RAFT")
        self.tick_at(0)
        self.assertEqual((self.client.hud_text, self.console.writes), ("GOT RAFT", 1))
        self.tick_at(9.9)
        self.assertEqual(self.client.hud_text, "GOT RAFT")
        writes = self.console.writes
        self.tick_at(10)
        self.assertIsNone(self.client.hud_text)
        self.assertEqual(self.console.writes, writes + 1)       # the first blank goes at once
        self.tick_at(10.5)
        self.assertEqual(self.console.writes, writes + 1)
        self.tick_at(11)
        self.tick_at(12)                                        # a blank can be lost: written 3 times
        self.assertEqual(self.console.writes, writes + 3)
        self.assertFalse(self.client.hud_dirty)
        self.tick_at(13)                                        # then nothing more
        self.assertEqual(self.console.writes, writes + 3)

    def test_a_shown_line_is_redrawn_each_second(self) -> None:
        self.queue("GOT RAFT")
        self.tick_at(0)
        self.tick_at(0.5)
        self.assertEqual(self.console.writes, 1)
        self.tick_at(1.0)
        self.assertEqual(self.console.writes, 2)
        self.tick_at(1.5)                                   # counted from the last redraw
        self.assertEqual(self.console.writes, 2)
        self.tick_at(2.0)
        self.assertEqual(self.console.writes, 3)

    def test_a_refused_redraw_is_tried_again_next_tick(self) -> None:
        self.queue("GOT RAFT")
        self.tick_at(0)
        self.console.ram[0x12] = 0x07                       # a scroll
        self.tick_at(1.0)
        self.assertEqual(self.console.writes, 1)
        self.console.ram[0x12] = 5
        self.tick_at(1.1)
        self.assertEqual(self.console.writes, 2)

    def test_a_refused_blank_is_tried_again_until_it_lands(self) -> None:
        self.queue("GOT RAFT")
        self.tick_at(0)
        self.console.ram[0x12] = 0x07
        self.tick_at(10)
        self.assertIsNone(self.client.hud_text)
        self.assertTrue(self.client.hud_dirty)              # the text is still on screen
        self.console.ram[0x12] = 5
        self.tick_at(10.1)
        self.assertEqual(self.console.writes, 2)
        self.tick_at(11.1)
        self.tick_at(12.1)
        self.assertFalse(self.client.hud_dirty)
        self.assertEqual(self.console.writes, 4)

    def test_lines_follow_each_other_without_a_blank_between(self) -> None:
        self.queue("GOT RAFT", "GOT BOW")
        self.tick_at(0)
        self.tick_at(10)
        self.assertEqual(self.client.hud_text, "GOT BOW")
        self.assertTrue(self.client.hud_dirty)

    def test_a_busy_queue_gives_each_line_5_s(self) -> None:
        self.queue("A", "B", "C", "D")
        self.tick_at(0)
        self.assertEqual(self.client.hud_until, 105.0)
        self.client.hud_queue().clear()
        self.queue("E", "F", "G")
        self.tick_at(5)
        self.assertEqual(self.client.hud_until, 115.0)      # 3 pending: 10 s again

    def test_a_line_up_when_the_queue_gets_busy_keeps_only_5_s(self) -> None:
        self.queue("A")
        self.tick_at(0)
        self.assertEqual(self.client.hud_until, 110.0)
        self.queue("B", "C", "D")
        self.tick_at(1)
        self.assertEqual(self.client.hud_until, 105.0)

    def test_items_given_again_get_5_s_each(self) -> None:
        self.client.hud_queue().append(("GOT RAFT", "regot"))
        self.tick_at(0)
        self.assertEqual(self.client.hud_until, 105.0)

    def test_a_refused_write_keeps_the_line(self) -> None:
        self.queue("GOT RAFT")
        self.console.ram[0x12] = 0                          # title screen
        self.now = 100.0
        asyncio.run(self.client.hud_tick(self.ctx))
        self.assertEqual((self.client.hud_text, len(self.client.hud_queue())), (None, 1))
        self.console.ram[0x12] = 5
        self.tick_at(1)
        self.assertEqual((self.client.hud_text, len(self.client.hud_queue())), ("GOT RAFT", 0))

    def test_a_dropped_connection_keeps_the_line(self) -> None:
        from worlds._bizhawk import RequestFailedError
        self.queue("GOT RAFT")
        self.console.errors = [RequestFailedError("gone")]
        with self.assertNoLogs("Client"):               # a dropped link is expected: not logged
            self.tick_at(0)
        self.assertEqual(len(self.client.hud_queue()), 1)
        self.tick_at(1)
        self.assertEqual(self.client.hud_text, "GOT RAFT")

    def test_an_unknown_error_is_logged_once_and_never_raised(self) -> None:
        self.queue("GOT RAFT")
        self.console.errors = [RuntimeError("odd"), RuntimeError("odd")]
        with self.assertLogs("Client", "WARNING") as logs:
            self.tick_at(0)
            self.tick_at(0.1)
        self.assertEqual(len(logs.records), 1)
        self.tick_at(0.2)
        self.assertEqual(self.client.hud_text, "GOT RAFT")
