"""The owner's 2.0 flag patches (docs/design/zora-flags-2.0.md), written for the flags a seed's
resolved ZORA string turns on.

flags2_patch_data.py is a verbatim copy of asm/flags2/flags2_data.py, the output of
asm/flags2/build.py (C2's patches; tests/test_owner_patches.py keeps them equal). Each patch
stands alone on top of ZORA's code patches, and no two write the same byte (asm/flags2's tests).
They are written after the code patches and before the level encoding and the seed's code.

All Swords No Boards' patches (docs/design/asnb.md section 3) come the same way from asm/asnb/
(asnb_patch_data.py, a verbatim copy of asm/asnb/asnb_data.py; tests/test_asnb_wired.py keeps
them equal): take-l4, sword-cap, which patches over fp-prog-01's and fp-prog-02's
ResolveProgressive copies, and l4-sword-look (level 4 looks like the magical sword in the white
sword's colors; docs/design/l4-sword.md Q2), with Add L4 Sword on (Level 2 or Level 9), and
level-9-gate with Level 9 Entrance = Level 4 sword. take-l4 retires l4-sword-take (3a): it gives
level 4 on every pickup path, so l4-sword-take's bytes and hook are no longer written.
Credits (docs/credits.md): Speed Up Heart Fill by snarfblam, Recorder Kills Dungeon Pols Voice by
Stratoform, Like-Like Eats Rupees by gzip, Start With Full Health by ShadowOne333, kalita-kun and gzip
(the Zelda Hack Pack).
"""
from __future__ import annotations

from collections.abc import Iterable

from .asnb_patch_data import PATCHES as ASNB_PATCHES
from .asnb_patch_data import SYMBOLS as ASNB_SYMBOLS
from .base_rom import piece_bytes
from .flags2_patch_data import CREDITS, PATCHES

# Each version-3 and version-7 ZORA flag (zora_flags.PATCHED_OWNER_FIELDS) and the patches it writes. Shuffle Blue
# Potion writes none of its own (fp-prog-01's buy-once rule, code_patches); Add L4 Sword writes the
# beam damage test (docs/design/l4-sword.md R17) and ASNB's take-l4, sword-cap and l4-sword-look (below).
PATCHES_BY_FLAG: dict[str, tuple[str, ...]] = {
    "shuffle_blue_potion": (),
    "add_l4_sword": ("l4-sword-beam",),
    "extra_raft_blocks": ("raft-blocks",),
    "extra_power_bracelet_blocks": ("bracelet-blocks",),
    "speed_up_dungeon_transitions": ("fast-dungeon-scroll",),
    "speed_up_heart_fill": ("fast-heart-fill",),
    "recorder_kills_pols_voice": ("recorder-pols-voice",),
    "four_potion_inventory": ("four-potions",),
    "like_like_eats_rupees": ("like-like-rupees",),
    "magical_boomerang_damage": ("magic-boomerang-damage",),
    "randomize_lost_hills": ("lost-hills",),
    "randomize_dead_woods": ("dead-woods",),
    # Version 7 (zora_flags.PEGASUS_BOOTS_FIELDS): the boomerangs become L1 and L2 Pegasus Boots.
    "pegasus_boots": ("pegasus-boots",),
    # Version 13 (zora_flags.FULL_HEALTH_FIELDS): loading a save and continuing after death fill every heart.
    "full_health": ("full-health",),
}
# asm/flags2's patches every ROM gets, whatever the flags: auto-show-letter, Auto Show Letter's, a flag
# up to 2.0 beta 6 (owner, 2026-10-17; zora_flags.RETIRED_FIELDS).
ALWAYS_WRITTEN = ("auto-show-letter",)
# asm/flags2's patches no flag writes any more: l4-sword-take, which take-l4 replaces (asnb.md 3a).
RETIRED_PATCHES = frozenset({"l4-sword-take"})
# asm/flags2's patches only an Archipelago game's ROM gets (GameConfig.archipelago_rom): ring-color, the
# tunic repainted for a ring the client gives through RAM (the beta 5 fixes spec, item 1).
ARCHIPELAGO_PATCHES = ("ring-color",)
# asm/flags2's patches a setting with levels writes, not a flag that is on or off: Harder Ganon's
# (zora/rom/harder_bosses.py sets its level byte).
LEVEL_PATCHES = ("harder-ganon",)
# Every built patch belongs to a flag or is retired; a flag's patch not built yet keeps that flag
# unproduced (zora_flags.PRODUCED_OWNER_FIELDS; tests/test_owner_flags_wired.py).
assert set(PATCHES) <= {name for names in PATCHES_BY_FLAG.values() for name in names} | RETIRED_PATCHES \
    | set(ALWAYS_WRITTEN) | set(ARCHIPELAGO_PATCHES) | set(LEVEL_PATCHES)
PATCH_CREDITS = CREDITS

# ASNB's patches by the setting that writes them: Add L4 Sword on (either place), and GameConfig's
# level_9_entrance_sword (LEVEL_9_ENTRANCE, not a version-3 flag).
LEVEL_9_ENTRANCE = "level_9_entrance_sword"
ASNB_PATCHES_BY_FLAG: dict[str, tuple[str, ...]] = {
    "add_l4_sword": ("take-l4", "sword-cap", "l4-sword-look"),
    LEVEL_9_ENTRANCE: ("level-9-gate",),
}
assert set(ASNB_PATCHES) == {name for names in ASNB_PATCHES_BY_FLAG.values() for name in names}
# sword-cap's switch, the operand of a CMP # in each ResolveProgressive copy (ASNB_SYMBOLS): $01 makes
# the sword line top out at level 4 (asm/asnb/README.md "sword-cap").
SWORD_LINE_TO_L4 = 0x01


def owner_patch_writes(flags: Iterable[str], level_9_entrance_sword: bool = False,
                       archipelago_rom: bool = False) -> list[tuple[int, bytes]]:
    """The writes of ALWAYS_WRITTEN's patches and of every patch the named (resolved-on) flags turn
    on, with Level 9 Entrance = Level 4 sword level-9-gate, and in an Archipelago game's ROM
    ARCHIPELAGO_PATCHES, as (file offset, bytes); sword-cap with its switch on."""
    always = (*ALWAYS_WRITTEN, *(ARCHIPELAGO_PATCHES if archipelago_rom else ()))
    writes: list[tuple[int, bytes]] = [(offset, piece_bytes(piece)) for name in always
                                       for offset, piece in PATCHES[name]]
    flags = (*flags, *((LEVEL_9_ENTRANCE,) if level_9_entrance_sword else ()))
    for flag in flags:
        for name in PATCHES_BY_FLAG.get(flag, ()):
            writes.extend((offset, piece_bytes(piece)) for offset, piece in PATCHES[name])
        for name in ASNB_PATCHES_BY_FLAG.get(flag, ()):
            writes.extend((offset, with_sword_line_to_l4(offset, piece_bytes(piece)))
                          for offset, piece in ASNB_PATCHES[name])
    return writes


def archipelago_patch_writes() -> list[tuple[int, bytes]]:
    """ARCHIPELAGO_PATCHES' writes, as (file offset, bytes): what an Archipelago game's ROM adds."""
    return [(offset, piece_bytes(piece)) for name in ARCHIPELAGO_PATCHES for offset, piece in PATCHES[name]]


def with_sword_line_to_l4(offset: int, data: bytes) -> bytes:
    """A piece written at `offset` with sword-cap's switch on wherever it holds one of the
    per-seed operands (ASNB_SYMBOLS), so that no byte is written twice."""
    patched = bytearray(data)
    for operand in ASNB_SYMBOLS.values():
        if offset <= operand < offset + len(data):
            patched[operand - offset] = SWORD_LINE_TO_L4
    return bytes(patched)
