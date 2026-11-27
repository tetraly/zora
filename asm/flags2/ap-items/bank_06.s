.SEGMENT "ZORA_F2_AP_ITEMS_FAR"

; Per-seed data, first in the segment (zora/rom/level_items.py writes it at SEED_DATA): the number the status
; bar shows for each data level 1-9, and the font's digits 1-9 as one bit plane, 8 bytes each, copied from
; the player's ROM so a custom font carries over.
ApItemsShownLevels:
    .BYTE 1, 2, 3, 4, 5, 6, 7, 8, 9
ApItemsDigitGlyphs:
    .RES 9 * 8, $00

; The far side of the item codes $24-$3E, and in per-level mode of the generic compass, map and Triforce
; piece ($16, $17, $1B) (docs/design/archipelago-items.md section 6), reached through StubDraw and StubTake
; in the fixed bank with this bank mapped. One row per code from $16: what it shows (an item slot's picture,
; or the Archipelago logo in a palette row: LOGO_ROW + the row), the inventory byte and bits it sets, and a
; map's data level. NO_ROW draws or takes nothing.
AP_ITEMS_FIRST_FAR = $16
AP_ITEMS_NO_ROW = $FF
AP_ITEMS_LOGO_ROW = $80
AP_ITEMS_PALETTE_ROW_BITS = $03
AP_ITEMS_COMPASS_SLOT = $10             ; InvCompass, Items+$10: levels 1-8, a bit each
AP_ITEMS_MAP_SLOT = $11                 ; InvMap
AP_ITEMS_COMPASS_9_SLOT = $12           ; InvCompass9
AP_ITEMS_MAP_9_SLOT = $13               ; InvMap9
AP_ITEMS_TRIFORCE_SLOT = $1A            ; InvTriforce
AP_ITEMS_LEVEL_BITS = $07                ; a level's bit in its inventory byte
AP_ITEMS_FILLING = $01                  ; World_IsFillingHearts and Paused as a potion sets them
AP_ITEMS_HALTED = $02
AP_ITEMS_MAP_SIGNAL = $01               ; StatusBarMapTrigger: the main loop draws the level's map
AP_ITEMS_BOMB_UPGRADE = $37             ; the Bomb Upgrade (piece 8): MaxBombs and the bombs rise
AP_ITEMS_BOMB_SLOT = $01                ; InvBombs, Items+$01: the bomb's picture
; The digit (docs/design/archipelago-items.md section 6, DigitTile): an 8x16 sprite whose odd tile draws the
; background pair (tile - 1, tile). Pairs $54/$55, $56/$57, $58/$59 are blank in PRG0 and PRG1 and loaded
; in every mode; a digit's glyph is written into a pair's first tile by the frame update itself
; (TransferTileBufAndDigit, after the game's own transfer), never through the dynamic transfer buffer, which
; the cave text rewrites from its start every frame. The second tile stays blank. The cache ($0370-$0376,
; zeroed by ClearRam and at every room entry, so never older than the tiles it describes) says which digit
; each pair holds, the frame it was last drawn, and the pair (plus one) whose glyph waits for the next frame
; update: one at a time.
AP_ITEMS_DIGIT_PAIRS = 3
AP_ITEMS_FIRST_DIGIT_TILE = $55
AP_ITEMS_DIGIT_PPU_HIGH = $15           ; tile $54 of the background pattern table at $1000: $1540
AP_ITEMS_DIGIT_PPU_LOW = $40
AP_ITEMS_PAIR_PPU_SHIFT = 5             ; a pair is 32 bytes
AP_ITEMS_GLYPH_BYTES = 8
AP_ITEMS_TILE_BYTES = 16
AP_ITEMS_RECORD_BYTES = 4               ; a sprite record: Y, tile, attributes, X
AP_ITEMS_NO_DIGIT = $FF
AP_ITEMS_PPU_INCREMENT_32 = $04         ; PPUCTRL's VRAM increment bit
AP_ITEMS_SHOWING = $18                  ; PPUMASK: the background or the sprites shown
AP_ITEMS_DIGIT_ATTRIBUTES = $01         ; palette row 1, in front, unflipped
AP_ITEMS_RECORD_COUNT = $3F             ; a transfer record's count bits (0 is 64)
AP_ITEMS_FULL_RECORD = $40
AP_ITEMS_RECORD_REPEAT = $40            ; a transfer record's flag: one tile, repeated
AP_ITEMS_RECORD_HEADER = 3              ; a record's address and count bytes
AP_ITEMS_RECORD_COST = 5                ; a record's address and setup, in bytes' time
AP_ITEMS_GLYPH_BUDGET = 24              ; the longest dynamic buffer a glyph is written with (ShortDynamicBuffer)
AP_ITEMS_HALF = 8                       ; the digit's top at the item's lower half
AP_ITEMS_NARROW = 12                    ; right of the compass and map (drawn 4 pixels in, 8 wide)
AP_ITEMS_WIDE = 8                       ; over the Triforce piece's lower right corner (16 wide)
DigitPairDigit := $0370
DigitPairDrawn := $0373
DigitPending := $0376
; The logo (zora/rom/archipelago_logo.py): an odd 8x16 tile draws the background table's pair (tile - 1,
; tile), so $5D is the left half ($5C/$5D) and $5F the right ($5E/$5F), 8 pixels apart, unflipped.
AP_ITEMS_LOGO_LEFT = $5D
AP_ITEMS_LOGO_RIGHT = $5F
AP_ITEMS_LOGO_HALVES_APART = 8
AP_ITEMS_LOGO_SECOND_HALF = 1           ; [07]: one more side after the first
AP_ITEMS_ITEM_SPRITE_CYCLER = $0F       ; the sprite cycler DrawItemBySlot passes in X

; Params:
; X: item ID, a far code
; [00], [01]: the sprite position
FarDraw:
    LDA ExtendedDrawSlots-AP_ITEMS_FIRST_FAR, X
    CMP #AP_ITEMS_NO_ROW
    BEQ @Exit
    CMP #AP_ITEMS_LOGO_ROW
    BCC :+
    JMP DrawLogo
:
    LDY ExtendedLevels-AP_ITEMS_FIRST_FAR, X
    CPY #AP_ITEMS_NO_ROW
    BNE @WithDigit
    ; A slot's picture alone (the Bomb Upgrade's bomb): no level, no digit.
    TAX
    TAY
    LDA #$00                    ; Value 0: the slot's own palette.
    STA $04
    JMP DrawItemBySlot

@WithDigit:
    ; The digit, then the item; then the digit's sprite record trades places with any of the item's that
    ; come before it, so it always shows over the item's corner (the sprite cycling reorders them each frame).
    PHA                         ; the slot
    LDY ExtendedLevels-AP_ITEMS_FIRST_FAR, X
    LDX #AP_ITEMS_NARROW
    CMP #AP_ITEMS_TRIFORCE_SLOT
    BNE :+
    LDX #AP_ITEMS_WIDE
:
    STX $02                     ; how far right of the item's position the digit goes
    LDA $00
    PHA
    LDA $01
    PHA
    LDA RollingSpriteIndex      ; the digit's record will be SpriteOffsets at this index
    PHA
    LDA ApItemsShownLevels-1, Y
    JSR DigitTile
    BCS @NoDigit
    JSR DrawDigit
    JMP @Item

@NoDigit:
    PLA
    LDA #AP_ITEMS_NO_DIGIT
    PHA

@Item:
    TSX
    LDA $0102, X
    STA $01
    LDA $0103, X
    STA $00
    LDA $0104, X                ; the slot
    TAY
    TAX
    LDA #$00                    ; Value 0: the slot's own palette.
    STA $04
    JSR DrawItemBySlot
    PLA
    TAX
    PLA
    PLA
    PLA
    CPX #AP_ITEMS_NO_DIGIT
    BEQ @Exit
    LDA SpriteOffsets, X
    TAX
    LDY LeftSpriteOffset
    JSR DigitBefore
    LDY RightSpriteOffset
    JMP DigitBefore

@Exit:
    RTS

; Params:
; X: the digit's sprite record offset
; Y: one of the item's
;
; Returns:
; X: the digit's record, now the earlier of the two (the records trade places when Y's came first)
DigitBefore:
    STX $02
    CPY $02
    BCS @Keep
    LDA #AP_ITEMS_RECORD_BYTES
    STA $03
@Trade:
    LDA Sprites, X
    PHA
    LDA Sprites, Y
    STA Sprites, X
    PLA
    STA Sprites, Y
    INX
    INY
    DEC $03
    BNE @Trade
    TYA
    SEC
    SBC #AP_ITEMS_RECORD_BYTES
    TAX

@Keep:
    RTS

@Exit:
    RTS

; Params:
; A: the digit's sprite tile
; [00], [01]: the item's position
; [02]: how far right of it the digit goes
DrawDigit:
    STA $04
    LDX RollingSpriteIndex
    LDY SpriteOffsets, X
    LDA $00
    CLC
    ADC $02
    STA Sprites+3, Y
    LDA $04
    STA Sprites+1, Y
    LDA #AP_ITEMS_DIGIT_ATTRIBUTES
    STA $03
    LDA #AP_ITEMS_HALF
    CLC
    ADC $01
    JMP Anim_EndWriteSprite

; Params:
; A: a digit, 1-9
;
; Returns:
; C: clear with A the digit's sprite tile; set if no pair holds it with its glyph written yet. A pair taken now
;    holds it once a frame update has written the glyph (WriteDigitGlyph), which may wait a frame or more:
;    until then the digit is not drawn, so its sprite never shows the pair's old glyph.
DigitTile:
    TAY
    LDX #AP_ITEMS_DIGIT_PAIRS - 1
@Find:
    TYA
    CMP DigitPairDigit, X
    BEQ @Drawn
    DEX
    BPL @Find

    ; Not held: a pair no item has drawn this frame takes it, when no other glyph waits.
    LDA DigitPending
    BNE @NotReady
    LDX #AP_ITEMS_DIGIT_PAIRS - 1
@Free:
    LDA DigitPairDrawn, X
    CMP FrameCounter
    BNE @Take
    DEX
    BPL @Free

@NotReady:
    SEC
    RTS

@Take:
    TYA
    STA DigitPairDigit, X
    INX
    STX DigitPending
    SEC                         ; shown once a frame update has written its glyph
    RTS

@Drawn:
    INX
    CPX DigitPending
    BEQ @NotReady               ; its glyph waits for a frame update with room for it
    DEX
    LDA FrameCounter
    STA DigitPairDrawn, X
    TXA
    ASL
    CLC
    ADC #AP_ITEMS_FIRST_DIGIT_TILE
    RTS

.SEGMENT "ZORA_F2_AP_ITEMS_FAR_GLYPH"

; IsrNmi's JSR TransferCurTileBuf (bank 6 mapped): a waiting digit glyph straight into its pair's first tile,
; 16 bytes, both planes the glyph (color 3), then the game's transfer. The glyph costs about 440 cycles, and
; the vertical blank has little to spare: every other frame the game's own status bar update is a dynamic buffer
; of 6 records, 34 bytes, which ends about 300 cycles before rendering starts (2.0.2's test build, measured in
; Mesen 2). A glyph written first on such a frame pushed the game's transfer past the vertical blank: its last
; bytes and the PPUADDR reset landed in the pre-render line and the first scanlines, which garbled the screen
; and left wrong tiles in the status bar, on a drop or on entering a room with a level item (reported by players
; on 2.0.2's test build). So the glyph is written only when the game sends a short dynamic buffer
; (ShortDynamicBuffer), not a static one (a room's tiles, the status bar's map); else it waits for the next
; frame, and the digit is not drawn until it is written (DigitTile).
;
; And only once the mode is set up (IsUpdatingMode) with the screen on: a mode's setup uploads tiles and, with
; the screen off, writes video memory from its main loop, which moving the video address would disturb. The
; cache is cleared at every room entry, before the mode updates.
TransferTileBufAndDigit:
    JSR WriteDigitGlyph
    JMP TransferCurTileBuf

WriteDigitGlyph:
    LDA TileBufSelector
    BNE @Exit
    LDA IsUpdatingMode
    BEQ @Exit
    LDA CurPpuMask_2001
    AND #AP_ITEMS_SHOWING
    BEQ @Exit
    LDX DigitPending
    BEQ @Exit
    JSR ShortDynamicBuffer
    BCC @Write

@Exit:
    RTS

@Write:
    LDX DigitPending
    DEX
    LDA #$00
    STA DigitPending
    LDA CurPpuControl_2000
    AND #<~AP_ITEMS_PPU_INCREMENT_32
    STA CurPpuControl_2000
    STA PpuControl_2000
    LDA PpuStatus_2002
    LDA #AP_ITEMS_DIGIT_PPU_HIGH
    STA PpuAddr_2006
    TXA
    .REPEAT AP_ITEMS_PAIR_PPU_SHIFT
    ASL
    .ENDREP
    ADC #AP_ITEMS_DIGIT_PPU_LOW             ; carry clear: X < 8
    STA PpuAddr_2006
    LDA DigitPairDigit, X
    ASL
    ASL
    ASL
    TAX                                     ; the glyph, from ApItemsDigitGlyphs-8
    LDY #AP_ITEMS_TILE_BYTES
@Byte:
    LDA ApItemsDigitGlyphs-AP_ITEMS_GLYPH_BYTES, X
    STA PpuData_2007
    INX
    DEY
    CPY #AP_ITEMS_GLYPH_BYTES
    BNE :+
    TXA                                     ; plane 1: the glyph again
    SEC
    SBC #AP_ITEMS_GLYPH_BYTES
    TAX
:
    TYA
    BNE @Byte
    RTS

; Returns:
; C: clear if the dynamic transfer buffer is short enough for a glyph this frame: its cost, each record's count
;    plus AP_ITEMS_RECORD_COST, at most AP_ITEMS_GLYPH_BUDGET (units of about one byte's transfer, 18 cycles;
;    a record's address and setup cost about 5). The game's every-other-frame status bar update (6 records,
;    34 bytes) is refused, a one-record update (a counter, a letter of cave text) taken. Uses [00], which
;    TransferCurTileBuf sets afterwards.
ShortDynamicBuffer:
    LDY #$00
    STY $00
@Record:
    LDA DynTileBuf, Y
    BMI @Short                              ; the end mark
    LDA DynTileBuf+2, Y
    AND #AP_ITEMS_RECORD_COUNT
    BNE :+
    LDA #AP_ITEMS_FULL_RECORD               ; a count of 0 is 64
:
    CLC
    ADC #AP_ITEMS_RECORD_COST
    ADC $00
    CMP #AP_ITEMS_GLYPH_BUDGET + 1
    BCS @Exit                               ; too long: C set
    STA $00
    LDA DynTileBuf+2, Y
    AND #AP_ITEMS_RECORD_REPEAT
    BEQ @Run
    INY                                     ; a repeated tile: address, count, the tile
    INY
    INY
    INY
    BNE @Record
@Run:
    LDA DynTileBuf+2, Y
    AND #AP_ITEMS_RECORD_COUNT              ; not 0: a 64-byte record is over the budget
    CLC
    ADC #AP_ITEMS_RECORD_HEADER
    STA $01
    TYA
    ADC $01
    TAY
    BCC @Record                             ; the buffer is short: no carry

@Short:
    CLC

@Exit:
    RTS

.SEGMENT "ZORA_F2_AP_ITEMS_FAR"

; Params:
; A: LOGO_ROW + the palette row: 2 red (progression), 1 blue (useful), 0 Link's (filler), as
;    DrawItemBySlot colors the three swords
; [00], [01]: the sprite position
;
; The two halves through the game's Anim_WriteSpritePair, from the next pair of sprite records, as
; Anim_WriteItemSprites picks them.
DrawLogo:
    AND #AP_ITEMS_PALETTE_ROW_BITS
    STA $04
    STA $05
    LDX RollingSpriteIndex
    LDA SpriteOffsets+1, X
    STA RightSpriteOffset
    LDA SpriteOffsets, X
    STA LeftSpriteOffset
    LDA #AP_ITEMS_LOGO_RIGHT
    STA $03
    LDA #AP_ITEMS_LOGO_LEFT
    STA $02
    LDA #AP_ITEMS_LOGO_HALVES_APART
    STA $0A
    LDA #AP_ITEMS_LOGO_SECOND_HALF
    STA $07
    LDA #$00
    STA ProcessedNarrowObj
    LDX #AP_ITEMS_ITEM_SPRITE_CYCLER
    STX $08
    JMP Anim_WriteSpritePair

; Params:
; X: item ID, a far code
;
; ORs the row's bits into its inventory byte, wherever the item is taken (the game's own take does nothing
; on the overworld and keys the bit by CurLevel). A Triforce piece refills the hearts as a potion does and
; the level goes on; a map taken in its own level draws the status bar's map, as the game's take does. A Bomb
; Upgrade raises MaxBombs by the seed's count and fills the bombs, as the upgraders do.
FarTake:
    CPX #AP_ITEMS_BOMB_UPGRADE
    BNE :+
    JMP TakeBombUpgrade         ; in the fixed block, with the seed's count
:
    LDY ExtendedTakeOffsets-AP_ITEMS_FIRST_FAR, X
    CPY #AP_ITEMS_NO_ROW
    BEQ @Exit
    LDA ExtendedLevels-AP_ITEMS_FIRST_FAR, X
    PHA
    ; The level's bit: 1 << ((level - 1) & 7), so level 9's is bit 0 of its own byte.
    SEC
    SBC #$01
    AND #AP_ITEMS_LEVEL_BITS
    TAX
    LDA #$00
    SEC
@Shift:
    ROL
    DEX
    BPL @Shift
    ORA Items, Y
    STA Items, Y
    PLA
    CPY #AP_ITEMS_TRIFORCE_SLOT
    BNE @Map
    LDA #AP_ITEMS_HALTED
    STA Paused
    LDA #AP_ITEMS_FILLING
    STA World_IsFillingHearts
    RTS

@Map:
    CPY #AP_ITEMS_MAP_SLOT
    BEQ @OwnLevel
    CPY #AP_ITEMS_MAP_9_SLOT
    BNE @Exit

@OwnLevel:
    CMP CurLevel
    BNE @Exit
    LDA #AP_ITEMS_MAP_SIGNAL
    STA StatusBarMapTrigger

@Exit:
    RTS

; $16-$3E: $16, $17 level 9's compass and map, $1B level 8's piece (far in per-level mode only); $24-$2B
; the compasses of levels 1-8, $2C-$33 their maps, $34-$36 another player's item (progression, useful,
; filler: the logo), $38-$3E the pieces of levels 1-7. Levels are data levels (CurLevel).
ExtendedDrawSlots:
    .BYTE AP_ITEMS_COMPASS_SLOT, AP_ITEMS_MAP_SLOT          ; $16, $17
    .RES $1B - $18, AP_ITEMS_NO_ROW                         ; $18-$1A
    .BYTE AP_ITEMS_TRIFORCE_SLOT                            ; $1B
    .RES $24 - $1C, AP_ITEMS_NO_ROW                         ; $1C-$23
    .RES 8, AP_ITEMS_COMPASS_SLOT                           ; $24-$2B
    .RES 8, AP_ITEMS_MAP_SLOT                               ; $2C-$33
    .BYTE AP_ITEMS_LOGO_ROW + 2                             ; $34
    .BYTE AP_ITEMS_LOGO_ROW + 1                             ; $35
    .BYTE AP_ITEMS_LOGO_ROW + 0                             ; $36
    .BYTE AP_ITEMS_BOMB_SLOT                                ; $37 (the Bomb Upgrade, piece 8; taken apart)
    .RES 7, AP_ITEMS_TRIFORCE_SLOT                          ; $38-$3E
ExtendedTakeOffsets:
    .BYTE AP_ITEMS_COMPASS_9_SLOT, AP_ITEMS_MAP_9_SLOT
    .RES $1B - $18, AP_ITEMS_NO_ROW
    .BYTE AP_ITEMS_TRIFORCE_SLOT
    .RES $24 - $1C, AP_ITEMS_NO_ROW
    .RES 8, AP_ITEMS_COMPASS_SLOT
    .RES 8, AP_ITEMS_MAP_SLOT
    .RES 4, AP_ITEMS_NO_ROW                                 ; $34-$37
    .RES 7, AP_ITEMS_TRIFORCE_SLOT
ExtendedLevels:                                             ; data levels; NO_ROW where none
    .BYTE 9, 9                                              ; $16, $17
    .RES $1B - $18, AP_ITEMS_NO_ROW
    .BYTE 8                                                 ; $1B
    .RES $24 - $1C, AP_ITEMS_NO_ROW
    .REPEAT 8, LEVEL                                        ; $24-$2B
    .BYTE LEVEL + 1
    .ENDREP
    .REPEAT 8, LEVEL                                        ; $2C-$33
    .BYTE LEVEL + 1
    .ENDREP
    .RES 4, AP_ITEMS_NO_ROW                                 ; $34-$37
    .REPEAT 7, LEVEL                                        ; $38-$3E
    .BYTE LEVEL + 1
    .ENDREP
