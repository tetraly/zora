.SEGMENT "ZORA_FP_HASH_01"

; ZORA FP-HASH-01: four item icons on the file-select screen that identify
; the build. ZORA writes the four item IDs per ROM (a hash of the finished
; ROM, zora/asm_patches.py).
.EXPORT ZORA_B2_CodeIcons
ZORA_B2_CodeIcons:
    .BYTE $00, $00, $00, $00

CODE_ICON_COUNT = 4
CODE_ICON_Y = $27                   ; on the heading row (PPU row 5)
ITEM_DESCRIPTOR_VALUE_MASK = $0F
ITEM_DESCRIPTOR_VALUE_FF = $30

; The icons' X, after the heading's label.
CodeIconXs:
    .BYTE $68, $78, $88, $98

InitMode1_Sub2AndCodeIcons:
    LDA #$14
    STA TileBufSelector
    INC GameSubmode
    LDX #CODE_ICON_COUNT-1

@DrawIcon:
    TXA
    PHA
    LDA CodeIconXs, X
    STA $00
    LDA #CODE_ICON_Y
    STA $01
    ; The sprite pair: rolling index 2X picks OAM offsets $60-$6C (left)
    ; and $B0-$BC (right), which the menu does not use.
    TXA
    ASL
    STA RollingSpriteIndex
    ; As a room item is drawn: the item value from the descriptor in [04]
    ; ($FF for descriptor $30), the item slot in X and Y.
    LDY ZORA_B2_CodeIcons, X
    LDA ItemIdToDescriptor, Y
    CMP #ITEM_DESCRIPTOR_VALUE_FF
    BNE :+
    LDA #$FF
:
    AND #ITEM_DESCRIPTOR_VALUE_MASK
    STA $04
    LDA ItemIdToSlot, Y
    TAX
    TAY
    JSR DrawItemBySlot
    PLA
    TAX
    DEX
    BPL @DrawIcon
    RTS
