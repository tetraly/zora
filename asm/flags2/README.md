# asm/flags2/: the ZORA 2.0 flag patches

ROM patches for the owner's ZORA 2.0 flags (docs/design/zora-flags-2.0.md), one folder each,
in asm/'s format (asm/README.md) plus data edits for the overworld's screen layouts, which the
pinned disassembly includes as a binary. The version-3 ZORA flags write them
(zora/rom/owner_patches.py, from zora/rom/flags2_patch_data.py, a verbatim copy of
`flags2_data.py`). `build.py` applies each one on its own on top of asm/series.txt and writes
`flags2_data.py`.

| Patch | Flag (document section) | Sites (headered file offsets) |
|---|---|---|
| `l4-sword-beam` | Add L4 Sword (2) | 0x7540 (1 byte): the sword shot's damage test takes level 3 or more |
| `l4-sword-take` | Add L4 Sword (2; docs/design/l4-sword.md) | 0x6BEC (2 bytes): TryTakeItem's room-item call; bank 7 $FF43-$FF4C (0x1FF53, 10 bytes): `TakeRoomItemForL4Sword`; bank 1 $BFC0-$BFCE (0x07FD0, 15 bytes): `RaiseSwordToL4` |
| `raft-blocks` | Extra Raft Blocks (3) | 21 bytes of RoomLayoutsOW: layouts 13, 28-30, 46, 51, 64, 65, 80 (screens $0E, $1D-$1F, $2F, $34, $44, $45, $54) |
| `bracelet-blocks` | Extra Power Bracelet Blocks (4) | 10 bytes of RoomLayoutsOW: layouts 18, 19, 34, 50 (screens $13, $14, $23, $33) |
| `fast-dungeon-scroll` | Speed Up Dungeon Transitions (5) | 0x141F3, 0x1426B, 0x1446B, 0x14478, 0x144AD (2 bytes each) |
| `fast-heart-fill` | Speed Up Heart Fill (6), credit snarfblam | 0x17203 and 0x17208 (1 byte each): World_FillHearts' threshold and step |
| `recorder-pols-voice` | Recorder Kills Dungeon Pols Voice (7), credit Stratoform | 0x11BB2 (4 bytes): the call in UpdatePolsVoice; bank 4 $BA00-$BA13 (0x13A10, 20 bytes): `KillPolsVoiceAfterRecorder` |
| `four-potions` | Four Potion Inventory (8) | 0x6C70 and 0x6C74 (1 byte each) |
| `auto-show-letter` | Auto Show Letter (9) | 0x4708 (13 bytes) |
| `like-like-rupees` | Like-Like Eats Rupees (10) | 0x11D45 and 0x11D47 (1 byte each) |
| `magic-boomerang-damage` | Magical Boomerang Does 1 HP Damage (11) | 0x7478 (30 bytes) |
| `lost-hills` | Randomize Lost Hills (12) | 11 bytes of RoomLayoutsOW: layouts 10-12, 27, 28 (screens $0B, $3C, $0C, $0D, $1C, $1D) |
| `dead-woods` | Randomize Dead Woods (13) | 0x15B08 (1 byte): layout 110 (screen $73) |

RoomLayoutsOW is bank 5 $9418, file 0x15428-0x15BB7: 16 column descriptors per layout. A
layout may serve several screens (layout 10 serves $0B and $3C). The maze sequences
(ForestMazeDirs 0x6DA7, MountainMazeDirs 0x6DAB) are per-seed data for the generator.

Free space (docs/rom-map.md has the rows):

| Segment | Bank | Slot | Used |
|---|---|---|---|
| `ZORA_F2_POLS_VOICE` (recorder-pols-voice) | 4 | $BA00-$BA3F, after fp-prog-02's Armos slot and before the overworld Wizzrobe routine ($BF00); was $B500 up to 2.0 beta 1, moved off z1rr-coop's reserved $B46F-$B882 | 20 bytes |
| `ZORA_F2_L4_TAKE_FIXED` (l4-sword-take) | 7 | $FF43-$FF4F, bank 7's last free gap | 10 of 13 bytes |
| `ZORA_F2_L4_TAKE` (l4-sword-take) | 1 | $BFC0-$BFDF, between the ISR copy's code and its vectors | 15 bytes |

## Commands

```
python3 asm/flags2/build.py build             # rebuild asm/flags2/flags2_data.py
python3 asm/flags2/build.py check             # exit 1 if it is out of date
python3 asm/flags2/build.py edit NAME         # the sources with NAME applied, in temp/asm-flags2/edit/src
python3 asm/flags2/build.py refresh NAME      # check NAME applies; list its hook sites and data edits
python3 asm/flags2/build.py apply IN OUT NAME ...   # write IN with the named patches as OUT
```

Tests: tests/test_flags2_patches.py (the module is current, every replaced byte is PRG0's in
ZORA's output, kept bytes are read from the player's ROM, no byte is written by two patches)
and tests/test_flags2_emulator.py (each patch's effect against ZORA's output as the control).
