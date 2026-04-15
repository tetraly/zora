"""
Replace Book Fire with Explosion.

Replaces the Book of Magic's fire projectile effect with a bomb
explosion effect. Writes a 13-byte ASM routine at 0x1FFE7.

"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class ReplaceBookFireWithExplosion(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.replace_book_fire_with_explosion

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            # JSR $714F; LDA #$12; STA $AC,X; LDA #$10; STA $0603; RTS
            # Redirects the book projectile handler to spawn a bomb explosion
            # sprite (type $12) and set the damage value ($10) at $0603.
            RomEdit(
                offset=0x1FFE7,
                new_bytes="20 4F 71 A9 12 95 AC A9 10 8D 03 06 60",
                old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment="Replace book fire projectile with bomb explosion effect",
            ),
        ]
