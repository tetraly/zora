.SEGMENT "ZORA_F2_COMPASS_CHIME_B0"

; ZORA Compass Chime (the ZORA flag compass_chime; docs/zora-extras.md section 25): the player.

; Compass chime: its own player on tune channel 1, so that its short
; notes can end in silence (the tune player's rests keep a note ringing).
; Tune1 holds COMPASS_CHIME_REQUEST while it plays; TunePtr1 is the offset
; in the script, NoteCounterTune1 the frames left. Any other tune 1
; request takes the channel back, as one tune replaces another.

; Script: a note's period low byte (each note's high byte is 0) or
; COMPASS_CHIME_REST, then its frames; 0 frames ends. The periods are
; NotePeriodTable's, written here so that no call goes into the audio code
; PRG1 moves.
COMPASS_CHIME_REST = $00
CompassChimeScript:
    .BYTE $86, 9, COMPASS_CHIME_REST, 3     ; A-flat 5 (NotePeriodTable $44)
    .BYTE $7E, 9, COMPASS_CHIME_REST, 3     ; A5 ($48)
    .BYTE $71, 9, COMPASS_CHIME_REST, 3     ; B5 ($4A)
    .BYTE $54, 45                           ; E6 ($4C)
    .BYTE COMPASS_CHIME_REST, 0

COMPASS_CHIME_REQUEST = $06     ; Two bits: the game only ever requests one.
COMPASS_CHIME_DUTY = $86        ; As the tune player's notes: 50%, decaying.
SQUARE_SILENT = $90             ; Constant volume 0.
SQUARE_LENGTH_HIGH_0 = $08      ; Period high 0, as EmitSquareNote1 writes it.

; In place of LDA Tune1Request at the start of DriveTune1.
;
; Returns to DriveTune1 with A: Tune1Request, flags set from it; or, while
; the chime plays, straight to DriveAudio, skipping DriveTune1.
;
CheckCompassChime:
    LDA Tune1Request
    CMP #COMPASS_CHIME_REQUEST
    BEQ @Start
    ORA #$00
    BNE @Return                 ; Another tune: DriveTune1 plays it.
    LDA Tune1
    CMP #COMPASS_CHIME_REQUEST
    BEQ @Play
    LDA Tune1Request

@Return:
    RTS

@Start:
    ; Play starts with EffectRequest $80, which DriveEffect (after this)
    ; turns into SilenceSample, ending tune 1. Silence first instead.
    LDA EffectRequest
    BPL :+
    JSR SilenceSample
    LDA #$00
    STA EffectRequest
:
    LDA #COMPASS_CHIME_REQUEST
    STA Tune1
    LDA #$00
    STA TunePtr1
    LDA #$01
    STA NoteCounterTune1

@Play:
    ; Return to DriveAudio, not DriveTune1.
    PLA
    PLA
    DEC NoteCounterTune1
    BNE @Exit
    LDY TunePtr1
    LDA CompassChimeScript+1, Y
    BEQ @End
    STA NoteCounterTune1
    LDA CompassChimeScript, Y
    BEQ @Rest
    STA Sq1Timer_4006
    LDA #SQUARE_LENGTH_HIGH_0
    STA Sq1Length_4007
    LDA #$7F
    STA Sq1Sweep_4005
    LDA #COMPASS_CHIME_DUTY
    BNE @SetDuty

@Rest:
    LDA #SQUARE_SILENT

@SetDuty:
    STA Sq1Duty_4004
    INY
    INY
    STY TunePtr1

@Exit:
    RTS

@End:
    ; The channel left as the tune player leaves it at a tune's end (through Y: X is not needed).
    LDY #SQUARE_SILENT
    STY Sq1Duty_4004
    LDY #$18
    STY Sq1Length_4007
    LDY #$00
    STY Tune1
    STY Sq1Timer_4006
    RTS
