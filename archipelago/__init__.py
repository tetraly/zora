"""ZORA, the Zelda One Randomizer App, as an Archipelago world (unofficial).

ZORA does the game-specific work through its Archipelago interface (zora/archipelago.py; the
.apworld holds ZORA's zora/ package from the same commit, scripts/build_apworld.py):
- build() makes the seed with ZORA's own generator and lists its item places and access rules;
- Archipelago fills those places;
- finish() writes Archipelago's items into the seed (checking it with ZORA's own walk), and
  the patch carries only ZORA's recipe, which the player's machine turns back into the ROM.

Generation needs a The Legend of Zelda (USA) ROM (host.yaml zora_options.rom_file): PRG0 or PRG1,
with or without modified graphics (rom.py). Each player's machine bakes from its own.
"""
import base64
import threading
from typing import Any, ClassVar

from BaseClasses import Item, ItemClassification, Location, MultiWorld, Region, Tutorial
from worlds.AutoWorld import WebWorld, World

from .client import ZoraClient  # noqa: F401  registers the BizHawk client
from .names import FILLER_ITEMS, HEART_CONTAINER, ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID
from .options import ZoraOptions, player_settings, zora_values
from .rom import GAME, ZoraProcedurePatch, ZoraSettings, base_rom_bytes
from .rules import state_rule
from .zora import archipelago as zora_ap
from .zora.generate.pipeline import SEED_LIMIT
from .zora.model.item_names import ITEM_NAMES
from .zora.rom.slot_identity import MAX_NAME_LENGTH as AP_NAME_LENGTH


class ZoraItem(Item):
    game = GAME


class ZoraLocation(Location):
    game = GAME


class ZoraWeb(WebWorld):
    theme = "grass"
    tutorials: ClassVar[list[Tutorial]] = []


class ZoraWorld(World):
    """ZORA reimagines The Legend of Zelda: new dungeon shapes, shuffled caves and shops, and
    many ways to replay the game. Here its items are shuffled across the multiworld."""
    game = GAME
    web = ZoraWeb()
    options_dataclass = ZoraOptions
    options: ZoraOptions
    settings: ClassVar[ZoraSettings]
    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    origin_region_name = "Menu"

    built: zora_ap.BuildResult
    places: list[zora_ap.PlaceInfo]
    pool: list[str]

    def __init__(self, multiworld: MultiWorld, player: int) -> None:
        super().__init__(multiworld, player)
        self.rom_name = b""
        self.rom_name_available = threading.Event()

    def generate_early(self) -> None:
        values = zora_values(self.options)
        flag_string, zora_flag_string = zora_ap.flag_strings(values)
        self.settings_values = player_settings(self.options)
        zora_ap.check_player_settings(self.settings_values)    # refused now, not at output
        seed = self.random.randrange(SEED_LIMIT)
        self.built = zora_ap.build_from_strings(flag_string, zora_flag_string, seed, base_rom_bytes())
        self.places, self.pool = list(self.built.places), list(self.built.pool)
        unexpected = sorted({name for name in self.pool if name not in ITEM_NAME_TO_ID})
        if unexpected:
            # receivable() is the item table; ZORA's pools never hold another item (its tests)
            raise RuntimeError(f"ZORA ({self.player_name}): this seed's pool holds {', '.join(unexpected)}, "
                               f"which aren't Archipelago items; please report the YAML to ZORA")

    def create_regions(self) -> None:
        menu = Region(self.origin_region_name, self.player, self.multiworld)
        model = self.built.logic
        for place in self.places:
            location = ZoraLocation(self.player, place.name, LOCATION_NAME_TO_ID[place.name], menu)
            location.access_rule = state_rule(model.places[place.name], self.player, model)
            forbidden = frozenset(place.forbids)
            location.item_rule = lambda item, forbidden=forbidden: (
                item.player != self.player or item.name not in forbidden
            )
            menu.locations.append(location)
        for event, rule in model.events.items():
            location = ZoraLocation(self.player, event, None, menu)
            location.access_rule = state_rule(rule, self.player, model)
            location.place_locked_item(ZoraItem(event, ItemClassification.progression, None, self.player))
            menu.locations.append(location)
        self.multiworld.regions.append(menu)
        goal = state_rule(model.goal, self.player, model)
        self.multiworld.completion_condition[self.player] = goal

    def create_item(self, name: str) -> ZoraItem:
        return ZoraItem(name, self.classification(name), ITEM_NAME_TO_ID[name], self.player)

    def classification(self, name: str) -> ItemClassification:
        if name in FILLER_ITEMS:
            return ItemClassification.filler
        if not hasattr(self, "built"):
            # an item-link group's world, which has no build of its own: progression is the safe side
            return ItemClassification.progression
        progression = {ITEM_NAMES[item] for item in self.built.logic.progression}
        if name in progression or name == HEART_CONTAINER:
            return ItemClassification.progression
        return ItemClassification.useful

    def create_items(self) -> None:
        self.multiworld.itempool += [self.create_item(name) for name in self.pool]

    def get_filler_item_name(self) -> str:
        return "Blue Potion"

    def generate_output(self, output_directory: str) -> None:
        try:
            assignment: dict[str, str | zora_ap.Foreign] = {}
            for place in self.places:
                item = self.multiworld.get_location(place.name, self.player).item
                assert item is not None
                assignment[place.name] = item.name if item.player == self.player else zora_ap.FOREIGN
            received = [
                location.item.name
                for location in self.multiworld.get_filled_locations()
                if location.item is not None and location.item.player == self.player
                and location.item.code is not None and location.player != self.player
            ]
            ap_name = self.ap_name()
            # ZORA's sanity check (R4)
            zora_ap.finish(self.built, assignment, received, self.settings_values, ap_name=ap_name)
            patch = ZoraProcedurePatch(player=self.player, player_name=self.player_name)
            patch.write_recipe(zora_ap.recipe(self.built, assignment, received, self.settings_values, ap_name=ap_name))
            self.rom_name = ap_name
            out_base = self.multiworld.get_out_file_name_base(self.player)
            patch.write(f"{output_directory}/{out_base}{patch.patch_file_ending}")
        finally:
            self.rom_name_available.set()

    def ap_name(self) -> bytes:
        """The slot name written into the ROM, which the client logs in with: unique in this
        multiworld by player number, and tied to the seed. ZORA takes 1-23 bytes."""
        return f"ZORA{self.player}_{self.multiworld.seed_name}".encode()[:AP_NAME_LENGTH]

    def fill_slot_data(self) -> dict[str, Any]:
        return {"client_tables": zora_ap.client_tables_to_json(self.built)}

    def modify_multidata(self, multidata: dict[str, Any]) -> None:
        self.rom_name_available.wait()
        if self.rom_name:
            name = base64.b64encode(self.rom_name).decode()
            multidata["connect_names"][name] = multidata["connect_names"][self.player_name]
