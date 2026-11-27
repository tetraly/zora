.SEGMENT "ZORA_F2_LEVEL_COMPASS"

; Per-seed data, first in the segment (zora/rom/level_items.py writes it at COMPASS_ROOMS): for each data level
; 1-8, the room whose item-taken flag the marker follows: the compass's marked room (the level's original Triforce
; room), or the item cellar under it where the level's piece stood.
LevelCompassRooms:
    .RES 8, $00

LEVEL_COMPASS_ZELDA_LEVEL = 9           ; level 9's marker blinks always, as the game's does
ROOM_FLAG_ITEM_TAKEN = $10
MARKER_STEADY = $03                     ; the game's two palettes: 3 shown alone once taken,
MARKER_BLINK = $02                      ; 2 for half of every 32 frames before
MARKER_BLINK_FRAMES = $10
FlagsPointer := $00                     ; and $01, both kept for the caller
; marker-palette-back (bank 1 $AA97, file 0x06AA7) where the game runs it: bank 1's $A500-$B76F is copied to
; battery RAM $6C90 (CopyCommonCodeToRam), so $6C90 + $AA97 - $A500
MARKER_PALETTE_BACK = $7227

; Reached by JMP from marker-palette (battery RAM, bank 6 mapped); goes back by JMP to MARKER_PALETTE_BACK, which
; maps bank 5 again.
;
; Returns:
; Y: the Triforce marker's palette, by the marked room's item in levels 1-8
; X: kept (the marker's sprite record)
CompassMarkerPalette:
    LDY CurLevel
    CPY #LEVEL_COMPASS_ZELDA_LEVEL
    BEQ @Blink
    LDA FlagsPointer
    PHA
    LDA FlagsPointer+1
    PHA
    LDA LevelInfo_WorldFlagsAddr+1
    STA FlagsPointer+1
    LDA LevelInfo_WorldFlagsAddr
    STA FlagsPointer
    LDA LevelCompassRooms-1, Y
    TAY
    LDA (FlagsPointer), Y
    TAY
    PLA
    STA FlagsPointer+1
    PLA
    STA FlagsPointer
    TYA
    AND #ROOM_FLAG_ITEM_TAKEN
    BNE @Steady

@Blink:
    LDA FrameCounter
    AND #MARKER_BLINK_FRAMES
    BNE @Steady
    LDY #MARKER_BLINK
    JMP MARKER_PALETTE_BACK

@Steady:
    LDY #MARKER_STEADY
    JMP MARKER_PALETTE_BACK
