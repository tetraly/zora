"""
Book Is A Translator.

Makes the Book of Magic function as a translator, showing readable hint text
from old men (blocks text display unless the player has the book).

"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class BookIsATranslator(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.book_is_a_translator

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x04847,
                new_bytes="20 30 9F",
                old_bytes="B9 00 80",
                comment="JSR $9F30: redirect text display through book-check routine",
            ),
            RomEdit(
                offset=0x05F40,
                new_bytes="AD 61 06 D0 06 C0 44 F0 02 A0 00 B9 00 80 60",
                old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment="15-byte book-check routine: LDA $0661; BNE +6; CPY #$44; BEQ +2; LDY #$00; LDA $8000,Y; RTS",
            ),
        ]
