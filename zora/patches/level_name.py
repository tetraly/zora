"""
Level Name Patch.

Replaces the 6-byte dungeon HUD label "LEVEL-" with an alternative name.
The label is followed by the level number digit (1-9) which is written
separately by the game engine and is not affected by this patch.

Five-letter names (and shorter, space-padded) get a trailing dash tile
(0x62 in HUD tile encoding). Six-letter names fill all 6 bytes with no
dash.
"""
from flags.flags_generated import LevelName
from zora.char_encoding import CHAR_TO_BYTE
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch
from zora.rom_layout import LEVEL_NAME_DASH_TILE, LEVEL_NAME_LENGTH, LEVEL_NAME_OFFSET

# Mapping from enum value to the display string. Strings are either 5 chars
# (get a trailing dash) or 6 chars (fill the full slot). Shorter names are
# right-padded with spaces in the source array so all are 5 or 6 chars.
_NAME_STRINGS: dict[LevelName, str] = {
    LevelName.LEVEL:       "LEVEL",
    LevelName.ABODE:       "ABODE",
    LevelName.ACT:         "ACT  ",
    LevelName.AREA:        "AREA ",
    LevelName.ASYLUM:      "ASYLUM",
    LevelName.BOARD:       "BOARD",
    LevelName.CAGE:        "CAGE ",
    LevelName.CAMP:        "CAMP ",
    LevelName.CAVE:        "CAVE ",
    LevelName.CORRAL:      "CORRAL",
    LevelName.LAIR:        "LAIR ",
    LevelName.PALACE:      "PALACE",
    LevelName.PLACE:       "PLACE",
    LevelName.RANDOM_NAME: "RANDOM",
    LevelName.REALM:       "REALM",
    LevelName.REGION:      "REGION",
    LevelName.SECTOR:      "SECTOR",
    LevelName.SPHERE:      "SPHERE",
    LevelName.STAGE:       "STAGE",
    LevelName.TEMPLE:      "TEMPLE",
    LevelName.WORLD:       "WORLD",
    LevelName.ZONE:        "ZONE ",
}

# Vanilla bytes at the level name offset (LEVEL-)
_OLD_BYTES = bytes([0x15, 0x0E, 0x1F, 0x0E, 0x15, 0x62])


def _encode_name(name: str) -> bytes:
    """Encode a level name string to 6 NES tile bytes.

    Appends a dash tile for names shorter than 6 characters (truncated to 6).
    """
    full = name + "-"
    result: list[int] = []
    for i in range(LEVEL_NAME_LENGTH):
        ch = full[i]
        if ch == "-":
            result.append(LEVEL_NAME_DASH_TILE)
        else:
            result.append(CHAR_TO_BYTE[ch])
    return bytes(result)


class ChangeLevelName(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.level_name != LevelName.LEVEL

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        from unittest.mock import MagicMock
        edits: list[RomEdit] = []
        seen: set[tuple[int, bytes]] = set()
        for name in _NAME_STRINGS:
            if name == LevelName.LEVEL:
                continue
            config = MagicMock()
            config.level_name = name
            for edit in self.get_edits_for_config(config):
                key = (edit.offset, edit.new_bytes)
                if key not in seen:
                    seen.add(key)
                    edits.append(edit)
        return edits

    def get_edits_for_config(
        self, config: GameConfig, rom_version: int | None = None,
    ) -> list[RomEdit]:
        name_str = _NAME_STRINGS[config.level_name]
        new_bytes = _encode_name(name_str)
        return [
            RomEdit(
                offset=LEVEL_NAME_OFFSET,
                new_bytes=new_bytes,
                old_bytes=_OLD_BYTES,
                comment=f"Level name: {name_str.strip()!r}",
            ),
        ]
