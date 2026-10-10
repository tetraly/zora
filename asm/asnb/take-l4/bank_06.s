.SEGMENT "ZORA_ASNB_TAKE_B6"

ITEM_SLOT_SWORD = $00
MAGICAL_SWORD_GRADE = $03
L4_SWORD_LEVEL = $04

; ASNB: bank 1's TakeGradeWithL4 (bank_01.s, where the comments are), the same bytes at the
; same address, for TakeItem running with this bank switched in.
TakeGradeWithL4:
    LDA $0A
    CPY #ITEM_SLOT_SWORD
    BNE @Compare
    CMP #MAGICAL_SWORD_GRADE
    BNE @Compare
    CMP Items
    BNE @Compare
    LDA #L4_SWORD_LEVEL
@Compare:
    CMP Items, Y
    RTS
