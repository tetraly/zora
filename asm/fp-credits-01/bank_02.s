.SEGMENT "ZORA_FP_CREDITS_01"

; ZORA FP-CREDITS-01: DrawCredits by ZORA's tables. CreditsRow counts the credits' tile rows
; (rows 30 and 31 of each 32 never come). ZORA writes the tables for each ROM
; (zora/rom/credits_staff.py); until then they hold no text and no walls.

; DrawCredits' walls: A = 0 none, 1 the side walls, 2 a horizontal wall, for CreditsRow inside
; or on the edge of a box of ZORA_B2_CreditsBoxes (top, bottom pairs, $FF ends).
CreditsWalls:
    LDX #$00
@Box:
    LDA ZORA_B2_CreditsBoxes, X
    CMP #$FF
    BEQ @None
    CMP CreditsRow
    BEQ @Horizontal
    BCS @Next                       ; the box starts below this row
    LDA ZORA_B2_CreditsBoxes+1, X
    CMP CreditsRow
    BEQ @Horizontal
    BCS @Side
@Next:
    INX
    INX
    BNE @Box
@None:
    LDA #$00
    RTS
@Side:
    LDA #$01
    RTS
@Horizontal:
    LDA #$02
    RTS

; Where DrawCredits goes on (CPU addresses: a label there would end the game's local-label
; scopes): @IncLine, @IncVramLine, and the copy of a record whose address is in [$00:$01].
CREDITS_INC_LINE      = $AEDF
CREDITS_INC_VRAM_LINE = $AEE2
CREDITS_COPY_RECORD   = $AE94       ; LDY #$00, the record's length

; DrawCredits' text, in place of PRG0's page masks: no text on this row, a line the quest skips
; (its index is used up), or the line's record. The first quest shows the lines below
; ZORA_B2_CreditsFirstQuestEnd, the second quest skips those from the first to the second
; byte of ZORA_B2_CreditsSecondQuestSkip, as PRG0's $10 and $0C-$0F.
CreditsRowLine:
    LDA CreditsRow
    LSR
    LSR
    LSR
    TAY
    LDA CreditsRow
    AND #$07
    TAX
    LDA ZORA_B2_CreditsTextRows, Y
@Shift:                             ; the row's bit to bit 7
    CPX #$00
    BEQ @Shifted
    ASL
    DEX
    BPL @Shift
@Shifted:
    AND #$80
    BEQ @None
    LDY CreditsLineIndex
    CPY ZORA_B2_CreditsLineCount
    BCS @None
    LDX CurSaveSlot
    LDA QuestNumbers, X
    BNE @SecondQuest
    CPY ZORA_B2_CreditsFirstQuestEnd
    BCS @Skip
    BCC @Text
@SecondQuest:
    CPY ZORA_B2_CreditsSecondQuestSkip
    BCC @Text
    CPY ZORA_B2_CreditsSecondQuestSkip+1
    BCC @Skip
@Text:
    LDA ZORA_B2_CreditsLinesLo, Y
    STA $00
    LDA ZORA_B2_CreditsLinesHi, Y
    STA $01
    JMP CREDITS_COPY_RECORD
@Skip:
    JMP CREDITS_INC_LINE
@None:
    JMP CREDITS_INC_VRAM_LINE

; DrawCredits' next VRAM page in Y: after page $B, page 4 ($2000), so the pages keep alternating
; the two nametables; PRG0 went back to page 0 ($2800), which its scroll never reached.
CreditsWrapPage:
    CPY #$0C
    BCC :+
    LDY #$04
:
    RTS

.SEGMENT "ZORA_FP_CREDITS_01_DATA"

; ZORA's tables, written per ROM (zora/rom/credits_staff.py reads these labels' addresses).
.EXPORT ZORA_B2_CreditsTextRows, ZORA_B2_CreditsLinesLo, ZORA_B2_CreditsLinesHi
.EXPORT ZORA_B2_CreditsLineCount, ZORA_B2_CreditsFirstQuestEnd, ZORA_B2_CreditsSecondQuestSkip
.EXPORT ZORA_B2_CreditsNameLine, ZORA_B2_CreditsBoxes, ZORA_B2_CreditsAttributes, ZORA_B2_CreditsRecords
ZORA_B2_CreditsTextRows:            ; a bit per CreditsRow, the high bit first
    .RES 32, $00
ZORA_B2_CreditsLinesLo:             ; each line's record address, in the order the rows take them
    .RES 64, $00
ZORA_B2_CreditsLinesHi:
    .RES 64, $00
ZORA_B2_CreditsLineCount:
    .BYTE $00
ZORA_B2_CreditsFirstQuestEnd:
    .BYTE $00
ZORA_B2_CreditsSecondQuestSkip:
    .BYTE $00, $00
ZORA_B2_CreditsNameLine:
    .BYTE $FF
ZORA_B2_CreditsBoxes:               ; (top row, bottom row) pairs, $FF ends
    .RES 8, $FF
ZORA_B2_CreditsAttributes:          ; an attribute byte per four CreditsRows
    .RES 64, $00
ZORA_B2_CreditsRecords:             ; the new lines' records: length, first column, tiles
    .RES 1024, $00
