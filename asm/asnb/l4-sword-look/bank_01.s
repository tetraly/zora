.SEGMENT "ZORA_ASNB_LOOK_B1"

MAGICAL_SWORD_VALUE = $03           ; the magical sword's item value (grade), and sword level 3
SWORD_OBJECT_SLOT = $0D             ; the sword's object slot

; Add L4 Sword's look for an item drawn in the world: AnimateItemObject (floor, cave and shop
; items, and the item Link holds up) jumps here in place of DrawItemBySlot, with X and Y the item
; slot (Z set by its TAY for slot 0) and [04] the item value. A magical sword shown while Link's
; sword is level 3 or more is the L4 item: take-l4 gives level 4 for it on every path, and at
; level 4 sword-cap shows it as the line's top. So it is drawn as value 4, level 4's look.
; Everything else goes on unchanged. Both routines run with any of banks 0-6 switched in, so each
; of them holds them at this address (bank_00.s to bank_06.s; a test compares the copies).
LookSwordInWorld:
    BNE @Draw                   ; not the sword slot
    LDA $04
    CMP #MAGICAL_SWORD_VALUE
    BNE @Draw
    LDA Items                   ; InvSword
    CMP #MAGICAL_SWORD_VALUE
    BCC @Draw
    INC $04                     ; value 4: level 4's look
@Draw:
    JMP DrawItemBySlot

; Add L4 Sword's look for the swing: UpdateSwordOrRod's @CalcSwordAttrs calls this with A the
; base attribute (its low bits 0) and X the sword's object slot, $0D. Returns A ORed with the row
; for the sword level (SwordLookRows: level 4 takes row 1, the white sword's), X $0D again.
SwingRowWithL4:
    LDX Items                   ; InvSword: level 1-4
    ORA SwordLookRows-1, X
    LDX #SWORD_OBJECT_SLOT
    RTS
