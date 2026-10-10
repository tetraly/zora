.SEGMENT "ZORA_FP_ROAR_01"

; ZORA FP-ROAR-01: the status-bar label above the hearts (9 tiles at PPU
; $2076) names a boss-sound room. CheckBossSoundEffectUW sets the flag on
; each room entry; FormatStatusBarText appends the label record at every
; status-bar text build. The flag lives in WRAM ZORA chose (docs/rom-map.md).
BossSoundLabelFlag := $6C7E
STATUS_BAR_TEMPLATE_END = $28       ; the template's terminator in DynTileBuf
LABEL_RECORD_SIZE = 13              ; address, count, 9 tiles, terminator

RequestBossSoundAndLabel:
    STA SampleRequest
    LDA #$01
    STA BossSoundLabelFlag
    RTS

SilenceBossSoundAndLabel:
    LDA #$00
    STA BossSoundLabelFlag
    LDA #$80                    ; Stop the boss sound.
    JMP PlayEffect

; FormatStatusBarText's last step, then the label record. FormatStatusBarText
; runs from RAM; both its callers (UpdateHeartsAndRupees, InitMode7) have
; bank 5 in.
FormatBombCountAndRoomLabel:
    JSR FormatDecimalCountByteInTextBuf
    LDY #$00                    ; The usual label,
    LDA CurLevel
    BEQ @Copy
    LDA BossSoundLabelFlag
    BEQ @Copy
    LDY #LABEL_RECORD_SIZE      ; or, in a boss-sound room, the second.
@Copy:
    LDX #$00
:
    LDA RoomLabelRecords, Y
    STA DynTileBuf+STATUS_BAR_TEMPLATE_END, X
    INY
    INX
    CPX #LABEL_RECORD_SIZE
    BNE :-
    RTS

RoomLabelRecords:
    ; PRG0's word with dash tiles $2F, padded with blanks.
    .BYTE $20, $76, $09, $24, $2F, $15, $12, $0F, $0E, $2F, $24, $24, $FF
    ; ZORA's own: the usual label's layout with a four-letter word, ROAR by default; the player
    ; setting writes another word into ZORA_B5_BossSoundWord (zora/rom/player_settings.py).
    .BYTE $20, $76, $09, $24, $2F
.EXPORT ZORA_B5_BossSoundWord
ZORA_B5_BossSoundWord:
    .BYTE $1B, $18, $0A, $1B
    .BYTE $2F, $24, $24, $FF
