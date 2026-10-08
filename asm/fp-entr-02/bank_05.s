.SEGMENT "ZORA_FP_ENTR_02"

; ZORA FP-ENTR-02: the level's exit-room count, kept at level information
; +$23 as count | $80 (the palette transfer buffer's terminator, so bit 7
; still ends that buffer).
LevelInfo_ExitRoomCount := LevelInfo_PalettesTransferBuf + $23
EXIT_ROOM_COUNT_MASK = $7F

; A next room with bit 7 set leaves the level, as in PRG0; in a dungeon, a
; next room equal to the level's count also leaves it.
CheckLevelExitRoom:
    LDA NextRoomId
    BMI @Leave
    LDA CurLevel
    BEQ @Stay
    LDA LevelInfo_ExitRoomCount
    AND #EXIT_ROOM_COUNT_MASK
    CMP NextRoomId
    BNE @Stay

@Leave:
    JMP EndGameMode12

@Stay:
    JMP MaskCurPpuMaskGrayscale
