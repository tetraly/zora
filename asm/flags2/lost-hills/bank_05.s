.SEGMENT "ZORA_F2_LOST_HILLS"

; ZORA Randomize Lost Hills: screen layouts $7C-$7F. A screen's layout number (LevelBlockAttrsD bits
; 6-0) indexes RoomLayoutsOW, 16 column descriptors each, which holds $00-$7B. Numbers $7C-$7F index
; ExtraLayouts instead, four more rows that zora/rom/extra_layouts.py writes. The idea of sending
; the unused numbers to a second table is gzip's.
;
; LayoutRoomOW multiplies the number by 16 and adds it to [$02:03], so for $7C-$7F this returns
; ExtraLayouts less $7C0: $7C lands on its first row with the game's own arithmetic.
FIRST_EXTRA_LAYOUT = $7C
LAYOUT_NUMBER_MASK = $7F            ; bit 7 is the monster list's high bit
LAYOUT_COLUMNS = 16
ExtraLayouts := $BBC0
EXTRA_BASE = ExtraLayouts - FIRST_EXTRA_LAYOUT * LAYOUT_COLUMNS

; Called by LayoutRoomOW for the current overworld screen. Leaves the base in [$02:03]; A and X
; are the caller's to load again. The number's carry from the compare picks the base.
ExtraLayoutsBase:
    LDX RoomId
    LDA LevelBlockAttrsD, X
    AND #LAYOUT_NUMBER_MASK
    CMP #FIRST_EXTRA_LAYOUT
    LDA #<RoomLayoutsOW
    LDX #>RoomLayoutsOW
    BCC @Store                      ; $00-$7B: the game's own table
    LDA #<EXTRA_BASE
    LDX #>EXTRA_BASE
@Store:
    STA $02
    STX $03
    RTS
