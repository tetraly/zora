.SEGMENT "ZORA_F2_POLS_VOICE"

; ZORA 2.0 Recorder Kills Dungeon Pols Voice (credit: Stratoform).
; Called first thing in UpdatePolsVoice, X: the Pols Voice's slot.
; While UsedFlute is set (the recorder was played in this dungeon room), deal the
; Pols Voice its whole HP as sword damage, so it dies the usual way, and return
; from UpdatePolsVoice too: a dying monster is not moved this frame.
KillPolsVoiceAfterRecorder:
    LDA UsedFlute
    BEQ @Alive
    LDA ObjHP, X
    STA $07                     ; [07] damage points: all of its HP
    LDA #$01
    STA $09                     ; [09] damage type: the sword's
    JSR DealDamage
    PLA                         ; drop UpdatePolsVoice's return address
    PLA
@Alive:
    RTS
