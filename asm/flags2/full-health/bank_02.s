.SEGMENT "ZORA_F2_FULL_HEALTH_LOAD"

; ZORA Start With Full Health (the Zelda Hack Pack's full_health.ips: ShadowOne333, kalita-kun and
; gzip). Runs where the save-file menu has just copied the chosen file's Items block (HeartValues
; and HeartPartial among them) and world flags to the profile: every heart container is full,
; the last one too, then the menu goes on to the next mode.
; HeartValues: the high nibble is the containers less one, the low nibble the full hearts less one.
FullHealthAfterLoad:
    LDA #$FF                    ; the last heart full too
    STA HeartPartial
    LDA HeartValues
    LSR
    LSR
    LSR
    LSR                         ; the containers, as a low nibble
    STA $00
    LDA HeartValues
    AND #$F0
    ORA $00                     ; as many full hearts as containers
    STA HeartValues
    JMP GoToNextMode
