.SEGMENT "ZORA_F2_L4_TAKE_FIXED"

; ZORA 2.0 Add L4 Sword. Called by TryTakeItem when the room item is taken, in place of its
; call to SetRoomFlagUWItemState; keeps X (the room item's slot). In a dungeon, where bank 1
; is switched in at this point, first let RaiseSwordToL4 raise the sword; then mark the item
; taken as PRG0 does.
TakeRoomItemForL4Sword:
    LDY CurLevel
    BEQ :+                      ; The overworld: another bank may be in.
    JSR RaiseSwordToL4
:
    JMP SetRoomFlagUWItemState
