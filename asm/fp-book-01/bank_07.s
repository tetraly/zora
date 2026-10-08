.SEGMENT "ZORA_FP_BOOK_01_TAKE"

; ZORA FP-BOOK-01: SetItemValue's store; taking the Book of Magic (item
; type $11, in X) also requests the status-bar map redraw, as taking a
; map does. SetItemValue runs from RAM with any bank in, so this lives in
; the fixed bank.
ITEM_TYPE_BOOK = $11

SetItemValueAndBookMap:
    STA Items, Y
    CPX #ITEM_TYPE_BOOK
    BNE :+
    STX StatusBarMapTrigger     ; Nonzero: redraw the map.
:
    RTS
