"""
Magical Boomerang Does 1 HP Damage.

Changes the magical boomerang to deal 1 HP of damage (equivalent to the wood
sword) to enemies. Note that a boomerang may damage an enemy multiple times in
one shot.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class MagicalBoomerangDamage(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.magical_boomerang_does_one_hp_damage

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x7478,
                new_bytes=(
                    "A9 50 99 AC 00 BD B2 04 25 09 F0 04 20 C5 7D "
                    "60 AD 75 06 0A 0A 0A 0A 85 07 A9 10 95 3D EA"
                ),
                old_bytes=(
                    "BD B2 04 25 09 F0 03 20 C5 7D A9 50 99 AC 00 "
                    "BD B2 04 25 09 D0 5A A9 00 85 07 A9 10 95 3D BD"
                ),
                comment="Magical boomerang deals 1 HP damage to enemies",
            ),
        ]
