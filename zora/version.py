"""ZORA's version (owner rule, 2026-10-05; version policy 2026-10-06): the same build with the
same non-cosmetic flags and seed makes exactly the same ROM, apart from player settings; output
may change between versions. This number is bumped at each published release, not at each
output change; docs/CHANGELOG.md lists output changes under "Unreleased" until then. The title
screen's version line (FP-TITLE-01), the page, the wheel and the beta show it. ZORA 2.0 beta 1 is
the first public release (ZORA 1.x was the owner's earlier, separate project)."""

import re

ZORA_VERSION = "2.0.1"               # PEP 440: the wheel, the seed document, file names
# The name players see: the title screen, the page, the spoiler log.
PLAYER_NAME = "ZORA"
_PRE_RELEASE = re.compile(r"^(\d+\.\d+)\.(\d+)b(\d+)$")


def player_version(version: str = ZORA_VERSION) -> str:
    """The version as players read it (owner decision, 2026-10-07): a beta "2.0.0b1" is
    "2.0 beta 1"; a final release keeps its number. A beta of a patch release keeps its patch
    digit (2026-11-12): "2.0.1b1" is "2.0.1 beta 1", where ".0" alone is dropped, so every beta
    released before reads as it did. The title screen, the page, the beta's file names, the
    changelog heading and the release's title show this form."""
    beta = _PRE_RELEASE.match(version)
    if not beta:
        return version
    release, patch, number = beta.groups()
    return f"{release}{'' if patch == '0' else '.' + patch} beta {number}"


PLAYER_VERSION = player_version()
