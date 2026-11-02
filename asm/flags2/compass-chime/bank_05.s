.SEGMENT "ZORA_F2_COMPASS_CHIME_B5"

; ZORA Compass Chime (the ZORA flag compass_chime; docs/zora-extras.md section 25): the room check.

; Compass chime: when Link enters a dungeon room with this level's
; compass, a chime plays if the room has a hidden item not yet taken
; (one that appears for killing the foes or the last boss), or if it has
; stairs (open, walled in by blocks, or under a push block) to an item
; cellar whose item is not yet taken.

COMPASS_CHIME_REQUEST = $06     ; Tune1Request value bank 0 turns into the chime.
; RoomItemNothingCode, the operand of CreateRoomObjects' no-item compare (ZORA writes $0E there under
; the no-item remap, layout.ASM_NOTHING_CODE_PATCH_OFFSET), is fp-prog-02's (asm/series.txt).
SECRET_TRIGGER_MASK = $07
SECRET_LAST_BOSS = $03
SECRET_FOES_FOR_ITEM = $07
ROOM_ITEM_MASK = $1F
UNIQUE_ROOM_MASK = $3F
UNIQUE_ROOM_ITEM_CELLAR = $3F
ROOM_FLAG_ITEM_TAKEN = $10
CELLAR_LIST_LENGTH = 10
CELLAR_LIST_END = $FF
ENEMY_MASK = $3F
ENEMY_GANON = $3E
ENEMY_HIGH_BIT = $80            ; In attribute D: the enemy code is $40 or more.

; In place of JSR CreateRoomObjects in bank 7 (bank 5 is in).
;
CreateRoomObjectsAndChime:
    JSR CreateRoomObjects

    ; Room objects are made twice on the way in: as Link walks in
    ; (mode 4) and as play starts (mode 5). Chime once, as play starts.
    ; (Cellars, mode 9, never chime: their item is in plain sight.)
    ; Only with the compass (HasCompass also returns 0 in the overworld).
    LDA GameMode
    CMP #$05
    BNE @Exit
    JSR HasCompass
    BEQ @Exit

    ; A hidden item: one the foes or the last boss hold back, or the
    ; Triforce of Power, which Ganon's death reveals whatever the trigger.
    LDY RoomId
    JSR IsGanonRoom
    BEQ @Hidden
    LDA LevelBlockAttrsF, Y
    AND #SECRET_TRIGGER_MASK
    CMP #SECRET_FOES_FOR_ITEM
    BEQ @Hidden
    CMP #SECRET_LAST_BOSS
    BNE @Stairs

@Hidden:
    JSR IsRoomItemWaiting
    BNE @Chime

@Stairs:
    ; Find a cellar the room's stairs lead to, as the stairs do: one
    ; whose destination A or B is this room. The list ends at $FF.
    LDX #$00
@FindCellar:
    LDA LevelInfo_CellarRoomIdArray, X
    CMP #CELLAR_LIST_END
    BEQ @Exit
    TAY
    LDA RoomId
    CMP LevelBlockAttrsA, Y
    BEQ @FoundCellar
    CMP LevelBlockAttrsB, Y
    BEQ @FoundCellar
    INX
    CPX #CELLAR_LIST_LENGTH
    BCC @FindCellar
    RTS

@FoundCellar:
    ; Only an item cellar, not a tunnel to another room.
    LDA LevelBlockAttrsD, Y
    AND #UNIQUE_ROOM_MASK
    CMP #UNIQUE_ROOM_ITEM_CELLAR
    BNE @Exit
    JSR IsRoomItemWaiting
    BEQ @Exit

@Chime:
    LDA #COMPASS_CHIME_REQUEST
    STA Tune1Request

@Exit:
    RTS

; Params:
; Y: room ID
;
; Returns:
; A: nonzero (Z clear) if the room has an item not yet taken
;
IsRoomItemWaiting:
    LDA LevelBlockAttrsE, Y
    AND #ROOM_ITEM_MASK
    CMP RoomItemNothingCode
    BNE @HasItem
    ; A randomizer may make the no-item code $0E, the Triforce of Power's:
    ; then that code in Ganon's room is still his Triforce.
    JSR IsGanonRoom
    BNE @None

@HasItem:
    LDA LevelInfo_WorldFlagsAddr+1
    STA $01
    LDA LevelInfo_WorldFlagsAddr
    STA $00
    LDA ($00), Y
    AND #ROOM_FLAG_ITEM_TAKEN
    EOR #ROOM_FLAG_ITEM_TAKEN
    RTS

@None:
    LDA #$00
    RTS

; Params:
; Y: room ID
;
; Returns:
; Z: set if Ganon is the room's enemy
;
IsGanonRoom:
    LDA LevelBlockAttrsD, Y
    AND #ENEMY_HIGH_BIT
    BNE @Return
    LDA LevelBlockAttrsC, Y
    AND #ENEMY_MASK
    CMP #ENEMY_GANON

@Return:
    RTS
