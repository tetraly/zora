.SEGMENT "ZORA_FP_HOT_01_BANK5"

; ZORA FP-HOT-01: call FindAndSelectOccupiedItemSlot (bank 5) from the
; play update, which runs with bank 2 in, and switch bank 2 back.
; A: direction, Y: starting slot.
FindItemSlotInBank5:
    PHA
    LDA #$05
    JSR SwitchBank
    PLA
    JSR FindAndSelectOccupiedItemSlot
    LDA #$02
    JMP SwitchBank
