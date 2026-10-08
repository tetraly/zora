.SEGMENT "ZORA_FP_HOT_01_MENU"

; ZORA FP-HOT-01: the Select hot key's mode, in the saved Items block
; (Items+$23, a slot no item uses; 0 in a new file): 0 = Select cycles
; the B item, nonzero = Select pauses. Its five-tile label is kept as a
; transfer record in WRAM (docs/rom-map.md), which the item screen's
; heading pointer names (TransferBufAddrs).
HotKeyModeInMenu := Items+$23
HotKeyLabelRecordInMenu := $6C7F
HOT_KEY_LABEL_SIZE_IN_MENU = 9       ; address, count, 5 tiles, terminator

INVENTORY_TEXT_SELECTOR = $30       ; TransferBufAddrs entry of the heading

HotKeyLabelRecordsInMenu:
    .BYTE $29, $84, $05, $12, $1D, $0E, $16, $1C, $FF
    .BYTE $29, $84, $05, $19, $0A, $1E, $1C, $0E, $FF

; On the item screen, Select toggles the mode and redraws its label.
DrawSubmenuItemsAndHotKeyToggle:
    JSR DrawSubmenuItems
    LDA ButtonsPressed
    AND #$20
    BEQ @Return
    LDA HotKeyModeInMenu
    EOR #$01
    STA HotKeyModeInMenu
    LDY #$00
    LDA HotKeyModeInMenu
    BEQ :+
    LDY #HOT_KEY_LABEL_SIZE_IN_MENU
:
    LDX #$00
@CopyLabel:
    LDA HotKeyLabelRecordsInMenu, Y
    STA HotKeyLabelRecordInMenu, X
    INY
    INX
    CPX #HOT_KEY_LABEL_SIZE_IN_MENU
    BNE @CopyLabel
    LDA #INVENTORY_TEXT_SELECTOR
    STA TileBufSelector

@Return:
    RTS
