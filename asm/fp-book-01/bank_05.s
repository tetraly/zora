.SEGMENT "ZORA_FP_BOOK_01_MAP"

; ZORA FP-BOOK-01: inside a level, holding the Book of Magic counts as
; holding the level's map. X is the Items slot HasMap or HasCompass asks
; about: the map slots ($11, $13) are odd, the compass slots ($10, $12)
; even. Y is the zero-based level number.
LevelItemOrBookMap:
    TXA
    LSR
    BCC @LevelItem              ; A compass slot: PRG0's test.
    LDA InvBook
    BNE @Return                 ; Nonzero: the map counts as held.

@LevelItem:
    LDA Items, X
    AND LevelMasks, Y           ; The level's bit of the item.

@Return:
    RTS
