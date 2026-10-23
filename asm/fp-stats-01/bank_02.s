.SEGMENT "ZORA_FP_STATS_SCREEN"

; ZORA FP-STATS-01 (player setting "Statistics screen"): the end-of-game statistics screen, and
; clearing the stats block when a new file is registered.
;
; After the credits, UpdateMode13WinGame_Sub4 draws the triforce and waits for Start; its first
; instruction calls StatsFrame. While the screen is not shown, Start (once the wait is over)
; draws it instead of going on, and every other frame runs the submode as PRG0 does. While it
; is shown, Start leaves the way the submode's Start does (the save mode; FP-SAVE-01 keeps the file). The
; whole screen is drawn in one frame with rendering off. The ending's song keeps playing there with
; music on; with music off (FP-SET-04) it stops (owner decision, 2026-10-19): Tune0 request $80,
; the audio driver's own signal to silence the song only, which leaves the effects and the songs
; the game requests later alone.

STATS_BLOCK      = $7F00
StatsMagic       = STATS_BLOCK + $00
TotalSeconds     = STATS_BLOCK + $02
AreaSeconds      = STATS_BLOCK + $06    ; 16 bits each: the overworld, levels 1-9
LevelStamps      = STATS_BLOCK + $1A    ; 16 bits each, levels 1-9; the item stamps follow
Stabs            = STATS_BLOCK + $3A
BombsUsed        = STATS_BLOCK + $3C
PrevBombs        = STATS_BLOCK + $3E
StatsScreenState = STATS_BLOCK + $3F    ; 0: not shown (bank 0 clears it outside the win mode)
STATS_SIZE       = $40
STATS_MAGIC      = $A5
SCREEN_SHOWN     = $01

BUTTON_START     = $10
; UpdateMode13WinGame_Sub4's Start path, from its JSR EndGameMode on (save mode, video off, sound
; off, then PRG0's JMP SwitchProfileToSecondQuest, which FP-SAVE-01 makes an RTS). A label there
; would end the game's local scopes.
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
SILENCE_SONG     = $80                  ; Tune0Request: DriveTune0 runs SilenceSong
; Music off's mark (asm/settings/music-off/bank_02.s writes SILENCE_SONG here; music on leaves
; the free space's $FF): this patch is built apart from the music choices, so the address is
; named in both.
MUSIC_OFF_MARK   = $B7A0
; The counters' small x: the screen writes its pattern over background tile $70, the first of the
; level's own tiles ($1700-$1F1F), which every level and the overworld load again before they are
; shown (the menus after the ending use only the common tiles).
SMALL_X_TILE     = $70
SMALL_X_PATTERN  = $1000 + SMALL_X_TILE * 16

; The status bar's level label record (LevelNumberTransferBuf, which power-on copies to RAM): the
; PPU address, the tile count, the tiles (the level word, maybe a dash, then the number), $FF. The
; screen's level labels take the word from it, so they read as the status bar does whatever level
; word the player chose (FP-LEVEL-01). With FP-LEVEL-02's 8-tile label (asm/fp-level-02/) the record
; is refilled from its own at each level load, so a long label reads here too.
LEVEL_RECORD_RAM    = $681C
LEVEL_RECORD_COUNT  = LEVEL_RECORD_RAM + 2
LEVEL_RECORD_TILES  = LEVEL_RECORD_RAM + 3
; The loaded level information's palette record (PPU address, count, 32 colors): its sprite rows,
; so the items keep their play-time colors.
SPRITE_PALETTES     = LevelInfo_PalettesTransferBuf + 3 + 16

LEVELS              = 9
CANDIDATES          = LEVELS + 7        ; levels 1-9, then the seven key items (bank 0's order)
LIST_ROWS           = 17                ; the overworld and up to 16 candidates
LABEL_LENGTH        = 9
TIME_LENGTH         = 7                 ; H.MM.SS
; A list row from column 2: the label (columns 2-10), the time in (13-19), the completion time
; (23-29; owner's layout, 2026-10-19), then blanks to the next row's column 2.
TIME_GAP            = 2
CLEARED_GAP         = 3
LIST_ROW_END_BLANKS = 32 - LABEL_LENGTH - TIME_GAP - TIME_LENGTH - CLEARED_GAP - TIME_LENGTH
NO_CANDIDATE        = $FF
SWORD_SLOT          = $00
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
BlanksAfter  = $0F                      ; PutCount: the columns left after the number

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
    LDA MUSIC_OFF_MARK
    CMP #SILENCE_SONG
    BNE :+                          ; music on: the ending's song plays on
    STA Tune0Request
:
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
    ; The submode's own Start path: the save mode (which keeps the file, FP-SAVE-01).
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
    JSR WriteSmallXPattern
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

WriteSmallXPattern:
    LDA #>SMALL_X_PATTERN
    LDY #<SMALL_X_PATTERN
    JSR SetPpuAddress
    LDX #$00
:
    LDA SmallXPattern, X
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
    ; Rows 1-9, the top (owner's layout, 2026-10-19): the seed number (rows 1-2), then on the left
    ; the file name (row 3) and the counters (rows 4-7); on the right the passive items (sprites,
    ; rows 1-2) and the B items in a blue box (rows 3-8, as the item screen draws them); the
    ; headings (row 9).
    LDX #32 + 2
    JSR PutBlanks
    LDA StatsSeedDigits
    CMP #NO_SEED_NUMBER
    BNE @SeedNumber
    LDX #30 + 32 + 2
    JSR PutBlanks
    JMP @Name
@SeedNumber:
    ; Rows 1-2: SEED and the first 10 digits, the rest under them.
    LDX #TextSeed - StatsText
    LDY #TextSeedEnd - TextSeed
    JSR PutText
    LDY #$00
:
    LDA StatsSeedDigits, Y
    STA PpuData_2007
    INY
    CPY #SEED_DIGITS_PER_ROW
    BNE :-
    LDX #32 - SEED_DIGITS_END_COLUMN + SEED_DIGITS_COLUMN
    JSR PutBlanks
:
    LDA StatsSeedDigits, Y
    STA PpuData_2007
    INY
    CPY #2 * SEED_DIGITS_PER_ROW
    BNE :-
    LDX #32 - SEED_DIGITS_END_COLUMN + 2
    JSR PutBlanks
@Name:
    ; Row 3: the file name, and the box's top.
    LDX CurSaveSlot
    LDA StatsNameOffsets, X
    TAX
    LDY #NAME_LENGTH
:
    LDA Names, X
    STA PpuData_2007
    INX
    DEY
    BNE :-
    LDX #BOX_LEFT_COLUMN - 2 - NAME_LENGTH
    JSR PutBlanks
    LDX #BoxTop - BoxTiles
    JSR PutBoxRow
    ; Rows 4-7: the counters, as Z2Randomizer draws its containers: each an icon (a sprite,
    ; DrawCounterIcons) over two columns of two rows, then on the icon's lower row the small x and
    ; the count. Deaths and stabs on row 5, heart containers and bombs on row 7.
    LDX #BOX_LEFT_COLUMN - 2
    JSR PutBlanks
    JSR PutBoxSide
    LDX CurSaveSlot
    LDA DeathCounts, X
    LDY #$00
    LDX #SHORT_COUNT_COLUMNS
    JSR PutCounterCell
    LDA Stabs
    LDY Stabs+1
    LDX #COUNT_COLUMNS
    JSR PutCounterCell
    LDX #BOX_LEFT_COLUMN - COUNTERS_END_COLUMN
    JSR PutBlanks
    JSR PutBoxSide
    LDX #BOX_LEFT_COLUMN - 2
    JSR PutBlanks
    JSR PutBoxSide
    LDA HeartValues                 ; heart containers: the high nibble, plus one
    LSR
    LSR
    LSR
    LSR
    CLC
    ADC #$01
    LDY #$00
    LDX #SHORT_COUNT_COLUMNS
    JSR PutCounterCell
    LDA BombsUsed
    LDY BombsUsed+1
    LDX #COUNT_COLUMNS
    JSR PutCounterCell
    LDX #BOX_LEFT_COLUMN - COUNTERS_END_COLUMN
    JSR PutBlanks
    JSR PutBoxSide
    ; Row 8: the box's bottom.
    LDX #BOX_LEFT_COLUMN - 2
    JSR PutBlanks
    LDX #BoxBottom - BoxTiles
    JSR PutBoxRow
    ; Row 9: the headings, over the time columns.
    LDX #HEADINGS_COLUMN - 2
    JSR PutBlanks
    LDX #TextHeadings - StatsText
    LDY #TextHeadingsEnd - TextHeadings
    JSR PutText
    LDX #32 - HEADINGS_COLUMN - (TextHeadingsEnd - TextHeadings) + 2
    JSR PutBlanks
    ; Rows 10-26: the list.
    JSR WriteList
    ; Row 27: PUSH START BUTTON.
    LDX #7 - 2
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

; A box row from its left column: the left tile, the inside's tiles, the right tile (BoxTiles+X),
; then blanks to the next row's column 2.
PutBoxRow:
    LDA BoxTiles, X
    STA PpuData_2007
    LDA BoxTiles+1, X
    LDY #BOX_INSIDE_COLUMNS
:
    STA PpuData_2007
    DEY
    BNE :-
    LDA BoxTiles+2, X
    STA PpuData_2007
    LDX #32 - BOX_RIGHT_COLUMN - 1 + 2
    JMP PutBlanks

PutBoxSide:
    LDX #BoxSide - BoxTiles
    JMP PutBoxRow

; One counter cell: blanks under the icon, the small x, then the value (A low, Y high) as PutCount
; writes it in X columns (COUNTER_ICON_COLUMNS + 1 + X in all).
PutCounterCell:
    STA Number
    STY Number+1
    DEX
    STX BlanksAfter                 ; the columns after the ones, which are always shown
    LDX #COUNTER_ICON_COLUMNS
    JSR PutBlanks
    LDA #SMALL_X_TILE
    STA PpuData_2007
    JMP PutCount

; --- the list -----------------------------------------------------------------------------------

; The overworld, then the levels and key items with a stamp in stamp order (ties by index), then
; the levels entered and not completed in level order, then blank rows: 17 rows.
WriteList:
    LDX #TextOverworld - StatsText
    LDY #LABEL_LENGTH
    JSR PutText
    LDX #TIME_GAP
    JSR PutBlanks
    LDA AreaSeconds
    STA Number
    LDA AreaSeconds+1
    STA Number+1
    JSR PutTime
    LDX #CLEARED_GAP + TIME_LENGTH + LIST_ROW_END_BLANKS
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

; Stamp = the stamp of candidate A (levels 0-8, items 9-15); Z set when it is 0.
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
    LDX #TIME_GAP
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
    LDX #TIME_GAP + TIME_LENGTH
    JSR PutBlanks

@Completion:
    LDX #CLEARED_GAP
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
    LDX #LIST_ROW_END_BLANKS
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

; Number left-aligned, BlanksAfter + 1 columns, blanks after it; more than 9999 shows 9999.
PutCount:
    LDA Number
    CMP #<(MAX_COUNT + 1)
    LDA Number+1
    SBC #>(MAX_COUNT + 1)
    BCC :+
    LDA #<MAX_COUNT
    STA Number
    LDA #>MAX_COUNT
    STA Number+1
:
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
    BEQ @NextPower                  ; a leading zero: not written
    STY PpuData_2007
    DEC BlanksAfter
@NextPower:
    INX
    CPX #COUNT_COLUMNS - 1
    BCC @Power
    LDA Number                      ; the ones
    STA PpuData_2007
    LDX BlanksAfter
    BEQ :+
    JMP PutBlanks
:
    RTS

MAX_COUNT     = 9999
COUNT_COLUMNS = 4
PowersLo:
    .BYTE <1000, <100, <10
PowersHi:
    .BYTE >1000, >100, >10

; --- sprites ------------------------------------------------------------------------------------

; The counters' icons and the inventory in the item screen's arrangement (the passive row above,
; the two rows of B items in their box). Each item is a pair of the rolling sprite indices, 2 per
; item (the counters' sword and at most 15 items: 16 of SpriteOffsets' 20 pairs); Link, the heart
; container and the counters' bomb are sprites 0-4, below SpriteOffsets' sprites. No scanline has
; more than 8 sprites: the passive row alone (8), the first B row's 5 and the upper counters' 3,
; the second B row's 4 and the lower counters' 3.
DrawStatsSprites:
    LDA #$00
    STA RollingSpriteIndex
    JSR DrawCounterIcons
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
    LDX #MAGIC_BOOMERANG_SLOT
    LDA Items, X
    BNE :+
    LDX #WOOD_BOOMERANG_SLOT
    LDA Items, X
    BEQ @PotionOrLetter
:
    STA $04
    LDA #STATS_BOOMERANG_X
    STA $00
    LDA #STATS_FIRST_ROW_Y
    STA $01
    JSR DrawStatsItem
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

; The counters' icons, over the cells PutCounterCell writes: Link (deaths), a heart container
; (hearts) and a bomb (bombs used) as fixed sprites, and the sword Link holds (stabs; the wooden
; sword without one) as the items are drawn. A level 4 sword (Add L4 Sword) is drawn as level 4:
; DrawItemBySlot then gives it its own look (l4-sword-look, always written with Add L4 Sword: the
; magical sword's icon in the white sword's colors). Drawn as the magical sword, it was red.
DrawCounterIcons:
    LDX #COUNTER_SPRITES_SIZE - 1
:
    LDA CounterSprites, X
    STA Sprites, X
    DEX
    BPL :-
    LDA Items
    BNE :+
    LDA #WOOD_SWORD_VALUE
:
    STA $04
    LDA #COUNTER_RIGHT_X
    STA $00
    LDA #COUNTER_UPPER_Y
    STA $01
    LDX #SWORD_SLOT
    JMP DrawStatsItem

; Draw the item in slot X (value in [04]) at ([00], [01]), on the next pair of sprites.
; DrawItemBySlot's sprite writer (Anim_WriteSpritePair, with object index $0F) itself moves
; RollingSpriteIndex on by one for each sprite it writes, one for a half-width item and two for a
; wide one, and wraps it only when it lands on exactly $28. So the pair is set here before each item
; and the next one counted from it: adding 2 after the call drifted the index by 3 or 4 an item,
; and with the code and a full inventory (20 items) it ran past SpriteOffsets' end, onto offsets
; that are not a sprite's, rewriting earlier sprites' fields (a code icon drawn mid-screen).
DrawStatsItem:
    TXA
    TAY
    LDA RollingSpriteIndex
    PHA
    JSR DrawItemBySlot
    PLA
    CLC
    ADC #SPRITES_PER_ITEM
    STA RollingSpriteIndex
    RTS

; --- data ---------------------------------------------------------------------------------------

SPRITES_PER_ITEM    = 2                 ; a pair of rolling sprite indices (SpriteOffsets)

; Sprite Y is the row's top pixel minus one.
STATS_PASSIVE_ROW_Y = 1 * 8 - 1         ; rows 1-2, beside the seed number
STATS_FIRST_ROW_Y   = 4 * 8 - 1         ; rows 4-5, in the box
STATS_SECOND_ROW_Y  = 6 * 8 - 1         ; rows 6-7, in the box
ITEMS_SHIFT         = $10               ; the item screen's Xs, one 16-pixel tile to the right
STATS_BOOMERANG_X   = $80 + ITEMS_SHIFT
STATS_POTION_X      = $B0 + ITEMS_SHIFT

; The other items: their slot and place, the item screen's Xs (SubmenuItemXs) moved ITEMS_SHIFT
; right, clear of the seed number (columns 2-16).
STATS_ITEM_COUNT = 13
StatsItemSlots:
    .BYTE $0E, $0D, $0C, $0B, $0A, $09  ; bracelet, magic key, ladder, ring, book, raft
    .BYTE $04, $03, $02, $01            ; candle, bow, arrow, bombs (when some are left)
    .BYTE $08, $06, $05                 ; rod, food, recorder
StatsItemXs:
    .BYTE $CC + ITEMS_SHIFT, $C0 + ITEMS_SHIFT, $B0 + ITEMS_SHIFT, $A0 + ITEMS_SHIFT, $94 + ITEMS_SHIFT, $80 + ITEMS_SHIFT
    .BYTE $C8 + ITEMS_SHIFT, $B4 + ITEMS_SHIFT, $AC + ITEMS_SHIFT, $98 + ITEMS_SHIFT
    .BYTE $C8 + ITEMS_SHIFT, $98 + ITEMS_SHIFT, $80 + ITEMS_SHIFT
StatsItemYs:
    .BYTE STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y
    .BYTE STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y, STATS_PASSIVE_ROW_Y
    .BYTE STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y, STATS_FIRST_ROW_Y
    .BYTE STATS_SECOND_ROW_Y, STATS_SECOND_ROW_Y, STATS_SECOND_ROW_Y

; The counters: two cells a row (columns 2-7 and 8-14, ending at COUNTERS_END_COLUMN, left of the
; box), each an icon over its
; first two columns and two rows, then the small x and the count on the lower row. The left cells'
; counts (deaths, at most 255; heart containers, at most 16) take 3 columns, the right ones 4.
NAME_LENGTH         = 8
COUNTERS_END_COLUMN = 15
COUNTER_ICON_COLUMNS = 2
SHORT_COUNT_COLUMNS = 3
COUNTER_LEFT_X      = 2 * 8
COUNTER_RIGHT_X     = (2 + COUNTER_ICON_COLUMNS + 1 + SHORT_COUNT_COLUMNS) * 8
COUNTER_UPPER_Y     = 4 * 8 - 1         ; rows 4-5: deaths, stabs
COUNTER_LOWER_Y     = 6 * 8 - 1         ; rows 6-7: heart containers, bombs
WOOD_SWORD_VALUE    = $01
BOMB_TILE           = $34
BOMB_PALETTE        = $01               ; ItemSlotToPaletteOffsetsOrValues' for the bombs
HALF_WIDTH_CENTER   = 4                 ; a half-width item is drawn 4 pixels in, centered
LINK_PALETTE        = $00
RED_PALETTE         = $02
FLIP_HORIZONTALLY   = $40
SLIM_SEPARATION     = 7                 ; a slim item's sides overlap one pixel (Anim_WriteSpecificItemSprites)

; Sprites 0-4 (Y, tile, attributes, X): Link facing down with his shield, as he stands in play, a
; heart container, red, and a bomb, as the item screen draws them.
CounterSprites:
    .BYTE COUNTER_UPPER_Y, $5A, LINK_PALETTE, COUNTER_LEFT_X
    .BYTE COUNTER_UPPER_Y, $08, LINK_PALETTE | FLIP_HORIZONTALLY, COUNTER_LEFT_X + 8
    .BYTE COUNTER_LOWER_Y, $68, RED_PALETTE, COUNTER_LEFT_X
    .BYTE COUNTER_LOWER_Y, $68, RED_PALETTE | FLIP_HORIZONTALLY, COUNTER_LEFT_X + SLIM_SEPARATION
    .BYTE COUNTER_LOWER_Y, BOMB_TILE, BOMB_PALETTE, COUNTER_RIGHT_X + HALF_WIDTH_CENTER
COUNTER_SPRITES_SIZE = * - CounterSprites

; The small x, background color 1 (white), its strokes on the digits' middle rows.
SmallXPattern:
    .BYTE %00000000
    .BYTE %00000000
    .BYTE %01000100
    .BYTE %00101000
    .BYTE %00010000
    .BYTE %00101000
    .BYTE %01000100
    .BYTE %00000000
    .RES 8, $00

; The seed number's 20 digit tiles (code_patches.STATS_SEED_DIGITS, written by generation in bank 2's
; free space outside every patch): 10 on row 1 after SEED, the rest under them; $FF, none written.
StatsSeedDigits     = $B780
NO_SEED_NUMBER      = $FF
SEED_DIGITS_PER_ROW = 10
SEED_DIGITS_COLUMN  = 7
SEED_DIGITS_END_COLUMN = SEED_DIGITS_COLUMN + SEED_DIGITS_PER_ROW
HEADINGS_COLUMN     = 13

; Each save slot's name in Names (8 tiles a slot).
StatsNameOffsets:
    .BYTE 0, 8, 16

; Background palette 0 white text; 1 the headings' orange text and the box's blue line (the font
; draws in color 1, the box tiles in color 3), so the headings share an attribute cell with the
; box's bottom; 2 white text and the box's blue line; 3 unused.
StatsBackgroundPalettes:
    .BYTE $0F, $30, $30, $30, $0F, $27, $27, BOX_BLUE, $0F, $30, $30, BOX_BLUE, $0F, $30, $30, $30

; The box around the B items, the status bar's own tiles (their lines in color 3), on columns
; 17-29 of rows 3-8: the items' Xs $90-$E3 with 7 pixels to each line.
BOX_LEFT_COLUMN     = 17
BOX_RIGHT_COLUMN    = 29
BOX_INSIDE_COLUMNS  = BOX_RIGHT_COLUMN - BOX_LEFT_COLUMN - 1
BOX_BLUE            = $12
BoxTiles:
BoxTop:
    .BYTE $69, $6A, $6B                 ; the corners and the line between them
BoxSide:
    .BYTE $6C, SPACE, $6C
BoxBottom:
    .BYTE $6E, $6A, $6D

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
    .BYTE "BOW      "
TextHeadings:
    .BYTE "TIME IN   CLEARED"
TextHeadingsEnd:
TextSeed:
    .BYTE "SEED "
TextSeedEnd:
TextPushStart:
    .BYTE "PUSH START BUTTON"
TextPushStartEnd:
TextTimeCap:
    .BYTE "9.59.59"

; Palette 2 under the box (rows 2-7, columns 16-29; row 2's column 16 holds only the seed's last
; digit, white in either palette), palette 1 under the box's bottom and the headings (rows 8-9,
; columns 12-29); palette 0 elsewhere.
StatsAttributes:
    .BYTE $00, $00, $00, $00, $A0, $A0, $A0, $20
    .BYTE $00, $00, $00, $00, $AA, $AA, $AA, $22
    .BYTE $00, $00, $00, $05, $05, $05, $05, $01
    .RES 5 * 8, $00
