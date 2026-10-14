.SEGMENT "ZORA_FP_STATS_SCREEN"

; ZORA FP-STATS-01 (player setting "Statistics screen"): the end-of-game statistics screen, and
; clearing the stats block when a new file is registered.
;
; After the credits, UpdateMode13WinGame_Sub4 draws the triforce and waits for Start; its first
; instruction calls StatsFrame. While the screen is not shown, Start (once the wait is over)
; draws it instead of going on, and every other frame runs the submode as PRG0 does. While it
; is shown, Start leaves the way PRG0's Start does (the save mode, then the second quest). The
; whole screen is drawn in one frame with rendering off.

STATS_BLOCK      = $7F00
StatsMagic       = STATS_BLOCK + $00
TotalSeconds     = STATS_BLOCK + $02
AreaSeconds      = STATS_BLOCK + $06    ; 16 bits each: the overworld, levels 1-9
LevelStamps      = STATS_BLOCK + $1A    ; 16 bits each, levels 1-9; the item stamps follow
Stabs            = STATS_BLOCK + $38
BombsUsed        = STATS_BLOCK + $3A
PrevBombs        = STATS_BLOCK + $3C
StatsScreenState = STATS_BLOCK + $3D    ; 0: not shown (bank 0 clears it outside the win mode)
STATS_SIZE       = $40
STATS_MAGIC      = $A5
SCREEN_SHOWN     = $01

BUTTON_START     = $10
; UpdateMode13WinGame_Sub4's Start path, from its JSR EndGameMode on (save mode, video off, sound
; off, then JMP SwitchProfileToSecondQuest). A label there would end the game's local scopes.
WIN_SUBMODE_START_PATH = $ABA5
VIDEO_ON         = $1E                  ; CurPpuMask_2001: background and sprites, left columns too
PPU_CONTROL_KEEP = $F8                  ; CurPpuControl_2000 without the nametable and increment bits
NMI_ENABLE       = $80
NAME_TABLE_0     = $20
PALETTE_PPU      = $3F
BLACK            = $0F
SPACE            = $24
FIRST_LETTER_TILE = $0A
PERIOD           = $2C

; The status bar's level label record (LevelNumberTransferBuf, which power-on copies to RAM): the
; PPU address, the tile count, the tiles (the level word, maybe a dash, then the number), $FF. The
; screen's level labels take the word from it, so they read as the status bar does whatever level
; word the player chose (FP-LEVEL-01).
LEVEL_RECORD_RAM    = $681C
LEVEL_RECORD_COUNT  = LEVEL_RECORD_RAM + 2
LEVEL_RECORD_TILES  = LEVEL_RECORD_RAM + 3
; The loaded level information's palette record (PPU address, count, 32 colors): its sprite rows,
; so the items keep their play-time colors.
SPRITE_PALETTES     = LevelInfo_PalettesTransferBuf + 3 + 16

LEVELS              = 9
CANDIDATES          = LEVELS + 6        ; levels 1-9, then the six key items (bank 0's order)
LIST_ROWS           = 16                ; the overworld and up to 15 candidates
LABEL_LENGTH        = 9
TIME_LENGTH         = 7                 ; H.MM.SS
NO_CANDIDATE        = $FF
ITEM_IDS            = $24               ; a code icon is an item ID below this
; CODE_ICON_COUNT, ITEM_DESCRIPTOR_VALUE_MASK and ITEM_DESCRIPTOR_VALUE_FF are fp-hash-01's (this file).
SWORD_SLOT          = $00
MAX_SWORD_VALUE     = $03
POTION_SLOT         = $07
LETTER_SLOT         = $0F
MAGIC_BOOMERANG_SLOT = $1E
WOOD_BOOMERANG_SLOT = $1D

; Zero page within the frame (every mode uses $00-$0F as scratch; nothing survives the frame).
LastStamp    = $00                      ; 16 bits: the last listed candidate's stamp
LastIndex    = $02                      ; its index, or NO_CANDIDATE
RowsWritten  = $03
BestStamp    = $04                      ; 16 bits
BestIndex    = $06
CandidateIx  = $07
Number       = $08                      ; 16 bits, being formatted
DigitShown   = $0A
Stamp        = $0C                      ; 16 bits: the candidate's stamp
RowIndex     = $0E

; --- entry ------------------------------------------------------------------------------------

StatsFrame:
    LDA StatsScreenState
    BNE @Shown
    LDA ObjTimer
    BNE @AsPrg0
    LDA ButtonsPressed
    AND #BUTTON_START
    BEQ @AsPrg0
    JSR DrawStatsScreen
    LDA #SCREEN_SHOWN
    STA StatsScreenState
    PLA                             ; return past the rest of the submode
    PLA
    RTS

@AsPrg0:
    JMP HideAllSprites

@Shown:
    PLA                             ; the submode does not run while the screen is shown
    PLA
    LDA ButtonsPressed
    AND #BUTTON_START
    BEQ @Wait
    ; PRG0's own Start path in the submode: the save mode, then the second quest.
    LDA #$00
    STA StatsScreenState
    JMP WIN_SUBMODE_START_PATH

@Wait:
    RTS

; The register path's @FlagBReady, reached for each new file: clear the stats block, then the two
; instructions the call replaced (FileBReadyToSave = 1; A stays 1 for the store after the return).
; Keeps X (the slot).
ClearStatsOnRegister:
    LDA #$00
    LDY #STATS_SIZE - 1
:
    STA STATS_BLOCK, Y
    DEY
    BPL :-
    LDA #STATS_MAGIC
    STA StatsMagic
    LDA InvBombs
    STA PrevBombs
    LDA #$01
    STA $0426                       ; FileBReadyToSave
    RTS

; --- drawing ------------------------------------------------------------------------------------

DrawStatsScreen:
    JSR TurnOffAllVideo             ; rendering stops now, so the PPU may be written this frame
    JSR HideAllSprites
    LDA #$00
    STA CurVScroll
    STA CurHScroll
    STA SwitchNameTablesReq
    STA TileBufSelector
    LDA #$FF                        ; nothing for the NMI to transfer
    STA DynTileBuf
    LDA CurPpuControl_2000
    AND #PPU_CONTROL_KEEP
    STA CurPpuControl_2000
    AND #<~NMI_ENABLE
    STA PpuControl_2000
    JSR WritePalettes
    JSR WriteNameTable
    JSR DrawStatsSprites
    LDA #VIDEO_ON
    STA CurPpuMask_2001
    RTS

SetPpuAddress:
    LDX PpuStatus_2002
    STA PpuAddr_2006
    STY PpuAddr_2006
    RTS

WritePalettes:
    LDA #PALETTE_PPU
    LDY #$00
    JSR SetPpuAddress
    LDX #$00
:
    LDA StatsBackgroundPalettes, X
    STA PpuData_2007
    INX
    CPX #16
    BNE :-
    LDA #BLACK                      ; $3F10 is $3F00's mirror
    STA PpuData_2007
    LDX #$01
:
    LDA SPRITE_PALETTES, X
    STA PpuData_2007
    INX
    CPX #16
    BNE :-
    RTS

; X blanks.
PutBlanks:
    LDA #SPACE
:
    STA PpuData_2007
    DEX
    BNE :-
    RTS

; Y characters of StatsText from offset X, as tiles.
PutText:
    LDA StatsText, X
    JSR CharacterTile
    STA PpuData_2007
    INX
    DEY
    BNE PutText
    RTS

; The tile of an ASCII character of StatsText: a capital, a digit, the period or a space.
CharacterTile:
    CMP #'A'
    BCC @NotLetter
    SBC #'A' - FIRST_LETTER_TILE    ; carry is set
    RTS
@NotLetter:
    CMP #'0'
    BCC @Punctuation
    SBC #'0'                        ; digits are tiles 0-9; carry is set
    RTS
@Punctuation:
    CMP #'.'
    BNE :+
    LDA #PERIOD
    RTS
:
    LDA #SPACE
    RTS

WriteNameTable:
    LDA #NAME_TABLE_0
    LDY #$00
    JSR SetPpuAddress
    ; Row 1: the file name.
    LDX #32 + 2
    JSR PutBlanks
    LDX CurSaveSlot
    LDA StatsNameOffsets, X
    TAX
    LDY #8
:
    LDA Names, X
    STA PpuData_2007
    INX
    DEY
    BNE :-
    ; Row 3: the headings.
    LDX #22 + 32 + 12
    JSR PutBlanks
    LDX #TextHeadings - StatsText
    LDY #TextHeadingsEnd - TextHeadings
    JSR PutText
    LDX #5 + 2
    JSR PutBlanks
    ; Rows 4-19: the list.
    JSR WriteList
    ; Rows 21-24: the counters, values right-aligned at column 13 (row 20's first two blanks are
    ; written already).
    LDX #30 + 2
    JSR PutBlanks
    LDX CurSaveSlot
    LDA DeathCounts, X
    LDY #$00
    LDX #TextDeaths - StatsText
    JSR PutCounterRow
    LDA HeartValues                 ; heart containers: the high nibble, plus one
    LSR
    LSR
    LSR
    LSR
    CLC
    ADC #$01
    LDY #$00
    LDX #TextHearts - StatsText
    JSR PutCounterRow
    LDA Stabs
    LDY Stabs+1
    LDX #TextStabs - StatsText
    JSR PutCounterRow
    LDA BombsUsed
    LDY BombsUsed+1
    LDX #TextBombs - StatsText
    JSR PutCounterRow
    ; Row 27: PUSH START BUTTON.
    LDX #32 + 32 + 7 - 2            ; the counter rows' last two blanks are written already
    JSR PutBlanks
    LDX #TextPushStart - StatsText
    LDY #TextPushStartEnd - TextPushStart
    JSR PutText
    LDX #8 + 32 + 32
    JSR PutBlanks
    ; The attributes.
    LDX #$00
:
    LDA StatsAttributes, X
    STA PpuData_2007
    INX
    CPX #64
    BNE :-
    RTS

; One counter row from column 2: the label at StatsText+X (6 tiles), a blank, the value (A low,
; Y high) in 5 columns, then blanks to the next row's column 2.
PutCounterRow:
    STA Number
    STY Number+1
    LDY #6
    JSR PutText
    LDX #1
    JSR PutBlanks
    JSR PutCount
    LDX #18 + 2
    JMP PutBlanks

; --- the list -----------------------------------------------------------------------------------

; The overworld, then the levels and key items with a stamp in stamp order (ties by index), then
; the levels entered and not completed in level order, then blank rows: 16 rows.
WriteList:
    LDX #TextOverworld - StatsText
    LDY #LABEL_LENGTH
    JSR PutText
    LDX #1
    JSR PutBlanks
    LDA AreaSeconds
    STA Number
    LDA AreaSeconds+1
    STA Number+1
    JSR PutTime
    LDX #1 + TIME_LENGTH + 5 + 2
    JSR PutBlanks
    LDA #$01
    STA RowsWritten
    LDA #$00
    STA LastStamp
    STA LastStamp+1
    LDA #NO_CANDIDATE
    STA LastIndex

@Select:
    LDA #$FF
    STA BestStamp
    STA BestStamp+1
    STA BestIndex
    LDA #CANDIDATES - 1
    STA CandidateIx
@Candidate:
    LDA CandidateIx
    JSR LoadStamp
    BEQ @NextCandidate              ; no stamp
    ; After the last listed one: (Stamp, index) > (LastStamp, LastIndex)?
    LDA LastStamp
    CMP Stamp
    LDA LastStamp+1
    SBC Stamp+1
    BCC @After                      ; LastStamp < Stamp
    LDA Stamp
    CMP LastStamp
    BNE @NextCandidate              ; LastStamp > Stamp
    LDA Stamp+1
    CMP LastStamp+1
    BNE @NextCandidate
    LDA LastIndex
    CMP #NO_CANDIDATE
    BEQ @After
    CMP CandidateIx
    BCS @NextCandidate              ; same stamp, not a later index
@After:
    ; Before the best so far: (Stamp, index) <= (BestStamp, BestIndex)? Candidates go down, so
    ; with equal stamps the later-visited lower index wins.
    LDA BestStamp
    CMP Stamp
    LDA BestStamp+1
    SBC Stamp+1
    BCC @NextCandidate              ; BestStamp < Stamp
    LDA Stamp
    STA BestStamp
    LDA Stamp+1
    STA BestStamp+1
    LDA CandidateIx
    STA BestIndex
@NextCandidate:
    DEC CandidateIx
    BPL @Candidate
    LDA BestIndex
    CMP #NO_CANDIDATE
    BEQ @Unfinished
    STA LastIndex
    LDA BestStamp
    STA LastStamp
    LDA BestStamp+1
    STA LastStamp+1
    LDA BestIndex
    JSR PutListRow
    JMP @Select

@Unfinished:
    LDA #$00
    STA CandidateIx
@Level:
    LDA CandidateIx
    JSR LoadStamp
    BNE @NextLevel
    LDA CandidateIx
    ASL
    TAX
    LDA AreaSeconds+2, X
    ORA AreaSeconds+3, X
    BEQ @NextLevel
    LDA CandidateIx
    JSR PutListRow
@NextLevel:
    INC CandidateIx
    LDA CandidateIx
    CMP #LEVELS
    BCC @Level

@Fill:
    LDA RowsWritten
    CMP #LIST_ROWS
    BCS @Done
    LDX #32
    JSR PutBlanks
    INC RowsWritten
    BNE @Fill
@Done:
    RTS

; Stamp = the stamp of candidate A (levels 0-8, items 9-14); Z set when it is 0.
LoadStamp:
    ASL
    TAX
    LDA LevelStamps, X
    STA Stamp
    LDA LevelStamps+1, X
    STA Stamp+1
    ORA Stamp
    RTS

; One list row from column 2 to the next row's column 2: the label, a blank, the time in (levels),
; a blank, the completion time.
PutListRow:
    STA RowIndex
    INC RowsWritten
    CMP #LEVELS
    BCS @ItemLabel
    ; The status bar's word and the level's number.
    LDX LEVEL_RECORD_COUNT
    DEX
    BEQ @Number
    LDY #$00
:
    LDA LEVEL_RECORD_TILES, Y
    STA PpuData_2007
    INY
    DEX
    BNE :-
@Number:
    LDA RowIndex
    CLC
    ADC #$01
    STA PpuData_2007
    LDA #LABEL_LENGTH
    SEC
    SBC LEVEL_RECORD_COUNT
    TAX
    BEQ :+
    JSR PutBlanks
:
    LDX #1
    JSR PutBlanks
    LDA RowIndex
    ASL
    TAX
    LDA AreaSeconds+2, X
    STA Number
    LDA AreaSeconds+3, X
    STA Number+1
    JSR PutTime
    JMP @Completion

@ItemLabel:
    SEC
    SBC #LEVELS - 1                 ; the item labels follow OVERWORLD
    TAX
    LDA #$00
:
    DEX
    BMI :+
    CLC
    ADC #LABEL_LENGTH
    BNE :-
:
    CLC
    ADC #TextOverworld - StatsText
    TAX
    LDY #LABEL_LENGTH
    JSR PutText
    LDX #1 + TIME_LENGTH
    JSR PutBlanks

@Completion:
    LDX #1
    JSR PutBlanks
    LDA RowIndex
    JSR LoadStamp
    BNE :+
    LDX #TIME_LENGTH
    JSR PutBlanks
    JMP @End
:
    LDA Stamp
    STA Number
    LDA Stamp+1
    STA Number+1
    JSR PutTime
@End:
    LDX #5 + 2
    JMP PutBlanks

; --- numbers ------------------------------------------------------------------------------------

; Number (seconds) as H.MM.SS; 10 hours or more show 9.59.59.
PutTime:
    LDY #$00
@Hour:
    LDA Number
    CMP #<3600
    LDA Number+1
    SBC #>3600
    BCC @Hours
    STA Number+1
    LDA Number
    SBC #<3600                      ; carry is set
    STA Number
    INY
    BNE @Hour
@Hours:
    CPY #10
    BCC :+
    LDX #TextTimeCap - StatsText
    LDY #TIME_LENGTH
    JMP PutText
:
    STY PpuData_2007
    LDY #$00
@Minute:
    LDA Number
    CMP #60
    LDA Number+1
    SBC #$00
    BCC @Minutes
    STA Number+1
    LDA Number
    SBC #60
    STA Number
    INY
    BNE @Minute
@Minutes:
    TYA
    JSR PutPeriodAndTwoDigits
    LDA Number

PutPeriodAndTwoDigits:
    LDX #PERIOD
    STX PpuData_2007
    LDX #$00
:
    CMP #10
    BCC :+
    SBC #10
    INX
    BNE :-
:
    STX PpuData_2007
    STA PpuData_2007
    RTS

; Number in 5 columns, right-aligned, leading zeros blank.
PutCount:
    LDA #$00
    STA DigitShown
    LDX #$00
@Power:
    LDY #$00
@Subtract:
    LDA Number
    CMP PowersLo, X
    LDA Number+1
    SBC PowersHi, X
    BCC @Digit
    STA Number+1
    LDA Number
    SBC PowersLo, X                 ; carry is set
    STA Number
    INY
    BNE @Subtract
@Digit:
    TYA
    ORA DigitShown
    STA DigitShown
    BNE :+
    LDA #SPACE
    STA PpuData_2007
    JMP @NextPower
:
    STY PpuData_2007
@NextPower:
    INX
    CPX #4
    BCC @Power
    LDA Number                      ; the ones, always shown
    STA PpuData_2007
    RTS

PowersLo:
    .BYTE <10000, <1000, <100, <10
PowersHi:
    .BYTE >10000, >1000, >100, >10

; --- sprites ------------------------------------------------------------------------------------

; The seed's code (when the ROM has one) and the inventory in the item screen's arrangement: the
; passive row above the two rows of B items, the sword beside them. Each item is a pair of the
; rolling sprite indices, 2 per item (20 pairs, at most 19 used).
DrawStatsSprites:
    LDA #$00
    STA RollingSpriteIndex
    JSR DrawCodeIcons
    LDX #STATS_ITEM_COUNT - 1
@Item:
    TXA
    PHA
    LDY StatsItemSlots, X
    LDA Items, Y
    BEQ @Next
    STA $04
    LDA StatsItemXs, X
    STA $00
    LDA StatsItemYs, X
    STA $01
    TYA
    TAX
    JSR DrawStatsItem
@Next:
    PLA
    TAX
    DEX
    BPL @Item
    ; The sword, beside the first row (a level 4 sword is drawn as the magical sword).
    LDA Items
    BEQ @Boomerang
    CMP #MAX_SWORD_VALUE + 1
    BCC :+
    LDA #MAX_SWORD_VALUE
:
    STA $04
    LDA #STATS_SWORD_X
    LDX #SWORD_SLOT
    JSR DrawStatsItemInFirstRow
@Boomerang:
    LDX #MAGIC_BOOMERANG_SLOT
    LDA Items, X
    BNE :+
    LDX #WOOD_BOOMERANG_SLOT
    LDA Items, X
    BEQ @PotionOrLetter
:
    STA $04
    LDA #STATS_BOOMERANG_X
    JSR DrawStatsItemInFirstRow
@PotionOrLetter:
    LDX #POTION_SLOT
    LDA Items, X
    BNE :+
    LDX #LETTER_SLOT
    LDA Items, X
    BEQ @Done
:
    STA $04
    LDA #STATS_POTION_X
    STA $00
    LDA #STATS_SECOND_ROW_Y
    STA $01
    JMP DrawStatsItem
@Done:
    RTS

DrawStatsItemInFirstRow:
    STA $00
    LDA #STATS_FIRST_ROW_Y
    STA $01

; Draw the item in slot X (value in [04]) at ([00], [01]), on the next pair of sprites.
DrawStatsItem:
    TXA
    TAY
    JSR DrawItemBySlot
    INC RollingSpriteIndex
    INC RollingSpriteIndex
    RTS

; As FP-HASH-01 draws them on the file-select screen, if all four bytes are item IDs (a ROM
; without the code holds $FF there).
DrawCodeIcons:
    LDX #CODE_ICON_COUNT - 1
:
    LDA ZORA_B2_CodeIcons, X
    CMP #ITEM_IDS
    BCS @Done
    DEX
    BPL :-
    LDX #CODE_ICON_COUNT - 1
@Icon:
    TXA
    PHA
    LDA StatsCodeIconXs, X
    STA $00
    LDA #STATS_CODE_ICON_Y
    STA $01
    LDY ZORA_B2_CodeIcons, X
    LDA ItemIdToDescriptor, Y
    CMP #ITEM_DESCRIPTOR_VALUE_FF
    BNE :+
    LDA #$FF
:
    AND #ITEM_DESCRIPTOR_VALUE_MASK
    STA $04
    LDA ItemIdToSlot, Y
    TAX
    JSR DrawStatsItem
    PLA
    TAX
    DEX
    BPL @Icon
@Done:
    RTS

; --- data ---------------------------------------------------------------------------------------

; Sprite Y is the row's top pixel minus one.
STATS_CODE_ICON_Y   = 1 * 8 - 1         ; rows 1-2
STATS_PASSIVE_ROW_Y = 21 * 8 - 1        ; rows 21-22
STATS_FIRST_ROW_Y   = 23 * 8 - 1        ; rows 23-24
STATS_SECOND_ROW_Y  = 25 * 8 - 1        ; rows 25-26
STATS_SWORD_X       = $70
STATS_BOOMERANG_X   = $80
STATS_POTION_X      = $B0

StatsCodeIconXs:
    .BYTE $A8, $B8, $C8, $D8

; The other items: their slot and place, the item screen's Xs (SubmenuItemXs).
STATS_ITEM_COUNT = 13
StatsItemSlots:
    .BYTE $0E, $0D, $0C, $0B, $0A, $09  ; bracelet, magic key, ladder, ring, book, raft
    .BYTE $04, $03, $02, $01            ; candle, bow, arrow, bombs
    .BYTE $08, $06, $05                 ; rod, food, recorder
StatsItemXs:
    .BYTE $CC, $C0, $B0, $A0, $94, $80
    .BYTE $C8, $B4, $AC, $98
    .BYTE $C8, $98, $80
StatsItemYs:
    .BYTE STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y
    .BYTE STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y
    .BYTE STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y
    .BYTE STATS_SECOND_ROW_Y, STATS_SECOND_ROW_Y, STATS_SECOND_ROW_Y

; Each save slot's name in Names (8 tiles a slot).
StatsNameOffsets:
    .BYTE 0, 8, 16

; Background palette 0 white text, 1 orange headings; 2 and 3 unused.
StatsBackgroundPalettes:
    .BYTE $0F, $30, $30, $30, $0F, $27, $27, $27, $0F, $30, $30, $30, $0F, $30, $30, $30

; The texts, in ASCII (PutText draws each character's tile, zora/rom/text_encoding.py). The
; labels are 9 characters, space-padded: OVERWORLD, then the key items in bank 0's order, named as
; the hints name them (tests/test_stats_screen.py checks them against
; zora/generate/steps/hint_text.py).
StatsText:
TextOverworld:
    .BYTE "OVERWORLD"
    .BYTE "SWORD    "
    .BYTE "LADDER   "
    .BYTE "BRACELET "
    .BYTE "RAFT     "
    .BYTE "RECORDER "
    .BYTE "S.ARROWS "
TextHeadings:
    .BYTE "TIME IN CLEARED"
TextHeadingsEnd:
TextDeaths:
    .BYTE "DEATHS"
TextHearts:
    .BYTE "HEARTS"
TextStabs:
    .BYTE "STABS "
TextBombs:
    .BYTE "BOMBS "
TextPushStart:
    .BYTE "PUSH START BUTTON"
TextPushStartEnd:
TextTimeCap:
    .BYTE "9.59.59"

; Palette 1 under the headings (row 3, columns 12-27) and the counter labels (rows 21-24,
; columns 2-7); palette 0 elsewhere.
StatsAttributes:
    .BYTE $00, $00, $00, $50, $50, $50, $50, $00
    .RES 4 * 8, $00
    .BYTE $44, $55, $00, $00, $00, $00, $00, $00
    .BYTE $04, $05, $00, $00, $00, $00, $00, $00
    .RES 8, $00
