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
stops a session. So is an ERROR from the connector (a ConnectorError; inside an ExceptionGroup on
Python 3.11 and later): z1rr-coop's console bridge answers ERROR while the console can't be read
(an EverDrive between screens or off the play screen), so that tick is skipped like a timeout,
logged only when its message changes.

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
        self.last_connector_error = ""
        self.hud_seen: dict | None = None   # see hud_seen_load
        self.hud_reset()

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        from worlds._bizhawk import RequestFailedError, get_memory_size, read

        try:
            if await get_memory_size(ctx.bizhawk_ctx, PRG_ROM) not in (PRG_SIZE, 2 * PRG_SIZE):
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
        self.hud_reset()                    # messages for the last game must not show on this ROM
        ctx.game = self.game
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        ctx.watcher_timeout = WATCHER_TIMEOUT
        logger.info(f"ZORA world {world_version()}: recognized the ROM for {identity.ap_name.decode(errors='replace')}")
        return True

    # fceux-archipelago patch: HUD messages
    # Item messages go in the blank top row of the status bar (nametable $2022, 28 columns), written
    # through the game's tile buffer: DynTileBuf at $0302, with $0301 the index of its $FF end. The NMI
    # copies it to the PPU and resets it. Written in play ($12=5, $13=0) and cellars ($12=9/$A)
    # while the buffer is empty, so the game's own records go after ours, or in play and caves
    # ($12=$B/$C) in place of that frame's status-bar redraw, which the game sends again.
    # Item names too long for the status-bar row (player's choice, 2026-11-20).
    HUD_SHORT_NAMES = {
        "Wood Sword": "SWORD", "White Sword": "W SWORD", "Magical Sword": "M SWORD",
        "Blue Candle": "B CANDLE", "Red Candle": "R CANDLE", "Wooden Arrow": "ARROWS",
        "Silver Arrow": "SILVERS", "Magical Key": "MAGIC KEY", "Triforce of Power": "TRIFORCE",
        "5 Rupees": "FIVER", "Blue Ring": "B RING", "Red Ring": "R RING",
        "Power Bracelet": "PB", "Heart Container": "HC", "Triforce": "TRI",
        "Boomerang": "BOOMER", "Magical Boomerang": "M BOOMER", "Blue Potion": "BLUE POT",
        "Red Potion": "RED POT", "Sword Upgrade": "SWORD UP", "Candle Upgrade": "CANDLE UP",
        "Arrow Upgrade": "ARROW UP", "Bomb Upgrade": "BOMB UP", "Boots Upgrade": "BOOTS UP",
        "Pegasus Boots": "BOOTS", "Magical Boots": "M BOOTS",
        # Items of the other games in a multiworld
        "Erdrick's Token": "TOKEN", "Erdrick's Sword": "E SWORD", "Erdrick's Armor": "E ARMOR",
        "Stones of Sunlight": "SUN STONES", "Magic Container": "MAGIC CONT",
        "Blue Magic Jar": "BLUE JAR", "Red Magic Jar": "RED JAR",
    }
    HUD_ROW = 0x2022
    HUD_WIDTH = 28
    HUD_SECONDS = 10.0
    HUD_SECONDS_BUSY = 5.0      # each message's time while HUD_BUSY_AT or more are pending
    HUD_BUSY_AT = 4             # pending messages, the one going up included: 3 or fewer get 10 s, more get 5 s
    HUD_REDRAW = 1.0            # written again this often while shown, in case a screen change wiped it

    def on_package(self, ctx: BizHawkClientContext, cmd: str, args: dict) -> None:
        """Queue a HUD message for items this slot sent to other players (fceux-archipelago patch).
        Items this slot receives are announced where they are given (hud_got), since the server
        sends this notice only to clients connected at the time and never again."""
        if cmd != "PrintJSON" or args.get("type") != "ItemSend":
            return
        try:
            item = args["item"]
            receiver = args["receiving"]
            if item.player != ctx.slot or receiver == ctx.slot:
                return
            player = self.hud_player(ctx.player_names[receiver], ctx.player_names[ctx.slot])
            room = self.HUD_WIDTH - len("SENT  TO ") - len(player)
            name = self.hud_item(ctx.item_names.lookup_in_slot(item.item, receiver), room)
            # A live line goes ahead of any backlog of received-item lines.
            queue = self.hud_queue()
            at = 0
            while at < len(queue) and queue[at][1] == "sent":
                at += 1
            queue.insert(at, (f"SENT {name} TO {player}", "sent"))
        except Exception:      # a message is never worth stopping the client
            logger.exception("ZORA: could not queue an item message")

    def hud_got(self, ctx: BizHawkClientContext, item: Any, count: int) -> None:
        """Queue the line for received item number `count` as it is given. An item already announced
        for this seed and slot (given again after a switch from the battery save, or in a new save
        file) is folded into one "N ITEMS GIVEN BACK" line."""
        try:
            key = f"{getattr(ctx, 'seed_name', None)}:{ctx.slot}"
            seen = self.hud_seen_load().get(key, 0)
            if count <= seen:
                self.hud_given_back += 1
                n = self.hud_given_back
                line = (f"{n} ITEM GIVEN BACK" if n == 1 else f"{n} ITEMS GIVEN BACK", "back")
                queue = self.hud_queue()
                for i, entry in enumerate(queue):
                    if entry[1] == "back":
                        queue[i] = line
                        break
                else:
                    queue.append(line)
                return
            self.hud_seen[key] = count
            self.hud_seen_save()
            if item.location == -2:         # starting inventory: not news
                return
            name = self.hud_item
            if item.player == ctx.slot:
                text = f"GOT {name(ctx.item_names.lookup_in_game(item.item), self.HUD_WIDTH - 4)}"
            else:
                player = self.hud_player(ctx.player_names[item.player], ctx.player_names[ctx.slot])
                room = self.HUD_WIDTH - len(" FROM ") - len(player)
                text = f"{name(ctx.item_names.lookup_in_game(item.item), room)} FROM {player}"
            self.hud_queue().append((text, "got"))
        except Exception:      # a message is never worth stopping the client
            logger.exception("ZORA: could not queue an item message")

    def hud_seen_path(self) -> str:
        import Utils
        return Utils.user_path("zora_hud_seen.json")

    def hud_seen_load(self) -> dict:
        """The highest received-item number announced, per seed and slot, kept across client restarts."""
        if self.hud_seen is None:
            import json
            try:
                with open(self.hud_seen_path(), encoding="utf-8") as file:
                    self.hud_seen = {str(k): int(v) for k, v in json.load(file).items()}
            except (OSError, ValueError, AttributeError):
                self.hud_seen = {}
        return self.hud_seen

    def hud_seen_save(self) -> None:
        import json
        try:
            with open(self.hud_seen_path(), "w", encoding="utf-8") as file:
                json.dump(self.hud_seen, file)
        except OSError:
            logger.warning("ZORA: could not save which item messages were shown")

    @classmethod
    def hud_item(cls, name: str, room: int) -> str:
        """The full item name if it fits in `room`, else its short name cut to fit."""
        if len(cls.hud_shown(name)) <= room:
            return cls.hud_shown(name) or "ITEM"
        return cls.hud_fit(cls.HUD_SHORT_NAMES.get(name, name), room) or "ITEM"

    def hud_reset(self) -> None:
        self.hud_messages: list = []        # (text, kind): kind is "sent", "got" or "back"
        self.hud_given_back = 0             # items given again that were announced before
        self.hud_text: str | None = None    # the message on screen now, or None
        self.hud_until = 0.0
        self.hud_drawn_at = 0.0
        self.hud_dirty = False              # the row holds text that still has to be blanked

    def hud_queue(self) -> list:
        return self.hud_messages

    @staticmethod
    def hud_shown(text: str) -> str:
        from .zora.rom.text_encoding import CHAR_TO_BYTE
        kept = "".join(c if c in CHAR_TO_BYTE and c not in "~\"" else " " for c in text.upper().replace("'", ""))
        return " ".join(kept.split())

    @classmethod
    def hud_player(cls, name: str, mine: str = "") -> str:
        """A player's name for a HUD line. A prefix up to the first "-" that this slot's own name
        shares (Gob-ZORA and Gob-Z2R) is left off: "Z2R"."""
        if "-" in name and "-" in mine and name.split("-", 1)[0].lower() == mine.split("-", 1)[0].lower():
            name = name.split("-", 1)[1]
        return cls.hud_shown(name)[:11].rstrip() or "ANOTHER PLAYER"

    @classmethod
    def hud_fit(cls, name: str, room: int) -> str:
        """The item name in at most `room` characters, cut at the last whole word that fits."""
        shown = cls.hud_shown(name)
        if len(shown) <= room:
            return shown
        head = shown[:room + 1]
        if " " in head:
            return head.rsplit(" ", 1)[0].rstrip()
        return shown[:room]

    async def hud_write(self, ctx: BizHawkClientContext, text: str) -> bool:
        """Write text (blank for "") into the HUD row; False if the game was not ready this tick."""
        from worlds._bizhawk import guarded_write
        from .zora.rom.text_encoding import CHAR_TO_BYTE

        text = text[:self.HUD_WIDTH]
        text = " " * ((self.HUD_WIDTH - len(text)) // 2) + text      # centered in the row
        tiles = [CHAR_TO_BYTE.get(c, CHAR_TO_BYTE[" "]) for c in text]
        tiles += [CHAR_TO_BYTE[" "]] * (self.HUD_WIDTH - len(tiles))
        record = [self.HUD_ROW >> 8, self.HUD_ROW & 0xFF, self.HUD_WIDTH] + tiles + [0xFF]
        writes = [(0x0302, record, RAM), (0x0301, [len(record) - 1], RAM)]
        if await guarded_write(
                ctx.bizhawk_ctx, writes,
                [(0x12, [5], RAM), (0x13, [0], RAM), (0x11, [1], RAM), (0x14, [0], RAM), (0x0302, [0xFF], RAM),
                 (0x0301, [0], RAM)]):
            return True
        # In play the game also queues the status-bar redraw (20 B6 08) every second frame, which
        # fails the empty-buffer guard above on those frames. Replace it, as in caves below.
        if await guarded_write(
                ctx.bizhawk_ctx, writes,
                [(0x12, [5], RAM), (0x13, [0], RAM), (0x11, [1], RAM), (0x14, [0], RAM),
                 (0x0302, [0x20, 0xB6, 0x08], RAM)]):
            return True
        # Cellars (mode 9, and $A on the way out) play with GameSubmode left at its last init step
        # (9), so they need their own guard: updating ($11=1) with an empty buffer.
        for mode in (0x09, 0x0A):
            if await guarded_write(
                    ctx.bizhawk_ctx, writes,
                    [(0x12, [mode], RAM), (0x11, [1], RAM), (0x14, [0], RAM), (0x0302, [0xFF], RAM), (0x0301, [0], RAM)]):
                return True
        # Caves (modes $B, $C) take only the frames with the status-bar redraw (every second frame,
        # starting 20 B6 08, sent alone into an empty buffer). Replacing it is harmless: the game
        # sends it again two frames later. Text typing and other one-off records start
        # differently and are left alone.
        for mode in (0x0B, 0x0C):
            if await guarded_write(
                    ctx.bizhawk_ctx, writes,
                    [(0x12, [mode], RAM), (0x11, [1], RAM), (0x14, [0], RAM), (0x0302, [0x20, 0xB6, 0x08], RAM)]):
                return True
        return False

    async def hud_tick(self, ctx: BizHawkClientContext) -> None:
        import time
        from worlds._bizhawk import NotConnectedError, RequestFailedError

        queue = self.hud_queue()
        now = time.monotonic()
        try:
            if self.hud_text is not None and now >= self.hud_until:
                self.hud_text = None                    # time is up: blank it, or show the next one
            if self.hud_text is None:
                if queue:
                    text = queue[0][0]
                    if await self.hud_write(ctx, text):
                        busy = len(queue) >= self.HUD_BUSY_AT
                        queue.pop(0)
                        self.hud_text, self.hud_drawn_at, self.hud_dirty = text, now, True
                        self.hud_until = now + (self.HUD_SECONDS_BUSY if busy else self.HUD_SECONDS)
                elif self.hud_dirty and await self.hud_write(ctx, ""):
                    self.hud_dirty = False
            elif now - self.hud_drawn_at >= self.HUD_REDRAW and await self.hud_write(ctx, self.hud_text):
                self.hud_drawn_at = now
        except (RequestFailedError, NotConnectedError):
            return                      # the connection dropped: tried again once it is back
        except Exception as error:      # unknown whether it was written: tried again next tick
            # The HUD is optional, so no error here may stop the game watcher: log it once.
            message = f"{type(error).__name__}: {error}"
            if message != getattr(self, "hud_last_error", None):
                self.hud_last_error = message
                logger.warning(f"ZORA: could not write an item message; trying again: {message}")

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        await self.zora_game_watcher(ctx)
        if ctx.server is not None and ctx.slot_data is not None:
            await self.hud_tick(ctx)

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

    def skip_connector_error(self, error: Exception) -> None:
        """Skip a tick whose request the connector answered with ERROR (logged when its message
        changes); re-raise anything else."""
        from worlds._bizhawk import ConnectorError

        errors = getattr(error, "exceptions", (error,))      # an ExceptionGroup on Python 3.11+
        if not errors or not all(isinstance(each, ConnectorError) for each in errors):
            raise error
        message = "; ".join(str(each) for each in errors)
        if message != self.last_connector_error:
            self.last_connector_error = message
            logger.info(f"ZORA: the connector couldn't read the game; trying again: {message}")

    async def zora_game_watcher(self, ctx: BizHawkClientContext) -> None:
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
        except Exception as error:
            self.skip_connector_error(error)
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
            except Exception as error:      # unknown whether it was written: read again next tick
                self.skip_connector_error(error)
                return
            if not written:
                return              # the game moved on since the read: decided again next tick
            count = dict(decision.writes)[zora_ap.RECEIVED_COUNT]
            # the server's name for it (Sword Upgrade), not the code it was given as
            shown = (ctx.item_names.lookup_in_game(ctx.items_received[count - 1].item)
                     if 0 < count <= len(ctx.items_received) else None)
            if (decision.gives or decision.skips) and 0 < count <= len(ctx.items_received):
                self.hud_got(ctx, ctx.items_received[count - 1], count)
            if decision.gives:
                logger.info(f"ZORA: gave received item #{count}, {shown or decision.gives}")
            elif decision.skips:
                logger.info(f"ZORA: received item #{count}, {shown or decision.skips}, was taken in this file "
                            f"(already held)")
            elif decision.cannot_give:
                logger.warning(f"ZORA: received item #{count}, {shown or decision.cannot_give}, isn't an item ZORA "
                               f"gives; skipped")
        self.memory = decision.memory
