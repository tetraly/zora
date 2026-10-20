.SEGMENT "ZORA_F2_POLS_VOICE"

; ZORA 2.0 Recorder Kills Dungeon Pols Voice (credit: Stratoform).
; Called first thing in UpdatePolsVoice, X: the Pols Voice's slot.
; Once the recorder has been played in this dungeon room (UsedFlute set) and its tune has
; ended (FluteTimer back at 0), deal the Pols Voice its whole HP as sword damage, so it dies
; the usual way, and return from UpdatePolsVoice too: a dying monster is not moved this frame.
; Why the timer: objects still update on the frame the recorder is played, and a kill there
; makes DealDamage's sound request replace the recorder's tune before the sound engine starts
; it, so the recorder was silent in a Pols Voice room (bug fix, 2026-10-17).
KillPolsVoiceAfterRecorder:
    LDA UsedFlute
    BEQ @Alive
    LDA FluteTimer
    BNE @Alive                  ; the tune is still playing
    LDA ObjHP, X
    STA $07                     ; [07] damage points: all of its HP
    LDA #$01
    STA $09                     ; [09] damage type: the sword's
    JSR DealDamage
    PLA                         ; drop UpdatePolsVoice's return address
    PLA
@Alive:
    RTS
