.SEGMENT "ZORA_FP_FIX_03"

; ZORA FP-FIX-03: clear the VRAM increment bit (PPUCTRL bit 2) in the
; shadow and the register before the level's pattern blocks go to the PPU,
; so a +32 increment left by a vertical tile-buffer record cannot scramble
; them.
TransferLevelPatternBlocksPlus1:
    LDA CurPpuControl_2000
    AND #$FB
    STA CurPpuControl_2000
    STA PpuControl_2000
    JMP TransferLevelPatternBlocks
