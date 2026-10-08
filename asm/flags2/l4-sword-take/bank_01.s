.SEGMENT "ZORA_F2_L4_TAKE"

ITEM_MAGICAL_SWORD = $03            ; also the magical sword's level (InvSword 3)

; ZORA 2.0 Add L4 Sword. [04]: the room item taken. The magical sword taken at sword level 3
; (Progressive Items shows a sword room item at Link's next level, so this is the top of the
; line) raises him to level 4. Any other item, or any other level, changes nothing. Keeps X.
RaiseSwordToL4:
    LDA Items                   ; InvSword
    CMP #ITEM_MAGICAL_SWORD
    BNE :+
    CMP $04
    BNE :+
    INC Items
:
    RTS
