"""The release gate's low-risk changes (scripts/full_tier.py low_risk_reason): Markdown, the version string, and
the page's hero graphic while it is a PNG of at most HERO_GRAPHIC_LIMIT bytes (owner decision, 2026-10-30)."""
import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)


@pytest.fixture(scope="module")
def full_tier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("full_tier", REPO / "scripts" / "full_tier.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit(repo: Path, files: dict[str, bytes | None]) -> str:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                              env=environment).stdout.strip()
    for name, data in files.items():
        path = repo / name
        if data is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git("add", "-A")
    git("-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "change")
    return git("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_the_hero_graphic_is_low_risk_while_a_small_png(full_tier: ModuleType, repo: Path) -> None:
    stamped = commit(repo, {full_tier.HERO_GRAPHIC: PNG, "README.md": b"x"})
    logo = commit(repo, {full_tier.HERO_GRAPHIC: PNG + b"the artist's logo"})
    assert full_tier.low_risk_reason(repo, full_tier.HERO_GRAPHIC, stamped, logo) == "the hero graphic"
    too_big = commit(repo, {full_tier.HERO_GRAPHIC: PNG + bytes(full_tier.HERO_GRAPHIC_LIMIT)})
    assert full_tier.low_risk_reason(repo, full_tier.HERO_GRAPHIC, stamped, too_big) is None
    not_png = commit(repo, {full_tier.HERO_GRAPHIC: b"GIF89a"})
    assert full_tier.low_risk_reason(repo, full_tier.HERO_GRAPHIC, stamped, not_png) is None
    removed = commit(repo, {full_tier.HERO_GRAPHIC: None})
    assert full_tier.low_risk_reason(repo, full_tier.HERO_GRAPHIC, stamped, removed) is None


def test_other_site_files_are_not_low_risk(full_tier: ModuleType, repo: Path) -> None:
    stamped = commit(repo, {"web/zora.css": b"a {}", "web/other.png": PNG})
    changed = commit(repo, {"web/zora.css": b"b {}", "web/other.png": PNG + b"!"})
    assert full_tier.low_risk_reason(repo, "web/zora.css", stamped, changed) is None
    assert full_tier.low_risk_reason(repo, "web/other.png", stamped, changed) is None
    assert full_tier.low_risk_reason(repo, "README.md", stamped, changed) == "Markdown"
