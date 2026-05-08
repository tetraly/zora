"""
Start Items ROM patch.

Installs four structural patches (always-on) plus a 40-byte inventory table
whose contents reflect the user's Start Items selections. Once the JMP hooks
at $9F4E and $AF8B are in place, the game *unconditionally* loads its new-save
inventory from the table at file offset 0xA850 — so the patcher must run on
every seed, even when the user selected nothing (in which case the table just
encodes vanilla defaults: 3 hearts, 8 max bombs, no items, no triforce).

Structure (all offsets are file offsets, including the iNES 16-byte header):

  0x9F4E (3 bytes): JMP $A830 — replaces vanilla LDY/LDA/STA save-init bytes
  0xA840 (13 bytes): ASM stub — copy 40-byte table into ($C0),Y save buffer
  0xA850 (40 bytes): inventory table (varies per seed)
  0xA880 (14 bytes): ASM stub — copy table into $0657,Y in-RAM save buffer
  0xAF8B (3 bytes): JMP $A870 — replaces vanilla LDA #$22 / STA $066F bytes

Slot map of the 40-byte table at 0xA850 (RAM addrs are $0657 + slot):

  slot  0 ($0657 Items):           sword tier (1=wood, 2=white, 3=magical)
  slot  1 ($0658 InvBombs):        current bomb count (8 if start_bombs)
  slot  2 ($0659 InvArrow):        arrow tier (1=wood, 2=silver)
  slot  3 ($065A Bow):             1 if bow granted
  slot  4 ($065B InvCandle):       candle tier (1=blue, 2=red)
  slot  5 ($065C):                 recorder (1 if granted)
  slot  6 ($065D InvFood):         bait (1 if granted)
  slot  7 ($065E Potion):          unused
  slot  8 ($065F):                 wand / magical rod (1 if granted)
  slot  9 ($0660 InvRaft):         raft (1 if granted)
  slot 10 ($0661 InvBook):         book (1 if granted)
  slot 11 ($0662 InvRing):         ring tier (1=blue, 2=red)
  slot 12 ($0663 InvLadder):       ladder (1 if granted)
  slot 13 ($0664 InvMagicKey):     magical key (1 if granted)
  slot 14 ($0665 InvBracelet):     power bracelet (1 if granted)
  slot 15 ($0666 InvLetter):       letter (1 if granted)
  slot 16-23: 0
  slot 24 ($066F HeartValues):     hearts byte — see encode below
  slot 25 ($0670 HeartPartial):    0xFF (always, fills initial heart fully)
  slot 26 ($0671 InvTriforce):     8-bit triforce-piece bitmask
  slot 27-28: 0
  slot 29 ($0674 InvBoomerang):    wood boomerang (1 if granted)
  slot 30 ($0675 InvMagicBoomerang): magical boomerang (1 if granted)
  slot 31 ($0676 InvMagicShield):  magical shield (1 if granted)
  slot 32-36: 0
  slot 37 ($067C MaxBombs):        8 (always; vanilla bomb capacity)
  slot 38-39: 0

Heart encoding for slot 24:
  slot24 = ((hearts - 1) << 4) | min(hearts - 1, 2)
    1 heart  → 0x00     2 hearts → 0x11     3 hearts → 0x22 (vanilla)
    6 hearts → 0x52     8 hearts → 0x72     16 hearts → 0xF2
  Confirmed against reference ROMs at 1/3/6/8/16 hearts.

Slot mapping confirmed byte-for-byte against reference-randomizer ROMs in
analysis/roms/ (single-item seeds for recorder, wand, bombs, wood boomerang,
magical shield; 6-hearts/3-triforce seed for hearts and triforce mask).
"""

from __future__ import annotations

from zora.data_model import Item
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch


# File offsets (zora convention: includes 16-byte iNES header).
HOOK_NEW_SAVE_OFFSET    = 0x9F4E   # JMP $A830 (3 bytes)
ASM_STUB_NEW_SAVE       = 0xA840   # 13 bytes
INVENTORY_TABLE_OFFSET  = 0xA850   # 40 bytes
ASM_STUB_LOAD_SAVE      = 0xA880   # 14 bytes
HOOK_LOAD_SAVE_OFFSET   = 0xAF8B   # JMP $A870 (3 bytes)

# Vanilla bytes we replace, used as RomEdit.old_bytes for round-trip safety.
_VANILLA_HOOK_NEW_SAVE  = bytes.fromhex("A018A9")          # LDY #$18 / LDA #...
_VANILLA_ASM_STUB_NEW   = bytes([0xFF] * 13)               # padding
_VANILLA_INVENTORY      = bytes([0xFF] * 40)               # padding
_VANILLA_ASM_STUB_LOAD  = bytes([0xFF] * 14)               # padding
_VANILLA_HOOK_LOAD_SAVE = bytes.fromhex("A9228D")          # LDA #$22 / STA ...

# The two ASM stubs are constants — their bytes don't depend on user flags.
# Stub #1 lives at file 0xA840 (CPU $A830). It runs from the JMP hook at
# $9F4E (CPU $9F3E) on a fresh save. It copies bytes $A840..$A867 (CPU; 40
# bytes starting at file 0xA850) into the ($C0),Y save buffer that the
# original save-init routine had set up, then JMPs back to $9F4F (CPU)
# which is file 0x9F4F (the byte after the 3-byte JMP we installed).
ASM_STUB_NEW_SAVE_BYTES = bytes.fromhex(
    "A0 27"          # LDY #$27   ; index 39 (count down)
    "B9 40 A8"       # LDA $A840,Y; load from inventory table at CPU $A840
    "91 C0"          # STA ($C0),Y; store to save buffer
    "88"             # DEY
    "10 F8"          # BPL -8     ; loop until Y rolls negative
    "4C 4F 9F"       # JMP $9F4F  ; resume after the 3-byte hook
    .replace(" ", "")
)
assert len(ASM_STUB_NEW_SAVE_BYTES) == 13

# Stub #2 lives at file 0xA880 (CPU $A870). It runs from the JMP hook at
# $AF8B (CPU $AF7B) when an existing save is loaded. Same loop, but stores
# to $0657,Y (the in-RAM live save buffer) and returns via JMP $AF88.
ASM_STUB_LOAD_SAVE_BYTES = bytes.fromhex(
    "A0 27"
    "B9 40 A8"
    "99 57 06"       # STA $0657,Y; store to in-RAM save buffer
    "88"
    "10 F7"
    "4C 88 AF"       # JMP $AF88
    .replace(" ", "")
)
assert len(ASM_STUB_LOAD_SAVE_BYTES) == 14

# JMP-hook bytes. JMP absolute is opcode 0x4C followed by little-endian addr.
HOOK_NEW_SAVE_BYTES  = bytes.fromhex("4C30A8")  # JMP $A830
HOOK_LOAD_SAVE_BYTES = bytes.fromhex("4C70A8")  # JMP $A870


# Mapping from start-item Item enum value → table slot index.
# Slots not in this map are zero-filled (or set by hearts/triforce/bomb logic).
_ITEM_TO_SLOT: dict[Item, int] = {
    # slot 0: sword tier — special-cased below (one byte holds the highest tier)
    Item.WOOD_SWORD:         0,
    Item.WHITE_SWORD:        0,
    Item.MAGICAL_SWORD:      0,
    # slot 1: current bomb count — special-cased (set to 8 if bombs granted)
    # slot 2: arrow tier
    Item.WOOD_ARROWS:        2,
    Item.SILVER_ARROWS:      2,
    Item.BOW:                3,
    # slot 4: candle tier
    Item.BLUE_CANDLE:        4,
    Item.RED_CANDLE:         4,
    Item.RECORDER:           5,
    Item.BAIT:               6,
    Item.WAND:               8,
    Item.RAFT:               9,
    Item.BOOK:               10,
    # slot 11: ring tier
    Item.BLUE_RING:          11,
    Item.RED_RING:           11,
    Item.LADDER:             12,
    Item.MAGICAL_KEY:        13,
    Item.POWER_BRACELET:     14,
    Item.LETTER:             15,
    Item.WOOD_BOOMERANG:     29,
    Item.MAGICAL_BOOMERANG:  30,
    Item.MAGICAL_SHIELD:     31,
}

# Tier values for items that share a slot. Highest tier wins (the generator
# already de-dups upgrade groups, but be defensive in case the same Item
# appears twice in the items list).
_TIER_VALUE: dict[Item, int] = {
    Item.WOOD_SWORD:        1,
    Item.WHITE_SWORD:       2,
    Item.MAGICAL_SWORD:     3,
    Item.WOOD_ARROWS:       1,
    Item.SILVER_ARROWS:     2,
    Item.BLUE_CANDLE:       1,
    Item.RED_CANDLE:        2,
    Item.BLUE_RING:         1,
    Item.RED_RING:          2,
}


def _encode_hearts(hearts: int) -> int:
    """Encode hearts/containers as the byte stored at save offset $066F.

    high nibble = hearts - 1 (= containers - 1, since we set them equal)
    low nibble  = min(hearts - 1, 2) = initial filled-hearts indicator
    Confirmed against reference ROMs for hearts ∈ {1, 3, 6, 8, 16}.
    """
    h = max(1, min(16, hearts))
    return ((h - 1) << 4) | min(h - 1, 2)


def _build_inventory_table(config: GameConfig) -> bytes:
    table = bytearray(40)
    start = config.start_items

    for item in start.items:
        slot = _ITEM_TO_SLOT.get(item)
        if slot is None:
            # MAGICAL_SHIELD has no logical-pool entry but is in the start map;
            # any other item that's not in the map is silently skipped.
            continue
        if item in _TIER_VALUE:
            table[slot] = max(table[slot], _TIER_VALUE[item])
        else:
            table[slot] = 1

    if start.bombs_granted:
        table[1] = 8                      # InvBombs (current bomb count)

    table[24] = _encode_hearts(start.start_hearts)
    table[25] = 0xFF                       # HeartPartial — full first heart
    table[26] = start.triforce_mask & 0xFF # InvTriforce bitmask
    table[37] = 8                          # MaxBombs (vanilla capacity)

    return bytes(table)


class StartItemsPatch(VariableBehaviorPatch):
    """Always-on ROM patch that installs the Start Items hooks and table."""

    def is_active(self, config: GameConfig) -> bool:
        # Always emit. The JMP hooks redirect the vanilla save-init code
        # unconditionally; if we don't write the table, a fresh save would
        # get all-zero inventory (0 hearts → instant death). Emitting the
        # default-vanilla table on every seed is the safe behavior.
        return True

    def get_edits_for_config(
        self,
        config: GameConfig,
        rom_version: int | None = None,
    ) -> list[RomEdit]:
        table = _build_inventory_table(config)
        return [
            RomEdit(
                offset=HOOK_NEW_SAVE_OFFSET,
                new_bytes=HOOK_NEW_SAVE_BYTES,
                old_bytes=_VANILLA_HOOK_NEW_SAVE,
                comment="JMP $A830 — redirect new-save init to start-items stub",
            ),
            RomEdit(
                offset=ASM_STUB_NEW_SAVE,
                new_bytes=ASM_STUB_NEW_SAVE_BYTES,
                old_bytes=_VANILLA_ASM_STUB_NEW,
                comment="ASM stub: copy inventory table into ($C0) save buffer",
            ),
            RomEdit(
                offset=INVENTORY_TABLE_OFFSET,
                new_bytes=table,
                old_bytes=_VANILLA_INVENTORY,
                comment="Inventory table (40 bytes, slot map in patch docstring)",
            ),
            RomEdit(
                offset=ASM_STUB_LOAD_SAVE,
                new_bytes=ASM_STUB_LOAD_SAVE_BYTES,
                old_bytes=_VANILLA_ASM_STUB_LOAD,
                comment="ASM stub: copy inventory table into $0657 in-RAM save buffer",
            ),
            RomEdit(
                offset=HOOK_LOAD_SAVE_OFFSET,
                new_bytes=HOOK_LOAD_SAVE_BYTES,
                old_bytes=_VANILLA_HOOK_LOAD_SAVE,
                comment="JMP $A870 — redirect save-load init to start-items stub",
            ),
        ]

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        # Representative variant: vanilla defaults (no items, 3 hearts, 0 triforce).
        # Used only by the patch-collision test in tests/test_behavior_patches.py.
        from zora.start_item_generator import StartItemResult

        cfg = GameConfig(start_items=StartItemResult())
        return self.get_edits_for_config(cfg)
