.SEGMENT "ZORA_FP_LEVEL_02"

; ZORA FP-LEVEL-02: the level label ("LEVEL-1" at the top of the status
; bar) with room for 8 tiles: a word of up to 6 characters, the dash and
; the level number, or 7 characters and the number. PRG0's record
; (LevelNumberTransferBuf, 11 bytes in bank 6's common data block, copied
; to RAM $681C at power-on) holds at most 7 tiles: the column directory
; follows it in RAM, and the copy's bounds are fixed. So the label is
; drawn from this record instead: the PPU address ($2042, status bar row
; 2, column 2), the tile count, up to 8 tiles (the last one the number's
; placeholder), $FF. The level word setting writes the word, the dash and
; the count here (zora/rom/player_settings.py `level_word`), always with
; the patch: its own record is a placeholder, the number alone.
;
; DrawLevelLabel, from InitMode3_Sub7 (in place of the number store and
; the cue of selector $0C), copies the record into the dynamic tile
; buffer, which the next NMI transfers (selector 0 is already cued: the
; previous submode's transfer reset it), stores the level number in the
; record's last tile and ends the submode. It also copies the record's
; first 11 bytes over PRG0's RAM record, so fp-stats-01's level rows,
; which read the word there (tile count at $681E, tiles from $681F), show
; the same word.
LEVEL_LABEL_RECORD_SIZE = 12
LEVEL_LABEL_RAM_COPY = 11           ; PRG0's record: address, count, 8 tiles; its terminator does not fit

.EXPORT ZORA_B5_LevelLabelRecord
ZORA_B5_LevelLabelRecord:
    .BYTE $20, $42, $01             ; PPU $2042 (status bar row 2, column 2), 1 tile
    .BYTE $00                       ; the level number's place
    .RES LEVEL_LABEL_RECORD_SIZE - 4, $FF   ; end of transfer; padding

; Params:
; LevelInfo_LevelNumber: the level number, 1-9 (InitMode3_Sub7 skips 0)
;
DrawLevelLabel:
    LDY #LEVEL_LABEL_RECORD_SIZE-1
:
    LDA ZORA_B5_LevelLabelRecord, Y
    STA DynTileBuf, Y
    CPY #LEVEL_LABEL_RAM_COPY
    BCS :+                          ; the terminator stays out of the RAM record
    STA LevelNumberTransferBuf, Y
:
    DEY
    BPL :--
    LDX DynTileBuf+2                ; the tile count: the number is the last tile
    LDA LevelInfo_LevelNumber
    STA DynTileBuf+2, X             ; tile (count - 1), at offset 3 + count - 1
    LDA #$FF
    STA DynTileBuf+3, X             ; end of transfer, at offset 3 + count
    INX
    INX
    INX
    STX DynTileBufLen               ; the next record would go after the label
    JMP L1701A_Exit                 ; next submode
