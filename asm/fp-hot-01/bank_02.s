.SEGMENT "ZORA_FP_HOT_01_PLAY"

; ZORA FP-HOT-01: the Select hot key's mode, in the saved Items block
; (Items+$23, a slot no item uses; 0 in a new file): 0 = Select cycles
; the B item, nonzero = Select pauses. Its five-tile label is kept as a
; transfer record in WRAM (docs/rom-map.md), which the item screen's
; heading pointer names (TransferBufAddrs).
HotKeyMode := Items+$23
HotKeyLabelRecord := $6C7F
HOT_KEY_LABEL_RECORD_SIZE = 9       ; address, count, 5 tiles, terminator

SELECT_BUTTON = $20
CYCLE_FORWARD = $01
NO_SLOT = $0F
SLOT_FOR_NO_SLOT = $07

HotKeyLabelRecords:
    ; Mode 0: ITEMS. Mode nonzero: PAUSE. ZORA's own labels.
    .BYTE $29, $84, $05, $12, $1D, $0E, $16, $1C, $FF
    .BYTE $29, $84, $05, $19, $0A, $1E, $1C, $0E, $FF

; Every play frame, at the Select check: keep the label record current,
; and in the cycling mode select the next occupied B slot. Returns Z set
; (no pause) unless Select was pressed in the pausing mode.
HotKeyFrame:
    LDY #$00
    LDA HotKeyMode
    BEQ :+
    LDY #HOT_KEY_LABEL_RECORD_SIZE
:
    LDX #$00
@CopyLabel:
    LDA HotKeyLabelRecords, Y
    STA HotKeyLabelRecord, X
    INY
    INX
    CPX #HOT_KEY_LABEL_RECORD_SIZE
    BNE @CopyLabel

    LDA ButtonsPressed
    AND #SELECT_BUTTON
    BEQ @Return                 ; No Select: Z set.
    LDA HotKeyMode
    BNE @Pause
    LDY SelectedItemSlot
    CPY #NO_SLOT
    BNE :+
    LDY #SLOT_FOR_NO_SLOT
:
    LDA #CYCLE_FORWARD
    JSR FindItemSlotInBank5
    LDA #$00                    ; Z set: no pause.
    RTS

@Pause:
    LDA #SELECT_BUTTON          ; Z clear: PRG0's pause toggle.

@Return:
    RTS
