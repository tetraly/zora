.SEGMENT "ZORA_FP_HOT_01_PLAY"

; ZORA FP-HOT-01, swap-only choice (a player setting, FP-SET-01): the
; toggle choice held in its item-cycling mode, without the mode, its label
; or the item-screen toggle. Select never pauses, and nothing is saved.

SELECT_BUTTON = $20
CYCLE_FORWARD = $01
NO_SLOT = $0F
SLOT_FOR_NO_SLOT = $07

; Every play frame, at the Select check: on a new Select press, select the
; next occupied B slot. Always returns Z set: PRG0's pause toggle never runs.
HotKeyFrame:
    LDA ButtonsPressed
    AND #SELECT_BUTTON
    BEQ @Return                 ; No Select: Z set.
    LDY SelectedItemSlot
    CPY #NO_SLOT
    BNE :+
    LDY #SLOT_FOR_NO_SLOT
:
    LDA #CYCLE_FORWARD
    JSR FindItemSlotInBank5
    LDA #$00                    ; Z set: no pause.

@Return:
    RTS
