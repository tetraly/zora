"""
Book Is An Atlas.

Makes the Book of Magic function as an atlas (shows the overworld map).

"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class BookIsAnAtlas(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.book_is_an_atlas

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x17614,
                new_bytes="4C A0 B8",
                old_bytes="39 BE E6",
                comment="JMP $B8A0: redirect overworld map display to atlas routine",
            ),
            RomEdit(
                offset=0x06C35,
                new_bytes="4C 43 FF",
                old_bytes="99 57 06",
                comment="JMP $FF43: redirect JSR to item-store routine",
            ),
            RomEdit(
                offset=0x178B0,
                new_bytes="E0 11 F0 04 E0 13 D0 07 39 BE E6 0D 61 06 60 39 BE E6 60",
                old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment="19-byte item-check routine: CPX #$11; BEQ +4; CPX #$13; BNE +7; AND/ADC/RTS paths",
            ),
            RomEdit(
                offset=0x1FF53,
                new_bytes="99 57 06 E0 11 D0 03 8E E5 04 4C 94 ED",
                old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment="13-byte item-store routine: STA $0657,Y; CPX #$11; BNE +3; STX $04E5; JMP $ED94",
            ),
            RomEdit(
                offset=0x1EDA4,
                new_bytes="60",
                old_bytes="FF",
                comment="RTS guard: prevents crash at removeHigherSwords stub (not yet implemented)",
            ),
        ]
