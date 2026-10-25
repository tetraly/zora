.SEGMENT "ZORA_F2_FULL_HEALTH_DEATH"

; ZORA Start With Full Health (the Zelda Hack Pack's full_health.ips: ShadowOne333, kalita-kun and
; gzip). Called by the death menu where PRG0 gives Link three full hearts, with A = HeartValues's
; high nibble (the containers less one): every container is full instead. The code after the call
; fills the partial heart.
FullHealthAfterDeath:
    STA HeartValues
    LSR
    LSR
    LSR
    LSR
    ORA HeartValues             ; as many full hearts as containers
    STA HeartValues
    RTS
