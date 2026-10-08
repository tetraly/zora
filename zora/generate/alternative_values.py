"""Which alternative values a generation produces (flags-behavior.md FL-ALT-02
to FL-ALT-04; owner ruling 2026-10-05: supported after the MVP).

One field per value, named after the function that produces it; each
function has one call site in generation_pass.py, which tests its field.
The defaults are the MVP baseline values: no alternative value, today's
output.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AlternativeValues:
    start_with_four_hearts: bool = False                 # C16 at 3, FL-ALT-02
    change_sword_hearts_from_five_hearts: bool = False   # C20 at 1, FL-ALT-03
    generate_community_hint_text: bool = False           # C03 at 2, FL-ALT-04


# Every field at its MVP baseline value: the default where none are given.
MVP_VALUES = AlternativeValues()
