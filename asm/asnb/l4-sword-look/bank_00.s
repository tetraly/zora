.SEGMENT "ZORA_ASNB_LOOK_B0"

MAGICAL_SWORD_VALUE = $03
SWORD_OBJECT_SLOT = $0D

; Add L4 Sword's look: bank 1's routines (bank_01.s, where the comments are), the same
; bytes at the same address, for AnimateItemObject running with this bank switched in.
LookSwordInWorld:
    BNE @Draw
    LDA $04
    CMP #MAGICAL_SWORD_VALUE
    BNE @Draw
    LDA Items
    CMP #MAGICAL_SWORD_VALUE
    BCC @Draw
    INC $04
@Draw:
    JMP DrawItemBySlot

; bank 1's SwingRowWithL4, the same bytes at the same address.
SwingRowWithL4:
    LDX Items
    ORA SwordLookRows-1, X
    LDX #SWORD_OBJECT_SLOT
    RTS
