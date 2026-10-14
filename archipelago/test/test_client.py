"""The BizHawk client's wrapper around ZORA's client_step, on hand-made RAM with a stand-in for the
connector's read and guarded_write (which, like the connector, writes only if every guard byte
still holds what the read saw). ZORA's own tests cover client_step itself; these cover what the
wrapper adds: the reads, the reports, the writes through guarded_write, the memory kept only on a
landed write, and never stopping on an error."""
import asyncio
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
PLACE_A, PLACE_B = "Level 4 Room 05", "Level 1 Room 1C"
FLAG_A, FLAG_B = inventory.WORLD_FLAGS + 0x81, inventory.WORLD_FLAGS + 0x82
TABLES = {"format": zora_ap.CLIENT_TABLES_FORMAT, "version": zora_ap.CLIENT_TABLES_VERSION,
          "checks": [[PLACE_A, FLAG_A, inventory.ITEM_TAKEN], [PLACE_B, FLAG_B, inventory.ITEM_TAKEN]],
          "rules": {"progressiveItems": False, "l4Sword": False, "fourPotions": False}}
IN_PLAY = {inventory.GAME_MODE: inventory.PLAY_MODE, inventory.IS_UPDATING_MODE: 1, inventory.CUR_SAVE_SLOT: 0,
           inventory.TRANSFERRED_COMMON_PATTERNS: inventory.SET_UP, inventory.SKIPPED_DEMO: inventory.SET_UP}
HEARTS = inventory.ITEMS + inventory.HEART_VALUES_SLOT
STARTING_HEARTS = 0x22                  # three containers, three hearts
BOMBS = inventory.ITEMS + 0x01
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

    async def read(self, _ctx: Any, reads: list[tuple[int, int, str]]) -> list[bytes]:
        data = [bytes(self.ram[address:address + length]) for address, length, _domain in reads]
        if self.between is not None:
            self.between(self.ram)
            self.between = None
        return data

    async def guarded_write(self, _ctx: Any, writes: list[tuple[int, list[int], str]],
                            guards: list[tuple[int, list[int], str]]) -> bool:
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
