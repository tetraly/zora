"""The owner's 2.0 flag patches (docs/design/zora-flags-2.0.md), written for the flags a seed's
resolved ZORA string turns on.

flags2_patch_data.py is a verbatim copy of asm/flags2/flags2_data.py, the output of
asm/flags2/build.py (C2's patches; tests/test_owner_patches.py keeps them equal). Each patch
stands alone on top of ZORA's code patches, and no two write the same byte (asm/flags2's tests).
They are written after the code patches and before the level encoding and the seed's code.
Credits (docs/credits.md): Speed Up Heart Fill by snarfblam, Recorder Kills Dungeon Pols Voice by
Stratoform.
"""
from __future__ import annotations

from collections.abc import Iterable

from zora.rom.base_rom import piece_bytes
from zora.rom.flags2_patch_data import CREDITS, PATCHES

# Each version-3 ZORA flag (zora_flags.OWNER_2_0_FIELDS) and the patches it writes. Shuffle Blue
# Potion writes none of its own (fp-prog-01's buy-once rule, code_patches); Add L4 Sword writes the
# beam damage test and the room-item take hook (docs/design/l4-sword.md R17, R20).
PATCHES_BY_FLAG: dict[str, tuple[str, ...]] = {
    "shuffle_blue_potion": (),
    "add_l4_sword": ("l4-sword-beam", "l4-sword-take"),
    "extra_raft_blocks": ("raft-blocks",),
    "extra_power_bracelet_blocks": ("bracelet-blocks",),
    "speed_up_dungeon_transitions": ("fast-dungeon-scroll",),
    "speed_up_heart_fill": ("fast-heart-fill",),
    "recorder_kills_pols_voice": ("recorder-pols-voice",),
    "four_potion_inventory": ("four-potions",),
    "auto_show_letter": ("auto-show-letter",),
    "like_like_eats_rupees": ("like-like-rupees",),
    "magical_boomerang_damage": ("magic-boomerang-damage",),
    "randomize_lost_hills": ("lost-hills",),
    "randomize_dead_woods": ("dead-woods",),
}
# Every built patch belongs to a flag; a flag's patch not built yet keeps that flag unproduced
# (zora_flags.PRODUCED_OWNER_FIELDS; tests/test_owner_flags_wired.py).
assert set(PATCHES) <= {name for names in PATCHES_BY_FLAG.values() for name in names}
PATCH_CREDITS = CREDITS


def owner_patch_writes(flags: Iterable[str]) -> list[tuple[int, bytes]]:
    """The writes of every patch the named (resolved-on) flags turn on, as (file offset, bytes)."""
    writes: list[tuple[int, bytes]] = []
    for flag in flags:
        for name in PATCHES_BY_FLAG[flag]:
            writes.extend((offset, piece_bytes(piece)) for offset, piece in PATCHES[name])
    return writes
