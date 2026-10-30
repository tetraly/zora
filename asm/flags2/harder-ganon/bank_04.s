.SEGMENT "ZORA_F2_HARDER_GANON"

; ZORA Harder Ganon (docs/zora-extras.md section 21), from Z1M1 (MetalMachine; asm 843932c,
; src/zelda/patches.asm:1962-2074, tables/fireball_rooms.asm). Ganon's fight is
; Ganon_ScenePhase2; Ganon_CheckCollisions runs in it every frame. Levels 1 to 3 index the
; tables below by GanonLevel, the byte a seed writes (zora/rom/harder_bosses.py).

GanonLevel:
    .BYTE $01

; Index 0 is never read: the level is 1 to 3.
GanonStunShifts:                ; the random byte's right shifts: $38 + random/16, $30 + /8, $20 + /4
    .BYTE $00, $04, $03, $02
GanonStunBase:
    .BYTE $00, $38, $30, $20
GanonJumpChance:                ; per 256, checked every 16 frames: 1/8, 1/4, 3/8
    .BYTE $00, $20, $40, $60
GanonRoomChance:                ; the Ganon room's statues, per 256: PRG0's rooms use $F0
    .BYTE $00, $50, $A0, $F0

; UpdateStatues' tables (PRG0's at $8634-$864F), with layout $28 (the Ganon room) as the third room
; and pattern: four flames at the four-statue room's spots (pattern 0's), and the old man's flames
; as the fourth pattern.
GanonStatueRooms:
    .BYTE $24, $23, $28
GanonStatueCounts:
    .BYTE $03, $01, $03, $01
GanonStatueBase:
    .BYTE $00, $04, $06, $0A
; Y before X: laid out as in the original game they would make an 8-byte run of its data (release scan).
GanonStatueYs:
    .BYTE $C0, $BC, $64, $5C, $94, $8C, $C0, $BC, $64, $5C, $82, $86
GanonStatueXs:
    .BYTE $24, $C8, $24, $C8, $64, $88, $24, $C8, $24, $C8, $48, $A8

; UpdateStatues' room id (GetUniqueRoomId), except that a room holding Ganon answers $28, the Ganon room's
; layout, which the statue code then shoots from: Z1M1 does this only in the layout itself, and ZORA's
; dungeons often put Ganon in another one. Keeps X.
GanonRoomId:
    JSR GetUniqueRoomId
    PHA
    TXA
    PHA
    LDX #$0B                    ; the monster slots, 11 down to 1
@Scan:
    LDA ObjType, X
    CMP #$3E                    ; Ganon
    BEQ @Found
    DEX
    BNE @Scan
    PLA
    TAX
    PLA                         ; the layout id as it was
    RTS
@Found:
    PLA
    TAX
    PLA
    LDA #$28
    RTS

; UpdateStatues' chance test, X the fireball's index, [0B] the pattern. PRG0: a random byte
; below $F0. Returns the flags of that compare.
GanonStatueChance:
    LDY $0B
    CPY #$02
    BNE @Usual                  ; the four-statue and two-statue rooms and the old man: $F0
    LDY GanonLevel
    LDA Random, X
    CMP GanonRoomChance, Y
    RTS
@Usual:
    LDA Random, X
    CMP #$F0
    RTS

; Ganon_ScenePhase2's call, X Ganon's slot: heal him a little every 32 frames while he is hurt, then
; run the collision check it replaced. A Ganon at 0 hit points (Set Gannon HP to 0, B41) is not healed:
; he would climb back to a real fight.
GanonRegenerates:
    LDA FrameCounter
    AND #$1F
    BNE @Check
    LDA ObjHP, X
    BEQ @Check                  ; Set Gannon HP to 0 (B41): a Ganon with none stays at none
    CMP #$E0
    BCS @Check
    ADC GanonLevel              ; the carry is clear
    STA ObjHP, X
@Check:
    JMP Ganon_CheckCollisions

; Replaces LDA #$40 / STA ObjTimer,X after a sword hit: the visible, unhurt time is a random value
; with PRG0's average. The last right shift's carry goes into the sum, as in Z1M1.
GanonVisibleTime:
    TYA
    PHA
    LDY GanonLevel
    LDA GanonStunShifts, Y
    TAY
    LDA Random, X
@Shift:
    LSR
    DEY
    BNE @Shift
    LDY GanonLevel
    ADC GanonStunBase, Y
    STA ObjTimer, X
    PLA
    TAY
    RTS

; Replaces the silver-arrow test at the start of @CheckArrowCollision (LDA InvArrow / CMP #$02),
; which it still ends with, so the caller's branch sees the same flags. Ganon is brown here. Every 16
; frames, with GanonLevel / 8 chance, he jumps to X $30-$B0 and Y $65-$A5.
GanonMayJump:
    LDA FrameCounter
    AND #$0F
    BNE @Test
    TYA
    PHA
    LDY GanonLevel
    LDA Random, X
    CMP GanonJumpChance, Y
    PLA
    TAY
    BCS @Test
    LDA Random + 2
    LSR
    ADC #$30
    STA ObjX, X
    LDA Random + 3
    LSR
    LSR
    ADC #$65
    STA ObjY, X
@Test:
    LDA InvArrow
    CMP #$02
    RTS
