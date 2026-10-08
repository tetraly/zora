"""The ZORA extras as the generation pass sees them (docs/zora-extras.md):
each extra's switch, tested at its one call site, and the heart figures the
magical sword's heart check needs. The defaults are every extra off, which
is today's generator."""
from __future__ import annotations

from dataclasses import dataclass

from zora.generate.acceptance_check import LogicRules, logic_rules
from zora.generate.steps.change_sword_hearts import MAGICAL_SWORD_HEARTS
from zora.generate.steps.overworld_gates import NO_GATES, OverworldGates


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

    @property
    def logic_rules(self) -> LogicRules:
        """The acceptance check's rules under these flags (plan section 5, the overworld gates)."""
        return logic_rules(self.progressive_items, self.shop_items_in_pool, self.gates)


# Every ZORA extra off: the default where none are given.
NO_EXTRAS = ExtraOptions()
