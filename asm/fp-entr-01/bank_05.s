.SEGMENT "ZORA_FP_ENTR_01"

; ZORA FP-ENTR-01: Link's starting direction, X and Y by the level's
; arrival code, level information +$3D (the cellar array's unused last
; entry): 0 for the overworld, 2 for each dungeon.
LevelInfo_ArrivalCode := LevelInfo_PalettesTransferBuf + $3D
ARRIVAL_OVERWORLD = 0
ARRIVAL_DUNGEON = 2
ARRIVAL_X = $78
DUNGEON_ARRIVAL_Y = $DD
FACING_UP = $08
FACING_NONE = $00                   ; Link is drawn facing left until he moves

; Link's overworld start Y (OW-START-01), written per seed by ZORA;
; LevelInfo_StartY keeps PRG0's value.
.EXPORT ZORA_B5_OverworldStartY
ZORA_B5_OverworldStartY:
    .BYTE $8D

PlaceLinkByArrivalCode:
    LDA #ARRIVAL_X
    STA ObjX
    LDA LevelInfo_ArrivalCode
    BEQ @Overworld
    CMP #ARRIVAL_DUNGEON
    BNE @Default
    LDA #FACING_UP
    STA ObjDir
    LDA #DUNGEON_ARRIVAL_Y
    STA ObjY
    JMP BeginUpdateMode

@Overworld:
    LDA #FACING_NONE
    STA ObjDir
    LDA ZORA_B5_OverworldStartY
    STA ObjY
    JMP BeginUpdateMode

@Default:
    ; Any other code: PRG0's placement.
    LDA #FACING_UP
    STA ObjDir
    LDA LevelInfo_StartY
    STA ObjY
    JMP BeginUpdateMode
