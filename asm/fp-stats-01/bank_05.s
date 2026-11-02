.SEGMENT "ZORA_FP_STATS_STAB"

; ZORA FP-STATS-01: count sword stabs. WieldSword jumps here once a swing starts (a sword is
; owned and its slot was idle; held-A repeats return before), then this does the two
; instructions the jump replaced. Not counted once the quest is finished (bank 0's StatsTick).

STATS_BLOCK      = $7F00
StatsFlags       = STATS_BLOCK + $01
DeathWarps       = STATS_BLOCK + $05
Stabs            = STATS_BLOCK + $3A    ; 16 bits
SWORD_EFFECT     = $01
MAX_DEATH_WARPS  = $FF

CountStab:
    BIT StatsFlags
    BMI :+
    INC Stabs
    BNE :+
    INC Stabs+1
:
    LDA #SWORD_EFFECT
    JMP PlayEffect

; Count a death warp: UpdateMenuActive calls this in place of its JSR EndGameMode once the item
; screen's death-warp buttons are down (Up and A on controller 2 in PRG0, or the buttons the
; player setting chose, FP-RESET-01), whatever the player picks after it. Straight to the stats
; block, so Retry and reset keep it, unlike the save file's death counts. Stops at 255.
CountDeathWarp:
    BIT StatsFlags
    BMI :+
    LDA DeathWarps
    CMP #MAX_DEATH_WARPS
    BEQ :+
    INC DeathWarps
:
    JMP EndGameMode                 ; its A = 0 is what UpdateMenuActive stores next
