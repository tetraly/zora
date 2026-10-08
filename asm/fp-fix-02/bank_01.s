.SEGMENT "ZORA_FP_FIX_02"

; ZORA FP-FIX-02: the Triforce of Power flash selects its palette buffer
; (Y) only when the dynamic tile buffer is empty ($FF). Otherwise that
; frame's palette change is skipped, and the pending update goes out
; instead of being discarded by TransferCurTileBuf.
SelectFanfarePaletteIfIdle:
    LDA DynTileBuf
    CMP #$FF
    BNE :+
    STY TileBufSelector
:
    RTS
