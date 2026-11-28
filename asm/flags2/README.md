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
| `recorder-pols-voice` | Recorder Kills Dungeon Pols Voice (7), credit Stratoform | 0x11BB2 (4 bytes): the call in UpdatePolsVoice; bank 4 $BA00-$BA17 (0x13A10, 24 bytes): `KillPolsVoiceAfterRecorder` |
| `four-potions` | Four Potion Inventory (8) | 0x6C70 and 0x6C74 (1 byte each) |
| `auto-show-letter` | Auto Show Letter (9; written in every ROM since 2026-10-17, no longer a flag) | 0x4708 (13 bytes) |
| `like-like-rupees` | Like-Like Eats Rupees (10) | 0x11D45 and 0x11D47 (1 byte each); 0x11D4A (1 byte: the capture time's reset, a rupee every 6 frames) |
| `magic-boomerang-damage` | Magical Boomerang Does 1 HP Damage (11) | 0x7478 (30 bytes) |
| `lost-hills` | Randomize Lost Hills (12) | 11 bytes of RoomLayoutsOW: layouts 10-12, 27, 28 (screens $0B, $3C, $0C, $0D, $1C, $1D) |
| `dead-woods` | Randomize Dead Woods (13) | 0x15B08 (1 byte): layout 110 (screen $73) |
| `pegasus-boots` | Pegasus Boots (ZORA string version 7; owner spec 2026-10-17) | bank 5 0x14E48 (57 bytes: `WieldBoomerang`'s body, three hooks: `BootsPressB`, `BootsSpeed`; L1 speed operand 0x14E7A, L2's 0x14E7D) and 0x17376 (4 bytes: `InitLinkSpeed` calls `BootsSpeed`, in z1rr-coop's reserved hook); bank 1 0x06B84 (8 bytes: `ItemSlotToPaletteOffsetsOrValues`, L1 in the red palette), 0x0714F, 0x0717C (8 bytes each: the icon's frame tables) and 0x071CD (2 bytes: narrow tiles from $1C); bank 7 0x1F4F5 (9 bytes: `BoomerangFrameCycle`) and 0x1F716 (3 bytes: Goriya boomerangs keep their palette); data: sprite tiles $1C/$1D at 0x0824F (32 bytes, the boot) and the attract text at 0x09358 and 0x0936F (9 bytes each, BOOTS) |
| `hud-white-text` | no flag: Archipelago games' ROMs only (`GameConfig.archipelago_rom`; owner approval 2026-11-22) | bank 6 0x1A2E9 (3 bytes: `StatusBarStaticsTransferBuf`'s values for attribute bytes $23C5-$23C7, $44 $55 $55 to $40 $50 $50): the status bar's top rows over -LIFE- take palette 0, so the client's HUD messages ($2022) stay white; -LIFE- keeps palette 1 |
| `full-health` | Start With Full Health (ZORA version 13; the Hack Pack's full_health.ips, credit ShadowOne333, kalita-kun and gzip) | 0x0A645 (3 bytes: `UpdateMode1Menu_Sub1`'s `JMP GoToNextMode` becomes `JMP FullHealthAfterLoad`), 0x14B82 (5 bytes: the death menu's `ORA #$02 / STA HeartValues` becomes `JSR FullHealthAfterDeath` + 2 NOPs); bank 2 $B0E0 (0x0B0F0, 27 bytes) and bank 5 $B920 (0x17930, 14 bytes): the two routines |
| `harder-ganon` | Harder Ganon (ZORA version 14; Z1M1's harder_ganon, credit MetalMachine; the level is the byte at bank 4 $BB00, set per seed by `zora/rom/harder_bosses.py`) | 0x12CF9 (3 bytes: Ganon_ScenePhase2's call to Ganon_CheckCollisions becomes `JSR GanonRegenerates`), 0x12F38 (4 bytes: the visible timer after a sword hit becomes `JSR GanonVisibleTime` + NOP), 0x12F43 (5 bytes: the silver-arrow test is preceded by `JSR GanonMayJump`); UpdateStatues: 0x10660, 0x10667 (the room id comes from `GanonRoomId`, which answers $28 in any room holding Ganon), 0x1066A, 0x1066C, 0x10688, 0x10696, 0x106A9, 0x106B6, 0x106BD (the room list, the patterns and their tables moved here, with layout $28 as a third room); bank 4 $BB00 (0x13B10, 191 bytes): `GanonLevel`, the tables and the five routines |
| `compass-chime` | Compass Chime (ZORA version 18; docs/zora-extras.md section 25) | 0x01AE5 (3 bytes: `DriveTune1`'s `LDA Tune1Request` becomes `JSR CheckCompassChime`), 0x1EAF2 (3 bytes: the one `JSR CreateRoomObjects` becomes `JSR CreateRoomObjectsAndChime`); bank 0 $82B0 (0x002C0, 133 bytes): the script and `CheckCompassChime`; bank 5 $BD20 (0x17D30, 137 bytes): `CreateRoomObjectsAndChime` and its checks. Both segments placed by asm/rom_space.py (asm/placements.toml) |
| `wizzrobe-hand` | Wizzrobes Shoot Wallmasters (ZORA version 21; idea: Ultralavos) | 0x07322 (2 bytes: `ObjTypeToDamagePoints` for the Wizzrobe shots $58 and $59 becomes the Wallmaster's $80), 0x1030E (3 bytes: `UpdateMonsterShot`'s `JSR CheckShotLinkCollision` becomes `JSR CheckShotLinkCollisionOrGrab`), 0x1F3D4 (6 bytes: `DrawSwordShotOrMagicShot`'s monster-shot choice becomes `JMP ChooseMonsterShotSprites`); bank 4 $BC00 (0x13C10, 110 bytes): the two routines, placed (asm/placements.toml). The hand's tile is read from the Wallmaster's open frame in `ObjAnimFrameHeap`; the flag turns Shuffle Enemy Groups on, whose deal puts Wizzrobes and Wallmasters in one dungeon group |
| `item-counter` | Item Counter (ZORA version 22; idea: Ultralavos) | 0x0655B (3 bytes: `World_ChangeRupees`' `LDA FrameCounter` / `LSR` becomes `JSR ItemCounterOnSkippedFrames`, which on the frames that skip the status bar text puts the counter's record in the free dynamic buffer); bank 5 $BDC0 (0x17DD0, 154 bytes): the routines (none in the stairs mode), placed (asm/placements.toml). ZORA's Python writes the seed's table at bank 5 $BE60-$BEDF (site `item-counter-table`, clear of lozft's code at $BA40-$BAB9 on a music ROM) and the chest and slash into CommonBackgroundPatterns' blank tiles $52 and $53 (`zora/rom/item_counter.py`; the row $50-$5F holds the tiles every mode needs, docs/deviations.md) |
| `level-compass` | no flag: per-level mode only (Add Triforces or Add Maps/Compasses to the Item Pool, `GameConfig.per_level_shown`; docs/design/archipelago-items.md piece 6) | 0x06A9E (9 bytes) and 0x06AA7 (8 bytes): `UpdatePositionMarker`'s Triforce-marker palette choice, run from the game's battery-RAM copy of bank 1 with bank 5 mapped, maps bank 6, asks `CompassMarkerPalette` and maps bank 5 again (back at RAM $7227); bank 6 $AD80 (0x1AD90, 64 bytes): the seed's `LevelCompassRooms` (written by `zora/rom/level_items.py`) and `CompassMarkerPalette`, placed (asm/placements.toml). The marker blinks until the marked room's item (or its item cellar's) is taken; level 9's always blinks |
| `item-line` | Show Item Pickups (ZORA version 24) | 0x06BFE (19 bytes: TakeItem's lift setup, after its tune requests and fp-fix-04's call, keeps the item's code in $F0 first), 0x0654B (3 bytes: `World_ChangeRupees`' `LDA InvRupees` becomes `JSR ItemLineEnter`), 0x1750A (1 byte: ClearRam clears $00-$F1); bank 6 $B150 (0x1B160, 230 bytes): `ItemLine`, which writes "GOT <item>" in the status bar's top row (PPU $2022) or blanks it, then leaves `World_ChangeRupees` for that frame; bank 5 $BDA9 (0x17DB9, 9 bytes) and bank 6 $BDAE (0x1BDBE, 3 bytes): the hop between them through `SwitchBank`. ZORA's Python writes the names at bank 6 $B240-$B3FF (site `item-line-names`, `zora/rom/item_line.py`) |
| `ring-color` | no flag: Archipelago games' ROMs only (`GameConfig.archipelago_rom`; owner 2026-10-18, the beta 5 fixes spec item 1) | bank 7 0x1EC8A (14 bytes: `BeginUpdateWorld`'s clock check calls bank 5's `RingColorAndClock`); bank 5 $BC80-$BCAC (0x17C90, 45 bytes): `RingColorAndClock`, Link repainted when a ring given through RAM disagrees with his tunic |
| `ap-items` | no flag: Archipelago games' ROMs only (docs/design/archipelago-items.md piece 4) | a room's item is six bits (table F bit 3 is bit 5) and codes $24-$3E are drawn and taken far: 0x17859 (5 bytes: `JSR ReadRoomItem6 / AND #$3F`), 0x17888 (9 bytes: `JSR IsTriforceRoomItem`), 0x1E739 (3 bytes: `JSR SlotOrExtended`), 0x1E741 (4 bytes: `JMP StubDraw`), 0x06C16 (3 bytes: `JSR DescriptorOrExtended`), 0x04B3F and 0x04B96 (4 and 3 bytes: the bomb upgrader's `JSR SellerWare` and `JSR SellerPays`, piece 8's seller mode), 0x1311F and 0x13158 (3 bytes each: bank 4's item object through the fixed bank's wrappers); 0x1FD8F (3 bytes: `InitObject`'s `JMP InitObjectFar`) and 0x1FD92 (190 bytes: the fixed-bank block, 187 used; the generic codes drawn as the game does on the title screen and in the ending); bank 4 $BC80 (0x13C90, 193 bytes): `InitObjectFar` and its table, read from the player's ROM (`[[moved]]`); bank 6 $9D70 (0x19D80, 653 bytes): `FarDraw`, `DrawLogo` (codes $34-$36, another player's item by class), the digits, `FarTake` (and the Bomb Upgrade, $37) and their tables; both placed (asm/placements.toml). In a ROM with it, Compass Chime's room item read is made six-bit (zora/rom/owner_patches.py `with_six_bit_room_items`) |

RoomLayoutsOW is bank 5 $9418, file 0x15428-0x15BB7: 16 column descriptors per layout. A
layout may serve several screens (layout 10 serves $0B and $3C). The maze sequences
(ForestMazeDirs 0x6DA7, MountainMazeDirs 0x6DAB) are per-seed data for the generator.

Free space (docs/rom-map.md has the rows):

| Segment | Bank | Slot | Used |
|---|---|---|---|
| `ZORA_F2_POLS_VOICE` (recorder-pols-voice) | 4 | $BA00-$BA3F, after fp-prog-02's Armos slot and before the overworld Wizzrobe routine ($BF00); was $B500 up to 2.0 beta 1, moved off z1rr-coop's reserved $B46F-$B882 | 24 bytes |
| `ZORA_F2_L4_TAKE_FIXED` (l4-sword-take) | 7 | $FF43-$FF4F, bank 7's last free gap | 10 of 13 bytes |
| `ZORA_F2_L4_TAKE` (l4-sword-take) | 1 | $BFC0-$BFDF, between the ISR copy's code and its vectors | 15 bytes |
| `ZORA_F2_RING_COLOR` (ring-color) | 5 | $BC80-$BCBF, after fp-entr-01-sides' slot | 45 bytes |
| `ZORA_F2_COMPASS_CHIME_B0` (compass-chime) | 0 | $82B0-$834F, placed (asm/placements.toml), after lozft's reserved $8000-$82A0 | 133 bytes |
| `ZORA_F2_COMPASS_CHIME_B5` (compass-chime) | 5 | $BD20-$BDA8, placed (asm/placements.toml) | 137 bytes |
| `ZORA_F2_WIZZROBE_HAND` (wizzrobe-hand) | 4 | $BC00-$BC7F, placed (asm/placements.toml) | 110 bytes |
| `ZORA_F2_ITEM_COUNTER` (item-counter) | 5 | $BDC0-$BE5F, placed (asm/placements.toml) | 159 bytes |
| `ZORA_F2_AP_ITEMS_B4` (ap-items) | 4 | $BC80-$BD5F, placed (asm/placements.toml) | 193 bytes |
| `ZORA_F2_AP_ITEMS_FAR` (ap-items) | 6 | $9D70-$9FFF, placed (asm/placements.toml) | 653 bytes |
| `ZORA_F2_LEVEL_COMPASS` (level-compass) | 6 | $AD80-$ADBF, placed (asm/placements.toml) | 64 bytes |
| `ZORA_F2_ITEM_LINE` (item-line) | 6 | $B150-$B23F, the owner's reservation $B150-$B3FF (the names follow at $B240) | 230 bytes |
| `ZORA_F2_ITEM_LINE_HOP_B5` (item-line) | 5 | $BDA9-$BDB1, after Compass Chime's code | 9 bytes |
| `ZORA_F2_ITEM_LINE_HOP_B6` (item-line) | 6 | $BDAE-$BDB0, where bank 5's hop lands | 3 bytes |

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
