.SEGMENT "ZORA_F2_ITEM_COUNTER"

; ZORA Item Counter (the ZORA flag item_counter; idea: Ultralavos): the status bar row under the rupees.

; The seed's table (asm/rom_space.toml site "item-counter-table"; zora/generate/item_counter.py):
;   10 bytes, one per area (0 the overworld, 1-9 the levels): the offset of the area's block in the table.
;   A block: the area's room flags address (low, high), N, then N places, a byte each:
;     $00-$7F  a room, cellar or overworld screen: bit $10 (item taken) of its byte in the room flags;
;     $80-$9F  a shop ware, %100PPSSS: bit SSS (the shop number) of ShopBoughtFlags + PP.
;   Each place counts one once taken. The area's total is N; 0 leaves the row blank.
; At $BE60, after the routines' slot: randomized music's lozft puts its own code at bank 5 $BA40-$BAB9.
ItemCounterTable := $BE60
BLOCK_FLAGS_LOW = 0
BLOCK_FLAGS_HIGH = 1
BLOCK_COUNT = 2
BLOCK_PLACES = 3
ROOM_FLAG_ITEM_TAKEN = $10
PLACE_WARE = $80
WARE_SHOP_MASK = $07
ShopBoughtFlags := Items+$20        ; fp-prog-01's: a byte per ware position, a bit per shop

COUNTER_ADDRESS_HIGH = $20          ; PPU $208B: the row under the rupees, in the icons' column
COUNTER_ADDRESS_LOW = $8B
COUNTER_TILES = 4
TRANSFER_END = $FF

GAME_MODE_STAIRS = $10              ; Link going down a cave's, level's or passage's stairs on the overworld

TILE_CHEST = $52                    ; CommonBackgroundPatterns' blank tiles $52 and $53 (zora/rom/item_counter.py)
TILE_SLASH = $53
TILE_BLANK = $24

; Scratch: World_ChangeRupees and its caller are done with it.
FlagsAddress := $00                 ; and $01
PlaceAddress := $02                 ; and $03
PlacesLeft := $04
Found := $05
Total := $06

; In place of World_ChangeRupees' LDA FrameCounter / LSR, which then returns (BCS) on every other frame.
; World_ChangeRupees has checked that no static transfer is chosen and that the dynamic buffer is free.
; Returns C as the LSR leaves it.
;
; Not in the stairs mode: Link stepping into a level's entrance (HandleWarpOW) sets CurLevel and the stairs mode
; inside a play frame, whose status bar update then comes, and the stairs mode draws no status bar, so the level's
; count would show for the whole walk down the overworld's stairs. That frame leaves the row as it is; the next
; play frame, in the level, writes the level's count. Leaving a level sets CurLevel back to 0 only after its last
; status bar update.
;
ItemCounterOnSkippedFrames:
    LDA FrameCounter
    LSR
    BCC @Return                     ; a frame that formats the status bar text
    LDA GameMode
    CMP #GAME_MODE_STAIRS
    BEQ @Return                     ; equal leaves C set: the text is skipped, as on any such frame
    JSR WriteCounterRecord
    SEC

@Return:
    RTS

; The counter's record, alone in the dynamic buffer: the blank record, then the counts.
;
WriteCounterRecord:
    LDX #BLANK_RECORD_SIZE-1
:
    LDA BlankCounterRecord, X
    STA DynTileBuf, X
    DEX
    BPL :-

    ; Blank when the area counts nothing; else chest, found, slash and total, the numbers each the font's
    ; tile for its value (0-9, then A-F for 10-15).
    JSR CountItems
    BEQ @Exit
    STA DynTileBuf+6
    LDA Found
    STA DynTileBuf+4
    LDA #TILE_CHEST
    STA DynTileBuf+3
    LDA #TILE_SLASH
    STA DynTileBuf+5

@Exit:
    RTS

; The record of a blank row: the PPU address, the tile count, the blank tiles, the end mark.
BlankCounterRecord:
    .BYTE COUNTER_ADDRESS_HIGH, COUNTER_ADDRESS_LOW, COUNTER_TILES
    .BYTE TILE_BLANK, TILE_BLANK, TILE_BLANK, TILE_BLANK
    .BYTE TRANSFER_END
BLANK_RECORD_SIZE = * - BlankCounterRecord

; For the area Link is in (CurLevel): returns A (and Z) the total, and Found.
;
CountItems:
    LDY CurLevel
    LDX ItemCounterTable, Y
    LDA ItemCounterTable+BLOCK_FLAGS_LOW, X
    STA FlagsAddress
    LDA ItemCounterTable+BLOCK_FLAGS_HIGH, X
    STA FlagsAddress+1
    LDA ItemCounterTable+BLOCK_COUNT, X
    STA PlacesLeft
    STA Total
    LDA #$00
    STA Found

@Next:
    DEC PlacesLeft                  ; N places (at most 15): $FF after the last
    BMI @Done
    JSR IsPlaceTaken
    BEQ @Next
    INC Found
    BNE @Next

@Done:
    LDA Total
    RTS

; X: the place before this one's offset in the table, less BLOCK_PLACES - 1. Returns Z clear when the
; place's bit is set; X at this place.
;
IsPlaceTaken:
    INX
    LDA ItemCounterTable+BLOCK_PLACES-1, X
    BMI @Ware
    ; A room, cellar or screen: its byte in the area's room flags.
    CLC
    ADC FlagsAddress
    STA PlaceAddress
    LDA FlagsAddress+1
    ADC #$00
    STA PlaceAddress+1
    LDA #ROOM_FLAG_ITEM_TAKEN
    BNE @Read

@Ware:
    ; A shop ware: ShopBoughtFlags + PP, bit SSS.
    PHA
    LSR
    LSR
    LSR
    AND #$03
    CLC
    ADC #<ShopBoughtFlags
    STA PlaceAddress
    LDA #>ShopBoughtFlags
    STA PlaceAddress+1
    PLA
    AND #WARE_SHOP_MASK
    TAY
    LDA #$01
:
    DEY
    BMI @Read
    ASL
    BNE :-

@Read:
    LDY #$00
    AND (PlaceAddress), Y
    RTS
