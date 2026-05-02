"""
Visual Roar Sound.

Patches dungeon entry to display a beast sound above the level number
instead of the vanilla "LIFE" label. The specific sound is driven by
the visual_roar_sound flag (ROAR, RAWR, MEOW, WOOF, HISS, HONK).

Also writes the supporting display routine (PPU nametable update) and
all label tile data into unused ROM space.

ROM version note: PRG1 rom[0x1C00] == 0x4C, so the base address offset
is always 10 and block1 is always at 0x15363.
"""
from flags.flags_generated import VisualRoarSound
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch

# Tile data for each sound: " -XXXX- " encoded with Zelda 1 tile indices.
# Each entry is 9 bytes; the table is laid out at 0x16C80 with sounds at
# consecutive 9-byte slots. The index loaded into $0108 selects the slot.
# Slot 0 is reserved for the vanilla LIFE label; chosen sounds occupy slots 1+.
_LIFE_TILES = "24 2F 15 12 0F 0E 2F 24 24"

_SOUND_TILES: dict[VisualRoarSound, tuple[int, str]] = {
    # (table_index, tile_hex_string)
    VisualRoarSound.ROAR: (1,  "24 2F 1B 18 0A 1B 2F 24 24"),
    VisualRoarSound.RAWR: (2,  "24 2F 1B 0A 20 1B 2F 24 24"),
    VisualRoarSound.MEOW: (3,  "24 2F 16 0E 18 20 2F 24 24"),
    VisualRoarSound.WOOF: (4,  "24 2F 20 18 18 0F 2F 24 24"),
    VisualRoarSound.HISS: (5,  "24 2F 11 12 1C 1C 2F 24 24"),
    VisualRoarSound.HONK: (6,  "24 2F 11 18 17 14 2F 24 24"),
}

_TABLE_BASE = 0x16C80
_SLOT_SIZE  = 9


class VisualRoar(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.visual_roar_sound not in (VisualRoarSound.DISABLED, VisualRoarSound.RANDOM)

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        from unittest.mock import MagicMock
        edits: list[RomEdit] = []
        seen: set[tuple[int, bytes]] = set()
        for sound in _SOUND_TILES:
            config = MagicMock()
            config.visual_roar_sound = sound
            for edit in self.get_edits_for_config(config):
                key = (edit.offset, edit.new_bytes)
                if key not in seen:
                    seen.add(key)
                    edits.append(edit)
        return edits

    def get_edits_for_config(self, config: GameConfig, rom_version: int | None = None) -> list[RomEdit]:
        table_index, tile_hex = _SOUND_TILES[config.visual_roar_sound]
        # LDA #(table_index * 9) selects which label slot the PPU loop reads.
        lda_index = table_index * _SLOT_SIZE

        edits: list[RomEdit] = [
            # Block 1: Main display routine at 0x15363 (23 bytes, num2=10).
            # Replaces the tail of the vanilla dungeon-entry routine with a
            # JMP to our trampoline, then appends the label-selector sub-routine.
            # LDA #<lda_index> loads the table offset for the chosen sound.
            RomEdit(
                offset=0x15363,
                new_bytes=(
                    f"4C 61 93 60 A9 00 8D 08 01 A9 80 4C 80 6D "
                    f"8D 01 06 A9 {lda_index:02X} 8D 08 01 60"
                ),
                old_bytes="8D 01 06 60 A9 80 4C 80 6D FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment=(
                    f"Redirect dungeon-entry routine to label display trampoline"
                    f" (sound={config.visual_roar_sound.name})"
                ),
            ),
            # Block 2: JSR trampoline at 0x16CA3 (3 bytes, unused ROM).
            RomEdit(
                offset=0x16CA3,
                new_bytes="20 A0 AC",
                old_bytes="FF FF FF",
                comment="JSR $ACA0 trampoline for PPU nametable update",
            ),
            # Block 3: PPU nametable update routine at 0x16CB0 (39 bytes, unused ROM).
            # Reads 9 tiles from the label table at $AC70 indexed by $0108 and
            # writes them to nametable address $2076.
            RomEdit(
                offset=0x16CB0,
                new_bytes=(
                    "A9 20 8D 2A 03 A9 76 8D 2B 03 A9 09 8D 2C 03 "
                    "A9 FF 8D 36 03 AD 08 01 A8 A2 00 B9 70 AC "
                    "9D 2D 03 C8 E8 E0 09 D0 F4 60"
                ),
                old_bytes="FF " * 38 + "FF",
                comment="PPU nametable write loop for label tiles",
            ),
            # Block 4a: Vanilla LIFE label at slot 0 (matches reference layout).
            RomEdit(
                offset=_TABLE_BASE,
                new_bytes=_LIFE_TILES,
                old_bytes="FF FF FF FF FF FF FF FF FF",
                comment="Slot 0: vanilla LIFE label",
            ),
            # Block 4b: Tile data for the chosen sound at its slot in the table.
            RomEdit(
                offset=_TABLE_BASE + table_index * _SLOT_SIZE,
                new_bytes=tile_hex,
                old_bytes="FF FF FF FF FF FF FF FF FF",
                comment=f"Label tile data for {config.visual_roar_sound.name}",
            ),
        ]
        return edits
