.SEGMENT "ZORA_FP_FIX_06"

; ZORA FP-FIX-06: the overworld maze check, skipped while a whirlwind
; carries Link. The trip runs the next-room calculation for a rightward
; move from the screen left of the entrance; on the mountain maze screen
; ($1B) PRG0's check would keep Link there.
CheckMazesUnlessWhirlwind:
    LDA WhirlwindTeleportingState
    CMP #$01
    BEQ :+
    JMP CheckMazes
:
    RTS
