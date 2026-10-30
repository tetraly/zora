.SEGMENT "ZORA_SET_QUARTER_SPEED_BEEP"

; ZORA quarter-speed low-health beep (a player setting, FP-BEEP-01's fourth choice): the heart
; warning plays a quarter as often. Half speed's routine (asm/settings/half-speed-beep/) with a
; longer wait: each beep is followed by three times as many silent frames as it lasts, so one
; starts every 4 x 19 = 76 frames. As there, the request's operand is untouched, nothing requests
; the beep when it is removed or under Hidden Health (FP-HIDE-01), and the wait counts in
; TunePtr0, from WAIT_START up to the wrap to 0: TuneScripts0 is 110 bytes, so every tune script
; ends below WAIT_START ($C7).
HEART_WARNING_END = 28              ; TunePtr0 just after the heart warning's closing 0 (TuneScripts0 + 27)
BEEP_FRAMES = 19                    ; one beep, the frame it ends in included (measured in the emulator)
WAIT_START = $100 - 3 * BEEP_FRAMES

; In place of DriveTune0's LDX Tune0, which it reaches only for a request of the heart warning
; alone. Returns Z set to start the beep (DriveTune0's BEQ @ChangeTune), Z clear to go on as PRG0
; does when channel 0 is busy (it plays on, or with nothing playing, returns).
HeartWarningAtQuarterSpeed:
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
