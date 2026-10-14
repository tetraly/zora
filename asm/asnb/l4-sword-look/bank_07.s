.SEGMENT "ZORA_ASNB_LOOK_B7"

; Add L4 Sword's look, by sword level - 1 (levels 1-4). The swing reads SwordLookRows-1 by the
; level, the A box and items both tables by level - 1. Levels 1-3 are PRG0's: rows 0, 1 and 2,
; and the magical sword's icon (item slot $20) at level 3. Level 4: that icon in row 1, the white
; sword's colors.
SwordLookRows:
    .BYTE $00, $01, $02, $01
SwordLookIcons:
    .BYTE $00, $00, $20, $20
