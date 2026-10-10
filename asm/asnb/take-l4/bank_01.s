.SEGMENT "ZORA_ASNB_TAKE_B1"

ITEM_SLOT_SWORD = $00
MAGICAL_SWORD_GRADE = $03           ; the magical sword's grade, and sword level 3
L4_SWORD_LEVEL = $04

; ASNB (docs/design/asnb.md 3a): level 4 from any pickup. Called by TakeItem's graded store
; (HandleClass2) in place of its LDA $0A / CMP Items, Y; the BCC and STA Items, Y follow. Y: the
; item slot, [0A]: the grade taken. Returns A: the grade to store, with the flags of its compare
; with Items, Y. A grade-3 sword (the magical sword) taken at sword level 3 gives level 4, on
; every path that ends in TakeItem: caves, shops, dungeon rooms and cellars, the coast, the
; Armos and dropped items. Keeps X and Y. TakeItem runs from work RAM with any of banks 0-6
; switched in, so each of them holds this routine at this address (bank_00.s to bank_06.s; a
; test compares the copies).
TakeGradeWithL4:
    LDA $0A
    CPY #ITEM_SLOT_SWORD
    BNE @Compare
    CMP #MAGICAL_SWORD_GRADE
    BNE @Compare
    CMP Items                   ; InvSword: taken at sword level 3
    BNE @Compare
    LDA #L4_SWORD_LEVEL
@Compare:
    CMP Items, Y
    RTS
