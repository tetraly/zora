"""The ZORA extras as the generation pass sees them (docs/zora-extras.md):
each extra's switch, tested at its one call site, and the heart figures the
magical sword's heart check needs. The defaults are every extra off, which
is today's generator."""
from __future__ import annotations

from dataclasses import dataclass

from .acceptance_check import LogicRules, logic_rules
from .steps.change_sword_hearts import MAGICAL_SWORD_HEARTS
from .steps.overworld_gates import NO_GATES, OverworldGates


@dataclass(frozen=True)
class ExtraOptions:
    randomize_magical_sword: bool = False
    randomize_letter: bool = False
    # The heart counts the magical-sword cave may ask for (FP-SWORD-01 with the ZORA cap,
    # zora_flags.magical_sword_heart_range): change_sword_hearts draws from it.
    magical_sword_hearts: range = MAGICAL_SWORD_HEARTS
    # M, the heart containers Link starts with (FL-DEP-03, C16 + 1)
    starting_heart_containers: int = 3
    # Progressive Items and Shop Items in the Item Pool (docs/design/progressive-items-plan.md)
    progressive_items: bool = False
    shop_items_in_pool: bool = False
    # The owner's 2.0 overworld gates (Extra Raft / Power Bracelet Blocks, Randomize Lost Hills /
    # Dead Woods), resolved
    gates: OverworldGates = NO_GATES
    # Shuffle Blue Potion (merged with plan Phase 2B) and Add L4 Sword, resolved
    shuffle_blue_potion: bool = False
    add_l4_sword: bool = False
    # All Swords No Boards (docs/design/asnb.md): Add L4 Sword's sword in a new level-2 item cellar
    # (Add L4 Sword = Level 2), and level 9 opening for a level-4 sword
    l4_sword_in_level_2: bool = False
    level_9_entrance_sword: bool = False

    @property
    def l4_sword_in_level_9(self) -> bool:
        return self.add_l4_sword and not self.l4_sword_in_level_2

    @property
    def checks_magical_sword_hearts(self) -> bool:
        """The owner's heart check for the magical-sword cave (randomize_magical_sword.py): with
        Randomize Magical Sword, and with level 9 opening for a level-4 sword, which needs the
        magical sword whatever cave or place holds it."""
        return self.randomize_magical_sword or self.level_9_entrance_sword

    @property
    def logic_rules(self) -> LogicRules:
        """The acceptance check's rules under these flags (plan section 5, the overworld gates,
        ASNB's level-9 entrance)."""
        return logic_rules(self.progressive_items, self.shop_items_in_pool, self.gates,
                           level_9_by_swords=self.level_9_entrance_sword,
                           magical_sword_cave_counts=not self.randomize_magical_sword)


# Every ZORA extra off: the default where none are given.
NO_EXTRAS = ExtraOptions()
