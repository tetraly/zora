"""The base ROM, and the patch file a player receives.

The base ROM is the player's own The Legend of Zelda (USA): PRG0 or PRG1 (Rev 1), with or without
modified graphics. ZORA's identify_rom (zora/rom/revision.py) is the one check, here as on ZORA's
web page, so host.yaml accepts exactly the ROMs ZORA does.

The patch carries ZORA's recipe (recipe.json) and no ROM data. Its one procedure step,
zora_rom_from_recipe, runs this world's copy of zora/ on the player's own ROM, which rebuilds
exactly the ROM made at generation (pinned by the copy's source hash), on the player's release.
The organizer's ROM and a player's may be different releases.
"""
import json
from typing import ClassVar

import settings
from worlds.Files import APPatchExtension, APProcedurePatch

from .zora import archipelago as zora_ap
from .zora.rom.revision import RomNotRecognized, identify_rom

GAME = "ZORA"
RECIPE_FILE = "recipe.json"


class ZoraSettings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File name of The Legend of Zelda (USA) ROM: PRG0 or PRG1 (Rev 1), with or without modified graphics"""
        description = "The Legend of Zelda (USA) ROM File"
        copy_to = "Legend of Zelda, The (U) (PRG0) [!].nes"

        @classmethod
        def validate(cls, path: str) -> None:
            """ZORA's own check (identify_rom) instead of a list of MD5s, which can't name a ROM
            with modified graphics."""
            with open(path, "rb") as rom:
                data = rom.read()
            try:
                identify_rom(data)
            except RomNotRecognized as refused:
                raise ValueError(f"{path}: {refused}") from refused

    rom_file: RomFile = RomFile(RomFile.copy_to)


def rom_file_bytes() -> bytes:
    """The ROM host.yaml names (zora_options rom_file), as read (Archipelago's settings have
    validated it)."""
    path = settings.get_settings().zora_options.rom_file
    with open(path, "rb") as rom:
        return rom.read()


def base_rom_bytes() -> bytes:
    return zora_ap.checked_rom(rom_file_bytes())


class ZoraProcedurePatch(APProcedurePatch):
    # No single base checksum: any release identify_rom knows will do (Archipelago only records it).
    hash = None
    game = GAME
    patch_file_ending = ".apzora"
    result_file_ending = ".nes"
    procedure: ClassVar = [("zora_rom_from_recipe", [RECIPE_FILE])]

    @classmethod
    def get_source_data(cls) -> bytes:
        return base_rom_bytes()

    def write_recipe(self, recipe: dict) -> None:
        self.write_file(RECIPE_FILE, json.dumps(recipe, sort_keys=True).encode())


class ZoraPatchExtension(APPatchExtension):
    game = GAME

    @staticmethod
    def zora_rom_from_recipe(caller: APProcedurePatch, rom: bytes, recipe_file: str) -> bytes:
        return zora_ap.rom_from_recipe(json.loads(caller.get_file(recipe_file)), rom)
