"""scripts/clean_copy.py run refuses a copy another session built: a build that stopped because its folder
was taken must not let the run after it verify that other session's tree against the wrong parent."""
from pathlib import Path

import pytest

# scripts/clean_copy.py is this repo's tooling, not released, so a release tree skips these
clean_copy = pytest.importorskip("scripts.clean_copy", reason="scripts/clean_copy.py is not released")


def copy_of(tmp_path: Path, session: str) -> Path:
    tree = tmp_path / "x-copy"
    tree.mkdir()
    (tree / clean_copy.SETTINGS_FILE).write_text(
        f"{clean_copy.COPY_REVISION_SETTING}=7f39e1eaf6e7\n{clean_copy.COPY_SESSION_SETTING}={session}\n",
        encoding="utf-8")
    return tree


def test_run_refuses_a_copy_another_session_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clean_copy.SESSION_ID_SETTING, "mine")
    with pytest.raises(clean_copy.CopyError, match="another session"):
        clean_copy.run(copy_of(tmp_path, "theirs"), ["true"])


def test_run_takes_its_own_copy_and_a_foreign_one_on_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(clean_copy.SESSION_ID_SETTING, "mine")
    assert clean_copy.run(copy_of(tmp_path, "mine"), ["true"]) == 0
    (tmp_path / "x-copy" / clean_copy.SETTINGS_FILE).write_text(
        f"{clean_copy.COPY_SESSION_SETTING}=theirs\n", encoding="utf-8")
    assert clean_copy.run(tmp_path / "x-copy", ["true"], foreign=True) == 0
