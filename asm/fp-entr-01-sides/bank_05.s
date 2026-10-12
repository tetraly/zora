.SEGMENT "ZORA_FP_ENTR_01_SIDES"

; ZORA FP-ENTR-01, codes 1, 3 and 4 (B26, PS-START-03): Link enters the
; moved start room through its open side, facing into the room.
ARRIVAL_FROM_ABOVE = 1
ARRIVAL_FROM_LEFT = 3
ARRIVAL_FROM_RIGHT = 4
TOP_ARRIVAL_Y = $3D
SIDE_ARRIVAL_Y = $8D
LEFT_ARRIVAL_X = $00
RIGHT_ARRIVAL_X = $F0
FACING_RIGHT = $01
FACING_LEFT = $02
FACING_DOWN = $04

PlaceLinkBySide:
    LDA LevelInfo_ArrivalCode
    CMP #ARRIVAL_FROM_ABOVE
    BEQ @FromAbove
    CMP #ARRIVAL_FROM_LEFT
    BEQ @FromLeft
    CMP #ARRIVAL_FROM_RIGHT
    BEQ @FromRight
    JMP PlaceLinkByArrivalCode

@FromAbove:
    LDA #ARRIVAL_X
    STA ObjX
    LDA #TOP_ARRIVAL_Y
    STA ObjY
    LDA #FACING_DOWN
    BNE @Face                       ; always taken

@FromLeft:
    LDA #LEFT_ARRIVAL_X
    STA ObjX
    LDA #SIDE_ARRIVAL_Y
    STA ObjY
    LDA #FACING_RIGHT
    BNE @Face                       ; always taken

@FromRight:
    LDA #RIGHT_ARRIVAL_X
    STA ObjX
    LDA #SIDE_ARRIVAL_Y
    STA ObjY
    LDA #FACING_LEFT

@Face:
    STA ObjDir
    JMP BeginUpdateMode
