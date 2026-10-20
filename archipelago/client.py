"""The BizHawk client for ZORA (NES): a thin wrapper around ZORA's client_step.

The ROM's slot record (zora.archipelago.rom_identity) tells the client it is a ZORA Archipelago
ROM and which slot to log in as. Every rule about what to report, write or send lives in ZORA's
client_step (zora/archipelago.py, docs/archipelago.md "client_step"); each tick (every 0.125 s)
this wrapper only:
- reads, in one request (so in one frame), the state bytes, the ranges ZORA's client tables list
  (slot data "client_tables", from client_tables_to_json), and the state bytes again;
- passes them to client_step with what the server has said (the received items, this slot's
  checked places, whether the goal was sent) and the memory it kept from the last tick;
- sends the places to report and the goal, and makes the RAM writes with guarded_write, which
  writes only if every guard byte still holds what was read; it keeps the decision's memory only
  when that write landed or there was nothing to write, so a refused write is simply decided
  again next tick.
An exception from client_step is logged and the next tick tries again, so one bad tick never
stops a session.

receive() (inside client_step) reads two of the original game's tables from the player's own ROM,
so the client hands ZORA host.yaml's ROM (client_ready) when it recognizes a ZORA ROM: it may run
without having baked the ROM in this process (started on its own, or restarted).
"""
from __future__ import annotations

import json
import logging
import pkgutil
from base64 import b64encode
from typing import TYPE_CHECKING, Any

from NetUtils import ClientStatus
from worlds._bizhawk.client import BizHawkClient

from .names import GIVEN_AS, LOCATION_NAME_TO_ID
from .rom import GAME, rom_file_bytes
from .zora import archipelago as zora_ap
from .zora.rom.slot_identity import SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_SIZE

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("Client")

RAM = "RAM"
PRG_ROM = "PRG ROM"
PRG_SIZE = 0x20000
NES_HEADER_SIZE = 0x10
RECIPE_FORMAT = tuple(zora_ap.FORMAT_VERSION_NUMBERS)        # the recipe format this copy of ZORA makes
WATCHER_TIMEOUT = 0.125
LOCATION_ID_TO_NAME = {location_id: name for name, location_id in LOCATION_NAME_TO_ID.items()}


def world_version() -> str:
    """This world's version, from its manifest (archipelago.json), for the client's log."""
    try:
        return json.loads(pkgutil.get_data(__package__, "archipelago.json"))["world_version"]
    except Exception:
        return "unknown"


def read_list(tables: zora_ap.ClientTables) -> list[tuple[int, int]]:
    """client_step's reads, in order: the state bytes, the ranges, the state bytes again."""
    state = [(address, 1) for address in tables.state_addresses]
    return [*state, *tables.ranges, *state]


def snapshot(tables: zora_ap.ClientTables, values: list[bytes]) -> tuple[dict[int, int], dict[int, int]]:
    """The bytes read, as client_step takes them: `ram` (the first state read and the ranges) and
    `ram_after` (the second state read)."""
    count = len(tables.state_addresses)
    ram: dict[int, int] = {}
    for (start, _length), data in zip(read_list(tables)[:-count], values[:-count], strict=True):
        ram.update((start + offset, byte) for offset, byte in enumerate(data))
    ram_after = {address: data[0] for address, data in zip(tables.state_addresses, values[-count:], strict=True)}
    return ram, ram_after


def zora_name(name: str) -> str:
    return GIVEN_AS.get(name, name)


def server_view(ctx: BizHawkClientContext) -> zora_ap.ServerView:
    """What the server has said: the received items in order (with the place, by name, only when
    this slot found the item), this slot's checked places, and whether the goal was sent. An item
    Archipelago names its own way (Sword Upgrade, Bomb Upgrade) is passed as the code it is given
    as (names.GIVEN_AS): the seed's give rules then give the line's next level."""
    received = tuple(
        zora_ap.ReceivedItem(
            zora_name(ctx.item_names.lookup_in_game(item.item)),
            LOCATION_ID_TO_NAME.get(item.location) if item.player == ctx.slot else None)
        for item in ctx.items_received)
    checked = frozenset(LOCATION_ID_TO_NAME[location] for location in ctx.checked_locations
                        if location in LOCATION_ID_TO_NAME)
    return zora_ap.ServerView(received, checked, bool(ctx.finished_game))


class ZoraClient(BizHawkClient):
    game = GAME
    system = "NES"
    patch_suffix = ".apzora"

    def __init__(self) -> None:
        super().__init__()
        self.ap_name = b""
        self.memory = zora_ap.NO_MEMORY
        self.tables: zora_ap.ClientTables | None = None
        self.tables_of: dict[str, Any] | None = None
        self.last_error = ""

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        from worlds._bizhawk import RequestFailedError, get_memory_size, read

        try:
            if await get_memory_size(ctx.bizhawk_ctx, PRG_ROM) != PRG_SIZE:
                return False
            prg_address = SLOT_IDENTITY_ADDRESS - NES_HEADER_SIZE
            (record,) = await read(ctx.bizhawk_ctx, [(prg_address, SLOT_IDENTITY_SIZE, PRG_ROM)])
        except RequestFailedError:
            return False
        identity = zora_ap.rom_identity(bytes(SLOT_IDENTITY_ADDRESS) + record)
        if identity is None:
            return False
        if tuple(identity.format_version) != RECIPE_FORMAT:
            logger.warning(f"This ZORA ROM was made by recipe format {identity.format_version}, but this "
                           f"client reads {RECIPE_FORMAT}: use the .apworld that generated it.")
            return False
        try:
            zora_ap.client_ready(rom_file_bytes())
        except Exception as error:
            logger.error(f"ZORA: can't use your Zelda ROM (host.yaml zora_options rom_file): {error}")
            return False
        self.ap_name = identity.ap_name
        self.memory = zora_ap.NO_MEMORY
        ctx.game = self.game
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        ctx.watcher_timeout = WATCHER_TIMEOUT
        logger.info(f"ZORA world {world_version()}: recognized the ROM for {identity.ap_name.decode(errors='replace')}")
        return True

    async def set_auth(self, ctx: BizHawkClientContext) -> None:
        if self.ap_name:
            ctx.auth = b64encode(self.ap_name).decode()

    def client_tables(self, slot_data: dict[str, Any]) -> zora_ap.ClientTables | None:
        if self.tables_of is not slot_data:
            self.tables_of = slot_data
            try:
                self.tables = zora_ap.client_tables_from_json(slot_data["client_tables"])
            except (KeyError, zora_ap.ClientTablesRefused) as refused:
                self.tables = None
                logger.error(f"ZORA: this game was generated by another ZORA world version ({refused}); "
                             f"install the zora.apworld it was generated with.")
        return self.tables

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        from worlds._bizhawk import RequestFailedError, guarded_write, read

        if ctx.server is None or ctx.slot_data is None:
            return
        tables = self.client_tables(ctx.slot_data)
        if tables is None:
            return
        try:
            values = await read(ctx.bizhawk_ctx, [(start, length, RAM) for start, length in read_list(tables)])
        except RequestFailedError:
            return
        ram, ram_after = snapshot(tables, values)
        try:
            decision = zora_ap.client_step(ram, ram_after, server_view(ctx), tables, self.memory)
        except Exception as error:      # never let one tick stop the client (docs/archipelago.md)
            if str(error) != self.last_error:
                self.last_error = str(error)
                logger.exception(f"ZORA: client_step failed; trying again: {error}")
            return

        if decision.report:
            locations = [LOCATION_NAME_TO_ID[name] for name in decision.report]
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": locations}])
        if decision.goal:
            ctx.finished_game = True
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        if decision.writes:
            try:
                written = await guarded_write(
                    ctx.bizhawk_ctx,
                    [(address, [value], RAM) for address, value in decision.writes],
                    [(address, [value], RAM) for address, value in decision.guards])
            except RequestFailedError:
                return
            if not written:
                return              # the game moved on since the read: decided again next tick
            count = dict(decision.writes)[zora_ap.RECEIVED_COUNT]
            # the server's name for it (Sword Upgrade), not the code it was given as
            shown = (ctx.item_names.lookup_in_game(ctx.items_received[count - 1].item)
                     if 0 < count <= len(ctx.items_received) else None)
            if decision.gives:
                logger.info(f"ZORA: gave received item #{count}, {shown or decision.gives}")
            elif decision.skips:
                logger.info(f"ZORA: received item #{count}, {shown or decision.skips}, was taken in this file "
                            f"(already held)")
            elif decision.cannot_give:
                logger.warning(f"ZORA: received item #{count}, {shown or decision.cannot_give}, isn't an item ZORA "
                               f"gives; skipped")
        self.memory = decision.memory
