.SEGMENT "ZORA_FP_PROG_02_ARMOS"

; ZORA progressive items (fp-prog-02; docs/progressive-patches.md): the
; Armos item, stored at its line's next level when an Armos reveals it.

ITEM_ID_LIMIT = $1F                 ; every upgrade-line ID is below $1F
ITEM_WOODEN_BOOMERANG = $1D
BOOMERANG_COUNT = 2                 ; $1D and $1E
DESCRIPTOR_GRADED = $20             ; class 2: swords, candles, arrows, rings
DESCRIPTOR_CLASS_SIZE = $10

; A: item ID. Returns A: the next level of the item's line, with C set; or
; the ID unchanged, with C clear, for an item in no upgrade line. With C
; set, [01] is nonzero when the player already has the line's top level.
; Keeps X; uses Y, [00] and [01]. The same bytes as bank 1's shared body
; (fp-prog-01, where the comments are; a test compares the copies); this
; copy does not read ZORA_B1_ProgressiveItems.
.EXPORT ResolveProgressiveBodyB4
ResolveProgressiveBodyB4:
ResolveProgressive:
    STA $00
    CMP #ITEM_ID_LIMIT
    BCS @NotProgressive
    SBC #ITEM_WOODEN_BOOMERANG-1
    CMP #BOOMERANG_COUNT
    BCC @Boomerang
    LDY $00
    LDA ItemIdToSlot, Y
    STA $01
    LDA ItemIdToDescriptor, Y
    SEC
    SBC #DESCRIPTOR_GRADED
    CMP #DESCRIPTOR_CLASS_SIZE
    BCS @NotProgressive
    EOR #$FF
    SEC
    ADC $00
    LDY $01
    SEC
    ADC Items, Y
    TAY
    LDA #$00
    STA $00
@Fit:
    LDA ItemIdToSlot, Y
    CMP $01
    BEQ @Fits
    DEY
    INC $00
    BNE @Fit
@Fits:
    LDA $00
    STA $01
    TYA
    SEC
    RTS

@Boomerang:
    LDA InvMagicBoomerang
    STA $01
    LDA InvBoomerang
    CLC
    ADC #ITEM_WOODEN_BOOMERANG
    SEC
    RTS

@NotProgressive:
    LDA $00
    CLC
    RTS

.EXPORT ResolveProgressiveEndB4
ResolveProgressiveEndB4:

; Called by the armos-item hook where an Armos reveals its item (patch.toml),
; for the item store and the call it replaces. A: the item. Returns GetRoomFlagUWItemState's result
; for the BNE after the hook. Keeps X, [00] and [01] (the Armos code keeps
; the stairs tile in [00]).
StoreArmosItemAtNextLevel:
    TAY
    LDA $01
    PHA
    LDA $00
    PHA
    TYA
    JSR ResolveProgressive
    STA RoomItemId
    PLA
    STA $00
    PLA
    STA $01
    JMP GetRoomFlagUWItemState
