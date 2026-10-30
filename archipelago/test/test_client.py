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
        patches = (mock.patch("worlds._bizhawk.read", self.console.read),
                   mock.patch("worlds._bizhawk.guarded_write", self.console.guarded_write))
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
