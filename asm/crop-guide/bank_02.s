.SEGMENT "ZORA_CROP_GUIDE"

; ZORA's crop guide on the file-select screen: a white square in each of the screen's four corner
; cells and a blue one a cell in diagonally from each. A player crops overscan until the white
; squares are just gone and the blue ones still show.
;
; The file-select screen is drawn on a nametable cleared to blank tiles with every attribute 0
; (TurnOffVideoAndClearArtifacts), and its layout (Mode1TileTransferBuf) sets no corner attribute, so
; all eight cells take background palette row 0 of MenuPalettesTransferBuf: $0F $30 $00 $12.
CROP_GUIDE_WHITE = $25              ; CommonBackgroundPatterns: solid color 1 ($30, white)
CROP_GUIDE_BLUE = $27               ; CommonBackgroundPatterns: solid color 3 ($12, blue)
ONE_TILE = $01                      ; a transfer record's length byte: one tile, across
; The death-count records end at this offset with $FF; the guide's records start there instead.
DEATH_COUNTS_END = $12

; Transfer records (PPU address high, low, length, tile), then the end marker.
CropGuideRecords:
    .BYTE $20, $00, ONE_TILE, CROP_GUIDE_WHITE      ; row 0, column 0
    .BYTE $20, $1F, ONE_TILE, CROP_GUIDE_WHITE      ; row 0, column 31
    .BYTE $23, $A0, ONE_TILE, CROP_GUIDE_WHITE      ; row 29, column 0
    .BYTE $23, $BF, ONE_TILE, CROP_GUIDE_WHITE      ; row 29, column 31
    .BYTE $20, $21, ONE_TILE, CROP_GUIDE_BLUE       ; row 1, column 1
    .BYTE $20, $3E, ONE_TILE, CROP_GUIDE_BLUE       ; row 1, column 30
    .BYTE $23, $81, ONE_TILE, CROP_GUIDE_BLUE       ; row 28, column 1
    .BYTE $23, $9E, ONE_TILE, CROP_GUIDE_BLUE       ; row 28, column 30
    .BYTE $FF
CROP_GUIDE_LENGTH = * - CropGuideRecords

; Called once InitMode1_Sub6 has copied the death-count records: the guide's go over their end marker,
; 51 bytes in all, within the dynamic transfer buffer's $3D. The draw then writes each slot's count
; into the first three records as before.
;
; With TileBufSelector 0 the NMI turns the screen on before it transfers the dynamic buffer, so the
; transfer must end inside vertical blank. Eleven records come close: by a rough count about 125
; cycles each, about 2,100 of its 2,273 with the NMI's work before them. (The emulator draws it either
; way.) TransferBufAddrs' entry $1A is the same buffer, and any selector but 0 leaves the screen as it
; is, off since InitMode1_Full's TurnOffAllVideo: the transfer has all the time it needs, and the
; screen comes on a frame later, with the next transfer.
DYNAMIC_BUFFER_SCREEN_OFF = $1A
CopyCropGuide:
    ; The two instructions the hook replaced: the first save slot. (First: the code after the hook
    ; reads none of A, Y or the flags.)
    LDA #$00
    STA $0A
    LDA #DYNAMIC_BUFFER_SCREEN_OFF
    STA TileBufSelector
    LDY #CROP_GUIDE_LENGTH-1
@CopyGuide:
    LDA CropGuideRecords, Y
    STA DynTileBuf+DEATH_COUNTS_END, Y
    DEY
    BPL @CopyGuide
    RTS
