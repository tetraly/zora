"""Where the corpora are: one folder per flag string, <base>/<name>/final, under one base folder,
the ZORA_CORPORA setting. It is read from the environment, else from the checkout's git-ignored
verify.env (a relative path there is read from the repo root); without either it is a corpora/
folder in the checkout, and the corpus tests skip when it is missing. The MVP baseline's corpus
(CP-5) is "clean": clean/final, with its shapes-stage snapshots in clean/shapes-stage and playtest
output in clean/zora-playtest.

Every script, test and checkpoint finds a corpus through corpus(); none names the base itself.
"""
import os
from pathlib import Path

CORPORA_VARIABLE = "ZORA_CORPORA"
REPO = Path(__file__).resolve().parent.parent
SETTINGS_FILE = REPO / "verify.env"
DEFAULT_CORPORA = REPO / "corpora"
CLEAN = "clean"
FINAL = "final"
SHAPES_STAGE = "shapes-stage"


def local_setting(name: str) -> str | None:
    """A VAR=value line of verify.env, or None."""
    if not SETTINGS_FILE.exists():
        return None
    for line in SETTINGS_FILE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and not key.startswith("#") and key.strip() == name:
            return value.strip().strip("\"'")
    return None


def corpora() -> Path:
    """The base folder: ZORA_CORPORA from the environment, else from verify.env, else DEFAULT_CORPORA."""
    value = os.environ.get(CORPORA_VARIABLE) or local_setting(CORPORA_VARIABLE)
    return REPO / value if value else DEFAULT_CORPORA


def corpus(name: str, stage: str = FINAL) -> Path:
    """One corpus's ROM folder: corpus("hopla") is <base>/hopla/final."""
    return corpora() / name / stage
