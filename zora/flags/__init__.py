"""Flag strings and settings (docs/spec/flags-behavior.md, B11).

The player-facing flag string is one whole number written in base 63 that
holds 27 option fields and 91 three-state fields (FL-ENC-01 to FL-ENC-06).
The package decodes a string into ``Settings`` and encodes ``Settings`` back
into the canonical string (codec), applies the dependency rules (FL-DEP-01
to FL-DEP-05; dependencies), names the four published presets (FL-PRE-01 to
FL-PRE-05; presets) and judges MVP support field by field (FL-SUP-01 to
FL-SUP-04; support). fields holds the fields themselves, form the web
page's flag form, and names.json the owner's names for the fields.

Settings are addressed by the spec's own field labels, ``C01`` to ``C27``
for the option fields and ``B01`` to ``B91`` for the three-state fields.
No UI and no generator wiring live here.
"""
