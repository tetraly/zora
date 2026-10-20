.SEGMENT "ZORA_SET_MUSIC_OFF_STATS"

; ZORA music off (FP-SET-04) on the statistics screen (FP-STATS-01): the screen
; silences the ending's song only when this mark holds SILENCE_SONG (Tune0
; request $80); with music on the byte is free space's $FF and the song plays
; on (owner decision, 2026-10-19). asm/fp-stats-01/bank_02.s's MUSIC_OFF_MARK
; names the same address.
SILENCE_SONG = $80

MusicOffMark:
    .BYTE SILENCE_SONG
