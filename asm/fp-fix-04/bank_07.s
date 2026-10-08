.SEGMENT "ZORA_FP_FIX_04"

; ZORA FP-FIX-04: taking the Triforce of Power requests the "item appears"
; tune ($02, as PRG0), and at once stores $02 in LastBossDefeated, which
; opens a last-boss room's shutters, and increments ObjType slot 0, which
; Ganon's ashes no longer do. TakeItem runs from RAM with any bank in, so
; this lives in the fixed bank. A (the item ID) is kept.
TUNE_ITEM_APPEARS = $02

TakePowerTriforceSignals:
    LDX #TUNE_ITEM_APPEARS
    STX Tune1Request
    STX LastBossDefeated
    INC ObjType
    RTS
