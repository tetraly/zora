.SEGMENT "ZORA_SET_MUSIC_OFF"

; ZORA music off (a player setting, FP-SET-04): the three looping area songs
; are never started. Every place PRG0 starts one (game start, entering or
; leaving a level or the overworld, after a cave, after the item fanfare,
; level 9's song after the Triforce of Power fanfare) goes through
; SongRequest with LevelSongIds' value, and DriveSong is the only code that
; starts a song, so filtering the request here covers them all. Every other
; song request (title, ending, fanfares) passes unchanged; the jingles,
; effects, samples and tune channel 0 do not use SongRequest.
OVERWORLD_SONG = $01
UNDERWORLD_SONG = $40               ; levels 1 to 8
LEVEL_9_SONG = $20

; Returns the song request in A, with N and Z set by it as LDA SongRequest
; set them; 0 in place of an area song.
SongRequestUnlessAreaSong:
    LDA SongRequest
    CMP #OVERWORLD_SONG
    BEQ @AreaSong
    CMP #UNDERWORLD_SONG
    BEQ @AreaSong
    CMP #LEVEL_9_SONG
    BEQ @AreaSong
    ORA #$00                        ; N and Z from the request.
    RTS

@AreaSong:
    ; PRG0 would replace the song playing (an event song: no area song
    ; ever plays) with the area song: stop it instead and stay silent.
    LDA Song
    BEQ :+
    JSR SilenceSong
:
    LDA #$00                        ; Z set: no song change.
    RTS
