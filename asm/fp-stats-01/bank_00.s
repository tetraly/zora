.SEGMENT "ZORA_FP_STATS_TICK"

; ZORA FP-STATS-01 (player setting "Statistics screen"): the clock and the stamps. StatsTick runs
; once per NMI in place of the JSR DriveAudio in IsrNmi, with bank 0 switched in, and ends by
; jumping to DriveAudio, so the audio call is unchanged. Every store goes to the stats block in
; battery-backed SRAM at $7F00 (docs/rom-map.md "RAM"), which PRG0 never reads or writes (of that
; page it writes only $7FFF). The page is z1rr-coop's: by owner ruling the screen and co-op are
; incompatible for now, and a co-op ROM has the Statistics screen Off.

STATS_BLOCK      = $7F00
StatsMagic       = STATS_BLOCK + $00
StatsFlags       = STATS_BLOCK + $01    ; bit 7: the quest was finished, the clock is frozen
TotalSeconds     = STATS_BLOCK + $02    ; 16 bits, from the file's registration
SubFrame         = STATS_BLOCK + $04    ; frames toward the next second
TenthPhase       = STATS_BLOCK + $05    ; 0-9: the tenth second of ten takes one frame more
AreaSeconds      = STATS_BLOCK + $06    ; 16 bits each: the overworld, levels 1-9 (CurLevel)
LevelStamps      = STATS_BLOCK + $1A    ; 16 bits each, levels 1-9: TotalSeconds at completion
ItemStamps       = STATS_BLOCK + $2C    ; 16 bits each: TotalSeconds when the key item was held
BombsUsed        = STATS_BLOCK + $3A    ; 16 bits
PrevBombs        = STATS_BLOCK + $3C    ; InvBombs last frame
StatsScreenState = STATS_BLOCK + $3D    ; the screen's state (bank 2); 0 outside the win mode
STATS_SIZE       = $40
STATS_MAGIC      = $A5
STATS_FINISHED   = $80

LEVEL_STAMP_OFFSET = LevelStamps - STATS_BLOCK
ITEM_STAMP_OFFSET  = ItemStamps - STATS_BLOCK
LEVEL_9_STAMP      = LevelStamps + 2 * 8

MODE_LOAD_FIRST    = $02                ; modes $02-$0C and $10-$12 run the clock
MODE_PLAY          = $05                ; from play on (not during loads) stamps and bombs count
MODE_SAVE          = $0D
MODE_CELLAR        = $10
MODE_WIN           = $13
AREAS              = 10                 ; the overworld and levels 1-9
TRIFORCE_LEVELS    = 8
ITEM_STAMPS        = 6

; 601 frames per 10 seconds (NTSC runs at 60.0988 frames a second): 60 frames a second, the
; tenth second 61.
FRAMES_PER_SECOND  = 60
LONG_SECOND_PHASE  = 9
PHASES             = 10

; The key items, in the screen's order: the slot (from Items) and the value at which the item is
; held. Any sword; ladder; bracelet; raft; recorder; silver arrows.
StampItemSlots:
    .BYTE $00, $0C, $0E, $09, $05, $02
StampItemThresholds:
    .BYTE $01, $01, $01, $01, $01, $02

StatsTick:
    LDA StatsMagic
    CMP #STATS_MAGIC
    BEQ @Initialized
    JSR ClearStatsBlock
    JMP DriveAudio

@Initialized:
    LDA GameMode
    CMP #MODE_WIN
    BEQ @Win
    ; Outside the win mode the screen is never shown (a reset during it leaves the state set).
    LDA #$00
    STA StatsScreenState
    LDA GameMode
    CMP #MODE_LOAD_FIRST
    BCC @NotCounted
    CMP #MODE_SAVE
    BCC @Counted
    CMP #MODE_CELLAR
    BCS @Counted

@NotCounted:
    ; Menus, the demo, saving and registering: a newly loaded file's bombs are never counted.
    JSR RememberBombs
    JMP DriveAudio

@Win:
    ; The first frame of the win mode completes level 9 and freezes the clock.
    BIT StatsFlags
    BMI @Done
    LDY #LEVEL_9_STAMP - STATS_BLOCK
    JSR StampIfUnset
    LDA StatsFlags
    ORA #STATS_FINISHED
    STA StatsFlags
    JMP DriveAudio

@Counted:
    BIT StatsFlags
    BMI @Done
    JSR TickClock
    LDA GameMode
    CMP #MODE_PLAY
    BCS :+
    JSR RememberBombs               ; the file is still loading
    JMP DriveAudio
:
    JSR StampLevels
    JSR StampItems
    JSR CountBombs

@Done:
    JMP DriveAudio

ClearStatsBlock:
    LDA #$00
    LDY #STATS_SIZE - 1
:
    STA STATS_BLOCK, Y
    DEY
    BPL :-
    LDA #STATS_MAGIC
    STA StatsMagic

RememberBombs:
    LDA InvBombs
    STA PrevBombs
    RTS

TickClock:
    LDX #FRAMES_PER_SECOND
    LDA TenthPhase
    CMP #LONG_SECOND_PHASE
    BNE :+
    INX
:
    INC SubFrame
    CPX SubFrame
    BEQ :+
    BCS @Exit                       ; not a second yet
:
    LDA #$00
    STA SubFrame
    LDX TenthPhase
    INX
    CPX #PHASES
    BCC :+
    LDX #$00
:
    STX TenthPhase
    INC TotalSeconds
    BNE :+
    INC TotalSeconds+1
:
    LDA CurLevel
    CMP #AREAS
    BCS @Exit
    ASL
    TAX
    INC AreaSeconds, X
    BNE @Exit
    INC AreaSeconds+1, X

@Exit:
    RTS

; Store TotalSeconds in the stamp at STATS_BLOCK+Y unless it is set already (a stamp is never
; overwritten); 0 means "not yet", so a stamp in the first second is 1. Keeps X.
StampIfUnset:
    LDA STATS_BLOCK, Y
    ORA STATS_BLOCK+1, Y
    BNE @Exit
    LDA TotalSeconds
    STA STATS_BLOCK, Y
    LDA TotalSeconds+1
    STA STATS_BLOCK+1, Y
    ORA STATS_BLOCK, Y
    BNE @Exit
    LDA #$01
    STA STATS_BLOCK, Y

@Exit:
    RTS

; Levels 1-8 by InvTriforce's bits.
StampLevels:
    LDA InvTriforce
    LDX #$00
@Level:
    LSR
    BCC @Next
    PHA
    TXA
    ASL
    ADC #LEVEL_STAMP_OFFSET         ; carry is clear after the ASL (X < 8)
    TAY
    JSR StampIfUnset
    PLA
@Next:
    INX
    CPX #TRIFORCE_LEVELS
    BCC @Level
    RTS

StampItems:
    LDX #ITEM_STAMPS - 1
@Item:
    LDY StampItemSlots, X
    LDA Items, Y
    CMP StampItemThresholds, X
    BCC @Next
    TXA
    ASL
    ADC #ITEM_STAMP_OFFSET          ; carry is clear after the ASL (X < 6)
    TAY
    JSR StampIfUnset
@Next:
    DEX
    BPL @Item
    RTS

; Bombs used: the drops in InvBombs. Buying, finding and the upgrade only raise it.
CountBombs:
    LDA InvBombs
    CMP PrevBombs
    BCS @Remember
    LDA PrevBombs
    SEC
    SBC InvBombs
    CLC
    ADC BombsUsed
    STA BombsUsed
    BCC @Remember
    INC BombsUsed+1
@Remember:
    JMP RememberBombs
