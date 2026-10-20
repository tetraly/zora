.SEGMENT "ZORA_F2_RING_COLOR"

; ZORA Archipelago ring colors: called each frame of play from BeginUpdateWorld (bank 7) in place
; of its clock check. When Link's tunic color in his save slot's menu palette row differs from
; the color table's entry for his ring, it repaints him as HandleClass2 does for a ring picked
; up: the menu row, the level palette's Link color, and a cue for the level palettes' transfer.
; A transfer already queued (TileBufSelector not 0) waits: the check runs again next frame.
TRANSFER_LEVEL_PALETTES = $18           ; TileBufSelector: LevelInfo_PalettesTransferBuf
LINK_COLOR_IN_ROW = 20                  ; MenuPalettesTransferBuf: Link's color, row 4 byte 1
CLOCK_INVINCIBILITY = $10               ; BeginUpdateWorld's own step

RingColorAndClock:
    LDX CurSaveSlot
    LDY SaveSlotToPaletteRowOffset, X
    LDX InvRing
    LDA LinkColors_CommonCode, X
    CMP MenuPalettesTransferBuf+LINK_COLOR_IN_ROW, Y
    BEQ @Clock
    LDX TileBufSelector
    BNE @Clock
    LDX #TRANSFER_LEVEL_PALETTES
    STX TileBufSelector
    STA MenuPalettesTransferBuf+LINK_COLOR_IN_ROW, Y
    STA LevelInfo_PalettesTransferBuf+LINK_COLOR_IN_ROW
@Clock:
    ; What the hook replaced: with the clock, Link's invincibility timer gains CLOCK_INVINCIBILITY.
    LDA InvClock
    BEQ @Done
    LDA #CLOCK_INVINCIBILITY
    CLC
    ADC ObjInvincibilityTimer
    STA ObjInvincibilityTimer
@Done:
    RTS
