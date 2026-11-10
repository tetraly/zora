.SEGMENT "ZORA_F2_ITEM_COUNTER"

; ZORA Item Counter (the ZORA flag item_counter; idea: Ultralavos): the status bar row under the rupees.

; The seed's table (asm/rom_space.toml site "item-counter-table"; zora/generate/item_counter.py):
;   10 bytes, one per area (0 the overworld, 1-9 the levels): the offset of the area's block in the table.
;   A block: the area's room flags address (low, high), U, G and K, then U + G places, a byte each:
;     $00-$7F  a room, cellar or overworld screen: bit $10 (item taken) of its byte in the room flags;
;     $80-$9F  a shop ware, %100PPSSS: bit SSS (the shop number) of ShopBoughtFlags + PP.
;   The first U places count one each once taken; the G after them, heart containers of which only K
;   count, count at most K together. The area's total is U + K; 0 leaves the row blank.
ItemCounterTable := $BA40
BLOCK_FLAGS_LOW = 0
BLOCK_FLAGS_HIGH = 1
BLOCK_UNIQUE = 2
BLOCK_GROUP = 3
BLOCK_CAP = 4
BLOCK_PLACES = 5
ROOM_FLAG_ITEM_TAKEN = $10
PLACE_WARE = $80
WARE_SHOP_MASK = $07
ShopBoughtFlags := Items+$20        ; fp-prog-01's: a byte per ware position, a bit per shop

COUNTER_ADDRESS_HIGH = $20          ; PPU $208B: the row under the rupees, in the icons' column
COUNTER_ADDRESS_LOW = $8B
COUNTER_TILES = 4
TRANSFER_END = $FF

TILE_CHEST = $50                    ; CommonBackgroundPatterns' blank tiles $50 and $51 (zora/rom/item_counter.py)
TILE_SLASH = $51
TILE_BLANK = $24

; Scratch: World_ChangeRupees and its caller are done with it.
FlagsAddress := $00                 ; and $01
PlaceAddress := $02                 ; and $03
UniqueLeft := $04
GroupLeft := $05
Found := $06
GroupFound := $07
Cap := $08
Total := $09

; In place of World_ChangeRupees' LDA FrameCounter / LSR, which then returns (BCS) on every other frame.
; World_ChangeRupees has checked that no static transfer is chosen and that the dynamic buffer is free.
; Returns C as the LSR leaves it.
;
ItemCounterOnSkippedFrames:
    LDA FrameCounter
    LSR
    BCC @Return                     ; a frame that formats the status bar text
    JSR WriteCounterRecord
    SEC

@Return:
    RTS

; The counter's record, alone in the dynamic buffer.
;
WriteCounterRecord:
    LDA #COUNTER_ADDRESS_HIGH
    STA DynTileBuf
    LDA #COUNTER_ADDRESS_LOW
    STA DynTileBuf+1
    LDA #COUNTER_TILES
    STA DynTileBuf+2
    LDA #TRANSFER_END
    STA DynTileBuf+3+COUNTER_TILES
    LDX #COUNTER_TILES-1
    LDA #TILE_BLANK
:
    STA DynTileBuf+3, X
    DEX
    BPL :-

    ; Blank when the area counts nothing; else the chest, found, slash and total, each the font's tile
    ; for its value (0-9, then A-F for 10-15).
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

; For the area Link is in (CurLevel): returns A (and Z) the total, and Found.
;
CountItems:
    LDY CurLevel
    LDX ItemCounterTable, Y
    LDA ItemCounterTable+BLOCK_FLAGS_LOW, X
    STA FlagsAddress
    LDA ItemCounterTable+BLOCK_FLAGS_HIGH, X
    STA FlagsAddress+1
    LDA ItemCounterTable+BLOCK_UNIQUE, X
    STA UniqueLeft
    LDA ItemCounterTable+BLOCK_GROUP, X
    STA GroupLeft
    LDA ItemCounterTable+BLOCK_CAP, X
    STA Cap
    CLC
    ADC UniqueLeft
    STA Total
    LDA #$00
    STA Found
    STA GroupFound

@Unique:
    LDA UniqueLeft
    BEQ @Group
    DEC UniqueLeft
    JSR IsPlaceTaken
    BEQ @Unique
    INC Found
    BNE @Unique

@Group:
    LDA GroupLeft
    BEQ @Sum
    DEC GroupLeft
    JSR IsPlaceTaken
    BEQ @Group
    INC GroupFound
    BNE @Group

@Sum:
    ; Found + min(GroupFound, K); the total U + K
    LDA GroupFound
    CMP Cap
    BCC :+
    LDA Cap
:
    CLC
    ADC Found
    STA Found
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
