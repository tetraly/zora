.SEGMENT "ZORA_FP_START_02"

; ZORA FP-START-02 and FP-START-03: a seed's starting items. A new save file, and a slot switched
; to the second quest, take their 40-byte Items block ($0657-$067E) from ZORA_B2_StartItems
; instead of PRG0's three stores (3 hearts and containers, a full partial heart, 8 maximum
; bombs). ZORA writes the table per seed (zora/rom/code_patches.py); the patch is written only
; when it differs from PRG0's start (FP-START-01), so other seeds keep PRG0's code. Each routine
; begins LDY #$27 / LDA ZORA_B2_StartItems, Y, the form zora/rom/parse/features.py reads back.

START_ITEMS_LAST = $27              ; the Items block's last offset ($28 bytes)
; Where each routine goes back to: the instruction after the stores its hook replaces (the
; hooks' 17 and 13 bytes; a label there would end the game's local-label scopes).
NEW_FILE_STORES_END     = $9F4F     ; UpdateModeERegister: TXA, before the ZELDA check
SECOND_QUEST_STORES_END = $AF88     ; SwitchProfileToSecondQuest: LDY CurSaveSlot

; The table as PRG0's routines leave the block (FP-START-01): 3 hearts and containers ($22) at
; HeartValues ($18), HeartPartial ($19) full, MaxBombs ($25) 8, every other byte 0.
.EXPORT ZORA_B2_StartItems
ZORA_B2_StartItems:
    .RES $18, $00
    .BYTE $22, $FF
    .RES $0B, $00
    .BYTE $08
    .RES $02, $00

; UpdateModeERegister, for each new file: the table into file B's Items block ([$C0]). Keeps X
; (the slot); goes back after the stores it replaces.
NewFileStartItems:
    LDY #START_ITEMS_LAST
@Copy:
    LDA ZORA_B2_StartItems, Y
    STA ($C0), Y
    DEY
    BPL @Copy
    JMP NEW_FILE_STORES_END

; SwitchProfileToSecondQuest, after it clears the block: the table into Items.
SecondQuestStartItems:
    LDY #START_ITEMS_LAST
@Copy:
    LDA ZORA_B2_StartItems, Y
    STA Items, Y
    DEY
    BPL @Copy
    JMP SECOND_QUEST_STORES_END
