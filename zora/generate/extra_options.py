"""The ZORA extras as the generation pass sees them (docs/zora-extras.md):
each extra's switch, tested at its one call site, and the heart figures the
magical sword's heart check needs. The defaults are every extra off, which
is today's generator."""
from __future__ import annotations

from dataclasses import dataclass

from ..flags.fields import WoodenSwordState
from ..flags.zora_flags import OopsAllBosses, OopsAllEnemies
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
    # Not a ZORA extra: every overworld quest but the first (C01 = 1, 2, 3) has the eleven-screen
    # recorder set the acceptance rules read (OW-MIX-08, OW-QST-04); here because logic_rules is
    # built from these options
    eleven_screen_recorder_set: bool = False
    # Allow Important Items in 9 (B25, VA-REJ-08): level 9's items need level-9 entry, not the long items
    important_items_in_level_9: bool = False
    # Swords (C07, resolved; VA-REJ-22): the acceptance walk's start, target and sword rules
    wooden_sword_state: WoodenSwordState = WoodenSwordState.NORMAL
    # Not a ZORA extra: Book to Understand NPCs (B48, HT-BOOK-01) without the book among the start
    # items, so the maze paths the hint shops sell need the book (LogicRules.maze_hints_need_book).
    # Start Book (B67) is not produced yet; see the TODO at flags/support.py START_ITEM_TOGGLES.
    maze_hints_need_book: bool = False
    # Oops All Enemies and Oops All Bosses (docs/design/oops-all.md), and the key of their own
    # random stream (zora_flags.oops_all_seed)
    oops_all_enemies: OopsAllEnemies = OopsAllEnemies.OFF
    oops_all_bosses: OopsAllBosses = OopsAllBosses.OFF
    oops_all_seed: int = 0
    # The ZORA 1.0 flags (docs/zora-extras.md section 13), resolved
    # Allow Triforces in Stairways, resolved (off unless C06 = 2)
    allow_triforces_in_stairways: bool = False
    # Shuffle Wood Sword, resolved
    shuffle_wood_sword: bool = False
    # Pegasus Boots, resolved: hint text names the boomerangs' items as the boots
    pegasus_boots: bool = False
    # Expanded Dungeon Locations, resolved, and the key of its own random stream
    # (expanded_dungeon_locations_seed)
    expanded_dungeon_locations: bool = False
    expanded_dungeon_locations_seed: int = 0
    # Highlight No-Drop Rooms, resolved (the pass is skipped when B91 resolves on)
    highlight_no_drop_rooms: bool = False

    @property
    def oops_all(self) -> bool:
        return bool(self.oops_all_enemies or self.oops_all_bosses)

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
                           magical_sword_cave_counts=not self.randomize_magical_sword,
                           eleven_screen_recorder_set=self.eleven_screen_recorder_set,
                           important_items_in_level_9=self.important_items_in_level_9,
                           maze_hints_need_book=self.maze_hints_need_book,
                           wood_sword_in_pool=self.shuffle_wood_sword,
                           wooden_sword_state=self.wooden_sword_state,
                           expanded_recorder_set=self.expanded_dungeon_locations)


# Every ZORA extra off: the default where none are given.
NO_EXTRAS = ExtraOptions()
