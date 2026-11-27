.SEGMENT "ZORA_F2_AP_ITEMS_B4"

; Params:
; A: object type, below $5F
;
; InitObject's last step, moved from the fixed bank with its jump table, which the build copies from
; the player's ROM. InitObject jumps here with bank 4 mapped, as it was when it ran the table itself.
InitObjectFar:
    JSR TableJump
    .INCBIN "zora-moved/init-object-table.bin"

