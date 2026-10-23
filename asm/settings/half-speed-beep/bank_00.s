.SEGMENT "ZORA_SET_HALF_SPEED_BEEP"

; ZORA half-speed low-health beep (a player setting, FP-BEEP-01's third choice; the idea is
; Z2Randomizer's, docs/credits.md): the heart warning plays half as often. The game requests it
; every frame while Link has no full heart left, and DriveTune0 starts it whenever tune channel 0
; is idle, so a beep starts the frame after the last one ends. Here each beep is followed by as
; many silent frames as it lasts. The beep's request operand (FP-BEEP-01, bank 7) is untouched:
; with the beep removed, or under Hidden Health (FP-HIDE-01), nothing requests it and this never runs.
;
; No RAM of its own: while channel 0 is idle, PRG0 never reads TunePtr0 (DriveTune0 sets it when
; a tune starts), so the wait counts there, from WAIT_START up to the wrap to 0. Every tune script
; ends below WAIT_START, so a pointer at or above it is always this wait.
HEART_WARNING_END = 28              ; TunePtr0 just after the heart warning's closing 0 (TuneScripts0 + 27)
BEEP_FRAMES = 19                    ; one beep, the frame it ends in included (measured in the emulator)
WAIT_START = $100 - BEEP_FRAMES

; In place of DriveTune0's LDX Tune0, which it reaches only for a request of the heart warning
; alone. Returns Z set to start the beep (DriveTune0's BEQ @ChangeTune), Z clear to go on as PRG0
; does when channel 0 is busy (it plays on, or with nothing playing, returns).
HeartWarningAtHalfSpeed:
    LDX Tune0
    BNE @Done                       ; A tune is playing: Z clear, as PRG0.
    LDX TunePtr0
    CPX #HEART_WARNING_END
    BEQ @BeginWait                  ; A beep has just ended.
    CPX #WAIT_START
    BCC @Start                      ; No wait (another tune ended, or none has played yet).
    INC TunePtr0                    ; Z set on the wrap to 0: the wait is over.
@Done:
    RTS

@BeginWait:
    LDX #WAIT_START                 ; Z clear: this frame is the wait's first.
    STX TunePtr0
    RTS

@Start:
    LDX #$00                        ; Z set.
    RTS
