.SEGMENT "ZORA_FP_STATS_STAB"

; ZORA FP-STATS-01: count sword stabs. WieldSword jumps here once a swing starts (a sword is
; owned and its slot was idle; held-A repeats return before), then this does the two
; instructions the jump replaced. Not counted once the quest is finished (bank 0's StatsTick).

STATS_BLOCK      = $7F00
StatsFlags       = STATS_BLOCK + $01
Stabs            = STATS_BLOCK + $3A    ; 16 bits
SWORD_EFFECT     = $01

CountStab:
    BIT StatsFlags
    BMI :+
    INC Stabs
    BNE :+
    INC Stabs+1
:
    LDA #SWORD_EFFECT
    JMP PlayEffect
