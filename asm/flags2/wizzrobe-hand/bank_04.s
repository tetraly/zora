.SEGMENT "ZORA_F2_WIZZROBE_HAND"

WALLMASTER_FRAMES = 146                 ; the Wallmaster's frames in ObjAnimFrameHeap (open hand, closed hand)

; Params:
; X: monster shot slot
;
; UpdateMonsterShot's collision check. After CheckShotLinkCollision, a Wizzrobe shot in a dungeon that
; touched Link either hurt him ([0C] set): then, unless that killed him, the Wallmaster's capture ending
; runs at once; or was parried by the Magical Shield: then [06] is set so the caller destroys it.
CheckShotLinkCollisionOrGrab:
    JSR CheckShotLinkCollision
    LDA ShotCollidesWithLink
    BEQ @Exit
    LDA CurLevel
    BEQ @Exit
    LDA ObjType, X
    CMP #$58
    BCC @Exit
    CMP #$5A
    BCS @Exit
    LDA $0C
    BNE @Grab
    INC $06                     ; Blocked: destroy it instead of bouncing.
@Exit:
    RTS

@Grab:
    ; A hit that killed Link has already set mode $11.
    LDA GameMode
    CMP #$11
    BEQ @Exit

    ; As UpdateWallmaster at the end of a capture: hide the sprites over Link,
    ; go to mode 3 to unfurl to the level's entrance, and make Link idle.
    ; (The stores are independent; their order is ZORA's own.)
    JSR HideSpritesOverLink
    LDA #$00
    STA ObjState
    STA GameSubmode
    STA IsUpdatingMode
    LDA #$03
    STA GameMode
    RTS                         ; [06] is set: the caller destroys the shot.

; Params:
; A: monster shot's object type ($57 to $59)
; X: monster shot slot
; Y: $22, the sword shot's item slot
;
; DrawSwordShotOrMagicShot's choice for a monster's shot: a sword shot as before; a Wizzrobe's magic shot
; as the Wallmaster's hand, in the Wallmaster's palette row, with the shot's flips; on the overworld,
; the magic shot.
ChooseMonsterShotSprites:
    CMP #$57
    BEQ @Write
    LDY #$23
    LDA CurLevel
    BEQ @Write

    LDA $04
    AND #$FC
    ORA #$01
    STA $04
    STA $05

    ; The state Anim_WriteItemSprites sets up before its tile lookup, with the hand's tile in place of the
    ; item frame's. (The stores are independent; their order is ZORA's own.)
    LDA #$08
    STA $0A
    LDA #$01
    STA $07
    STX $08
    LDY RollingSpriteIndex
    LDA SpriteOffsets+1, Y
    STA RightSpriteOffset
    LDA SpriteOffsets, Y
    STA LeftSpriteOffset
    LDA #$00
    STA ProcessedNarrowObj
    ; The left tile of the Wallmaster's open hand, its first frame (ObjAnimFrameHeap + 146): $AC, where the
    ; enemy groups' pack puts it.
    LDA ObjAnimFrameHeap + WALLMASTER_FRAMES
    ; Anim_WriteSpecificItemSprites from STA $02, after its tile lookup (20 bytes in).
    JMP Anim_WriteSpecificItemSprites + 20

@Write:
    JMP Anim_WriteItemSprites
