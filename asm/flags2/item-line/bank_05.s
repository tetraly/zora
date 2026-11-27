.SEGMENT "ZORA_F2_ITEM_LINE_HOP_B5"

; ZORA Show Item Pickups: the hop into bank 6. SwitchBank returns to $BDAE, which is bank 6's
; ZORA_F2_ITEM_LINE_HOP_B6 (JMP ItemLine) once bank 6 is in. ItemLine comes back through SwitchBank to
; ItemLineTail, here at the same $BDAE with bank 5 in again.
ItemLineEnter:
    LDA #$06
    JSR SwitchBank

; What the hook replaced: A and Z from InvRupees, for World_ChangeRupees' BEQ.
ItemLineTail:
    LDA InvRupees
    RTS
