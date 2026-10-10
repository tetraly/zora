.SEGMENT "ZORA_FP_PROG_02_ROOM"

; ZORA progressive items (fp-prog-02; docs/progressive-patches.md): the
; room item and the coast item, stored at their line's next level when the
; room loads (bank 1 has the cave wares, bank 4 the Armos item).

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
.EXPORT ResolveProgressiveBodyB5
ResolveProgressiveBodyB5:
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

.EXPORT ResolveProgressiveEndB5
ResolveProgressiveEndB5:

; The operand of CreateRoomObjects' "no item" compare: CMP #$03 is 20 bytes
; into the routine (file 0x1785E), and the serializer writes its operand
; ($03, or $0E with the ZORA remap). The hook reads it there, so it follows
; the remap. (A label inside the routine would end its @ label scope.)
NOTHING_CODE_COMPARE_OFFSET = 20
RoomItemNothingCode := CreateRoomObjects + NOTHING_CODE_COMPARE_OFFSET + 1
.EXPORT RoomItemNothingCodeB5
RoomItemNothingCodeB5 := RoomItemNothingCode

; Called by the room-item hook in CreateRoomObjects (patch.toml), for the
; item store and the trigger-byte load it replaces. A: the room item, Y: RoomId. Returns A: the room's
; LevelBlockAttrsF byte, Y: RoomId. The "no item" code is never swapped: a
; "foes for item" secret would reactivate the object. Keeps X, [00] and
; [01].
StoreRoomItemAtNextLevel:
    CMP RoomItemNothingCode
    BEQ @Store
    TAY
    LDA $01
    PHA
    LDA $00
    PHA
    TYA
    JSR ResolveProgressive
    TAY
    PLA
    STA $00
    PLA
    STA $01
    TYA
    LDY RoomId

@Store:
    STA RoomItemId
    LDA LevelBlockAttrsF, Y
    RTS

; Called by the coast-item hook at @MakeHeartContainerOW (patch.toml), for
; the item store and the Y load it replaces. A: the coast item. Returns A: $C0, the item's Y. Keeps X, [00] and [01].
COAST_ITEM_Y = $C0

StoreCoastItemAtNextLevel:
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
    LDA #COAST_ITEM_Y
    RTS
