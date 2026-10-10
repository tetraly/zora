; ASNB sword-cap (patch.toml): the per-seed operand, the CMP's in the hook at @Fits, 57
; bytes into the shared body; the hook's CMP # is its second instruction, so its operand is 3
; bytes further. asm/asnb/build.py checks that the label lands on that operand.
SWORD_LINE_OPERAND_OFFSET = 57 + 3
ZORA_B4_SwordLineToL4 = ResolveProgressiveBodyB4 + SWORD_LINE_OPERAND_OFFSET
