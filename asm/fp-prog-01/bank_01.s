; ZORA progressive items (fp-prog-01; docs/progressive-patches.md). Each
; sword, candle, arrow, ring or boomerang is shown and given as the next
; level of its line when it appears: here for cave and shop wares, in bank 5
; for the room and coast items and in bank 4 for the Armos item
; (fp-prog-02). TakeItem is unchanged, since the swapped ID is the real
; item. A shop sells each ware marked in ZORA_B1_OneTimeWares only once.

ITEM_ID_LIMIT = $1F                 ; every upgrade-line ID is below $1F
ITEM_WOODEN_BOOMERANG = $1D
BOOMERANG_COUNT = 2                 ; $1D and $1E
DESCRIPTOR_GRADED = $20             ; class 2: swords, candles, arrows, rings
DESCRIPTOR_CLASS_SIZE = $10

CAVE_ITEM_ID_MASK = $3F
CAVE_FLAG_MASK = $C0
CAVE_NO_ITEM = $3F
CAVE_POTION_SHOP = $74              ; the first shop's object type
SHOP_TYPE_COUNT = 7                 ; object types $74-$7A
NOT_A_SHOP = $FF

; Items+$20 to Items+$22 ($0677-$0679): one byte per ware position (0-2),
; one bit per shop (LevelMasks[shop number]), set when a one-time ware is
; bought. Saved with the file, 0 in a new file (docs/progressive-patches.md
; "RAM").
ShopBoughtFlags := Items+$20


.SEGMENT "ZORA_FP_PROG_01_SHOP"

; Per seed. Nonzero: progressive items are on. 0 keeps only the buy-once
; rule for shop wares; fp-prog-02 (the bank 4 and 5 hooks) must then be
; left out, since its copies of ResolveProgressive do not read this byte.
.EXPORT ZORA_B1_ProgressiveItems
ZORA_B1_ProgressiveItems:
    .BYTE $01

; Per seed. The shop wares sold only once, laid out like ShopBoughtFlags:
; one byte per ware position (0-2), one bit per shop (LevelMasks[shop
; number]). Whoever places the wares writes this, from what each holds.
.EXPORT ZORA_B1_OneTimeWares
ZORA_B1_OneTimeWares:
    .BYTE $00, $00, $00

; Shop number by object type - $74: the potion shop, two caves that are
; not shops, then shops A-D.
ShopNumbers:
    .BYTE $00, NOT_A_SHOP, NOT_A_SHOP, $01, $02, $03, $04

; Returns A, Y, [02] and N: this cave's shop number, or $FF (N set) when
; it is not a shop. Keeps X.
FindShopNumber:
    LDA ObjType+1
    SEC
    SBC #CAVE_POTION_SHOP
    TAY
    LDA #NOT_A_SHOP
    CPY #SHOP_TYPE_COUNT
    BCS :+
    LDA ShopNumbers, Y
:
    STA $02
    TAY
    RTS

; Called by the cave-flags hook in InitCaveContinue (patch.toml): store the
; flags, then go over the three wares. In a shop, a ware bought before is hidden (no item,
; price 0). A progressive ware shows its next level, and in a shop is
; hidden when the player has its line's top level. Each ware's top two
; bits are cave flags and stay. Returns A: the cave flags, as the code
; after the hook expects. Keeps X; uses Y and [00] to [03], which the code
; after the hook does not read.
StoreCaveFlagsAndFixUpWares:
    STA CaveFlags
    TXA
    PHA
    JSR FindShopNumber
    LDX #$02

@LoopWare:
    LDY $02
    BMI @Resolve                ; Not a shop.
    LDA LevelMasks, Y           ; This shop's bit
    AND ShopBoughtFlags, X      ; in this ware position's byte.
    BNE @HideWare

@Resolve:
    LDA CaveItemIds, X
    AND #CAVE_ITEM_ID_MASK      ; No item ($3F) is in no line.
    JSR ResolveProgressive
    BCC @NextWare
    STA $03                     ; [03]: the ware's new item ID
    LDY $02
    BMI @SetWare                ; Not a shop: show the next level.
    LDA $01
    BEQ @SetWare                ; Below the top level: show it.

@HideWare:
    LDA #$00
    STA CavePrices, X
    LDA #CAVE_NO_ITEM
    STA $03

@SetWare:
    LDA CaveItemIds, X
    AND #CAVE_FLAG_MASK
    ORA $03
    STA CaveItemIds, X

@NextWare:
    DEX
    BPL @LoopWare
    PLA
    TAX
    LDA CaveFlags
    RTS

; Called by the take-ware hook at @Take (patch.toml), which also makes the
; call it replaces. X: the ware taken.
; Marks a one-time shop ware bought, so every shop of this type leaves it
; out from now on. Keeps X; uses Y and [02], which the code after the hook
; does not read.
TakeWareAndMarkBought:
    JSR SetRoomFlagUWItemState
    JSR FindShopNumber
    BMI @Return
    LDA LevelMasks, Y           ; This shop's bit,
    AND ZORA_B1_OneTimeWares, X ; if this ware is one-time,
    BEQ @Return
    ORA ShopBoughtFlags, X      ; is set in the ware's bought byte.
    STA ShopBoughtFlags, X

@Return:
    RTS


.SEGMENT "ZORA_FP_PROG_01_RESOLVE"

; A: item ID. Returns A: the next level of the item's line, with C set; or
; the ID unchanged, with C clear, for an item in no upgrade line or with
; progressive items off. With C set, [01] is nonzero when the player
; already has the line's top level. Keeps X; uses Y, [00] and [01].
ResolveProgressive:
    LDY ZORA_B1_ProgressiveItems
    BNE ResolveProgressiveBody
    CLC
    RTS

; The shared body: banks 4 and 5 hold the same bytes (fp-prog-02; a test
; compares the three copies). A graded line's IDs are consecutive and the
; ID after its top level is in another slot, so the line's first ID plus
; the level owned is the next level, or past the top: then step back until
; the ID is in the line's slot again, which gives the top level. The level
; owned can be more than one past the top (Add L4 Sword's sword level 4:
; $01 + 4 is the recorder, $05, and one step back would be the bait), and
; the loop always stops, since the line's first ID is in its slot. Every
; upgrade-line ID is below $1F (graded lines $01-$13, boomerangs $1D-$1E);
; $1F-$23 are potions, the clock, a heart and a fairy. Quirk: the red
; potion's descriptor ($22) reads as graded, so the limit keeps the potion
; shop and the take-any cave from showing it as a blue potion.
.EXPORT ResolveProgressiveBodyB1
ResolveProgressiveBodyB1:
ResolveProgressiveBody:
    STA $00                     ; [00]: the item ID
    CMP #ITEM_ID_LIMIT
    BCS @NotProgressive
    SBC #ITEM_WOODEN_BOOMERANG-1    ; carry clear: ID - $1D
    CMP #BOOMERANG_COUNT
    BCC @Boomerang
    LDY $00
    LDA ItemIdToSlot, Y
    STA $01                     ; [01]: the line's item slot
    LDA ItemIdToDescriptor, Y
    SEC
    SBC #DESCRIPTOR_GRADED      ; the level, for a graded item
    CMP #DESCRIPTOR_CLASS_SIZE
    BCS @NotProgressive
    EOR #$FF
    SEC
    ADC $00                     ; ID - level: one before the line's first ID
    LDY $01
    SEC
    ADC Items, Y                ; + 1 + level owned
    TAY
    LDA #$00
    STA $00                     ; [00]: steps taken back
@Fit:
    LDA ItemIdToSlot, Y
    CMP $01                     ; [01]: the line's slot
    BEQ @Fits
    DEY                         ; Past the top level: step back.
    INC $00
    BNE @Fit                    ; always
@Fits:
    LDA $00
    STA $01                     ; Nonzero: the player has the line's top level.
    TYA
    SEC
    RTS

@Boomerang:
    LDA InvMagicBoomerang
    STA $01
    LDA InvBoomerang
    CLC
    ADC #ITEM_WOODEN_BOOMERANG  ; the magical one once the wooden is held
    SEC
    RTS

@NotProgressive:
    LDA $00
    CLC
    RTS

.EXPORT ResolveProgressiveEndB1
ResolveProgressiveEndB1:
