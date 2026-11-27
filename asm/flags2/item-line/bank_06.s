.SEGMENT "ZORA_F2_ITEM_LINE_HOP_B6"

; Bank 5's ItemLineEnter lands here ($BDAE) when its SwitchBank returns.
    JMP ItemLineLevel

.SEGMENT "ZORA_F2_ITEM_LINE"

; ZORA Show Item Pickups: the status bar's top row says what Link just took.
;
; The seed's table (asm/rom_space.toml site "item-line-names"; zora/rom/item_line.py):
;   ITEM_CODES low bytes, then ITEM_CODES high bytes: each item code's name, or a high byte of 0 for no line;
;   a name: its length N (1-24, bit 7 set for half the show time), then N font tiles. "GOT " comes from GotTiles.
ItemLineNames := $B240
ITEM_CODES = $24

ItemLineLatch := $F0                ; TakeItem's last item code, $FF once shown (bombs are code 0)
ItemLineTimer := $F1                ; every other frame one less while the line shows; at 0 the row is blanked
ItemLineAttrReq := $F2             ; bit 0 after a line is written: the next NMI makes the top row palette 0 (white);
                                    ; bit 7 (ARMED) once ItemLine has run, so ClearRam's 0 in the latch is not bombs
ARMED = $80
NO_ITEM = $FF
SHOW_TIME = 180                     ; 180 x 2 frames: 6 seconds; half that with the name's SHORT_BIT
SHORT_BIT = $80
GOT_TILES = 4

ROW_ADDRESS_HIGH = $20              ; PPU $2022: the status bar's blank top row
ROW_ADDRESS_LOW = $22
ROW_TILES = 28
RECORD_END = 3 + ROW_TILES          ; the record's $FF, and DynTileBufLen
TILE_BLANK = $24
TRANSFER_END = $FF
WCR_SLOT_INDEX = $27                ; World_ChangeRupees' LDY #$27, which the hook comes after

; Scratch: World_ChangeRupees and its caller are done with it (asm/flags2/item-counter).
Text := $00                         ; and $01
TilesLeft := $02

; Entered by JMP from the hop, with the hook's return (into World_ChangeRupees) on top of the stack. Writes the
; line for a new item, or the blank once the timer runs out, and then returns past World_ChangeRupees to its
; caller (the row's record has to be alone this frame: the status bar text and the Item Counter both write from
; DynTileBuf+0). Otherwise returns to the hook with Y as it was. Both ways go back through SwitchBank to bank 5's
; ItemLineTail.
;
ItemLine:
    BIT ItemLineAttrReq
    BMI ItemLineArmed
    LDA #ARMED                      ; the first call since ClearRam: its 0 in the latch is no item
    STA ItemLineAttrReq
    LDA #NO_ITEM
    STA ItemLineLatch
ItemLineArmed:
    LDX ItemLineLatch
    CPX #NO_ITEM
    BEQ ItemLineTick
    LDA #NO_ITEM
    STA ItemLineLatch
    CPX #ITEM_CODES
    BCS ItemLineTick                      ; not an item code
    LDA ItemLineNames+ITEM_CODES, X
    BEQ ItemLineTick                      ; an item with no line
    STA Text+1
    LDA ItemLineNames, X
    STA Text
ItemLineWrite:                      ; ItemLineLevel comes in here with Text at its composed name
    JSR BlankRecord

    ; The show time: half with SHORT_BIT.
    LDY #$00
    LDA (Text), Y
    ASL                             ; C = SHORT_BIT
    LDA #SHOW_TIME
    BCC :+
    LSR
:
    STA ItemLineTimer

    ; "GOT " and the name centered: the first tile at column (24 - N) / 2 + 3.
    LDA (Text), Y
    AND #<~SHORT_BIT
    STA TilesLeft
    LDA #ROW_TILES-GOT_TILES
    SEC
    SBC TilesLeft
    LSR
    CLC
    ADC #3
    TAX
    LDY #<-GOT_TILES
:
    LDA GotTiles-$100+GOT_TILES, Y   ; Y runs $FC-$FF
    STA DynTileBuf, X
    INX
    INY
    BNE :-                          ; Y = 0 again for the name
:
    INY
    LDA (Text), Y
    STA DynTileBuf, X
    INX
    DEC TilesLeft
    BNE :-
    LDA #ARMED|1
    STA ItemLineAttrReq             ; the NMI makes the top row's colours white
    ; The record is 28 tiles, so Tetra's NMI skips its 480-cycle glyph upload (under 25 bytes).
    ; ItemLineAttr is about 290 cycles; with a record under 20 tiles it plus that upload would be near vblank's end.
    BNE ItemLineWritten

ItemLineTick:
    LDA ItemLineTimer
    BEQ ItemLineBack
    LDA Paused
    ORA MenuState                          ; the item screen (Start, with Select's swap) is down too
    BNE ItemLineBack                       ; the line waits while the game is paused or the item screen is down
    LDA FrameCounter
    LSR
    BCC ItemLineBack
    DEC ItemLineTimer
    BNE ItemLineBack
    JSR BlankRecord

ItemLineWritten:
    PLA                             ; the hook's return: ItemLineTail's RTS goes to World_ChangeRupees' caller
    PLA

ItemLineBack:
    LDY #WCR_SLOT_INDEX
    LDA #>(ItemLineTail-1)
    PHA
    LDA #<(ItemLineTail-1)
    PHA
    LDA #$05
    JMP SwitchBank

; Called from TransferCurTileBuf in the NMI, after its transfer (bank 6 is in). The row is PPU $2022, columns 2-29:
; attribute bytes $23C0-$23C7. Each byte's low nibble is the top two quadrants (the row's colours); the read-modify-
; write keeps the high nibble (the bottom quadrants, the life meter's). Ends as TransferCurTileBuf did: buffer empty.
ItemLineAttr:
    LDA ItemLineAttrReq
    LSR
    BCC @Done
    LDA #ARMED
    STA ItemLineAttrReq
    LDA CurPpuControl_2000          ; +1 increment: a vertical record may have left +32 (as fp-fix-03)
    AND #$FB
    STA CurPpuControl_2000
    STA PpuControl_2000
    LDA #$23
    STA PpuAddr_2006
    LDA #$C0
    STA PpuAddr_2006
    LDA PpuData_2007                ; the first read after a $2006 write is stale
    LDX #$07
@Read:                              ; the buffer is transferred, so its first 8 bytes are free
    LDA PpuData_2007                ; $23C0 first, kept at DynTileBuf+7
    AND #$F0                        ; the low nibble to palette 0
    STA DynTileBuf, X
    DEX
    BPL @Read
    LDA #$23
    STA PpuAddr_2006
    LDA #$C0
    STA PpuAddr_2006
    LDX #$07
@Write:
    LDA DynTileBuf, X               ; DynTileBuf+7 first: $23C0's byte
    STA PpuData_2007
    DEX
    BPL @Write
@Done:
    LDX #$FF
    STX DynTileBuf
    RTS

.SEGMENT "ZORA_F2_ITEM_LINE_LEVEL"     ; bank 6 too: ZORA_F2_ITEM_LINE has no room for it

; The row's record, all blank, alone in the dynamic buffer.
;
BlankRecord:
    LDA #ROW_ADDRESS_HIGH
    STA DynTileBuf
    LDA #ROW_ADDRESS_LOW
    STA DynTileBuf+1
    LDA #ROW_TILES
    STA DynTileBuf+2
    LDA #TRANSFER_END
    STA DynTileBuf+RECORD_END
    LDA #RECORD_END                 ; records the game adds this frame go after it
    STA DynTileBufLen
    LDX #ROW_TILES-1
    LDA #TILE_BLANK
:
    STA DynTileBuf+3, X
    DEX
    BPL :-
    RTS

.SEGMENT "ZORA_F2_ITEM_LINE"

GotTiles:                           ; "GOT " in the font
    .BYTE $10, $18, $1D, $24

.SEGMENT "ZORA_F2_ITEM_LINE_LEVEL"

; Per-level mode only (Triforce Shuffle, Map & Compass Shuffle): the codes $24-$3E, and the generic
; compass and map (level 9's) and piece (level 8's). The line is "LEVEL", the number the status bar shows for that
; level, then the kind's own name from the table: "GOT LEVEL 4 TRIFORCE". The name is composed after the row's
; record in DynTileBuf, then ItemLine writes it from its BlankRecord call. Any other code goes on to ItemLine.
; shortcut: without ap-items this is the game's own byte ($94 in PRG0, never 1); if a non-ap-items patch ever
; writes 1 there, give the item line its own per-seed mode byte.
ApItemsPerLevelMode := $FD82        ; bank 7: 1 in per-level mode, 0 without (zora/rom/level_items.py)
PER_LEVEL_ON = $01
LevelShown := $9D70                 ; bank 6: each data level's status-bar number 1-9 (zora/rom/level_items.py)
LevelText := DynTileBuf+RECORD_END+1 ; up to 25 bytes (a 16-tile name), below OpenDoorwayMask ($33F)
COMPASS_CODE = $16
MAP_CODE = $17
TRIFORCE_CODE = $1B
FIRST_LEVEL_CODE = $24              ; compasses 1-8 $24-$2B, maps 1-8 $2C-$33, pieces 1-7 $38-$3E
KIND_LEVELS = 8
TRIFORCE_GAP = 4                    ; $34-$37 are not level items
TRIFORCE_LEVELS = 7
PREFIX_TILES = 6                    ; "LEVEL "
NAME_AT = 1+PREFIX_TILES+2           ; LevelText: its length, "LEVEL ", the digit, a space, then the name

ItemLineLevel:
    LDA ApItemsPerLevelMode
    CMP #PER_LEVEL_ON
    BNE @Other                      ; C = 1 from here on when it is on
    LDA ItemLineLatch
    TAX
    SBC #FIRST_LEVEL_CODE
    BCC @Generic
    LDX #COMPASS_CODE
    CMP #KIND_LEVELS
    BCC @Level
    SBC #KIND_LEVELS
    LDX #MAP_CODE
    CMP #KIND_LEVELS
    BCC @Level
    SBC #KIND_LEVELS+TRIFORCE_GAP
    BCC @Other
    LDX #TRIFORCE_CODE
    CMP #TRIFORCE_LEVELS
    BCC @Level
@Other:
    JMP ItemLine

@Generic:
    LDA #9-1
    CPX #COMPASS_CODE
    BEQ @Level
    CPX #MAP_CODE
    BEQ @Level
    LDA #8-1
    CPX #TRIFORCE_CODE
    BNE @Other

@Level:                             ; A: the data level - 1; X: the kind's generic code
    TAY
    LDA LevelShown, Y
    STA LevelText+1+PREFIX_TILES    ; the digit: the font's digit n is tile n
    LDA #TILE_BLANK
    STA LevelText+2+PREFIX_TILES
    LDA #NO_ITEM
    STA ItemLineLatch
    LDA ItemLineNames, X
    STA Text
    LDA ItemLineNames+ITEM_CODES, X
    STA Text+1                      ; the three generic codes always have a name
    LDX #PREFIX_TILES-1
:
    LDA LevelPrefix, X
    STA LevelText+1, X
    DEX
    BPL :-
    LDY #$00
    LDA (Text), Y
    AND #<~SHORT_BIT
    TAX
:
    INY
    LDA (Text), Y
    STA LevelText+NAME_AT-1, Y
    DEX
    BNE :-
    TYA
    CLC
    ADC #NAME_AT-1                  ; the line's length: the prefix, digit and space, then the name
    STA TilesLeft
    LDY #$00
    LDA (Text), Y
    AND #SHORT_BIT                  ; maps and compasses keep the short time
    ORA TilesLeft
    STA LevelText
    LDA #<LevelText
    STA Text
    LDA #>LevelText
    STA Text+1
    JMP ItemLineWrite

LevelPrefix:                        ; "LEVEL " in the font
    .BYTE $15, $0E, $1F, $0E, $15, $24
