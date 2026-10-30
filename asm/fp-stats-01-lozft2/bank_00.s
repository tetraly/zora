.SEGMENT "ZORA_FP_STATS_TICK"

; Where StatsTick returns to in this build: the instructions its hook at DriveAudio's end replaces,
; then back to DriveAudio, which goes on to reset the other sound requests.
StatsTickExit:
    LDA #$00
    STA Tune0Request
    RTS
