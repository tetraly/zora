.SEGMENT "ZORA_F2_BOOTS_ENDING"

; The file after the ending (tetraly/zora#4, owner): Start after the credits saves the file with
; its items (FP-SAVE-01); with Pegasus Boots it also holds the L2 boots, so the player can run
; through the seed again. Called in place of the Start path's JSR SilenceAllSound (the statistics
; screen's Start takes the same path), before the save mode stores the profile.
BootsAfterEnding:
    LDA #$01
    STA InvMagicBoomerang
    JMP SilenceAllSound
