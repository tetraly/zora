"""scripts/check_imports.py: zora/ (generation only, what Archipelago ships) imports no sibling package,
and itself only with relative imports."""
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_imports.py"


def _check_imports() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_imports", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_package_imports_no_sibling_and_itself_relatively() -> None:
    check = _check_imports()
    assert check.sibling_imports() == []
    assert check.absolute_imports() == []


def test_a_sibling_import_is_found_inside_a_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check = _check_imports()
    package = tmp_path / "zora"
    package.mkdir()
    (package / "clean.py").write_text("import json\nfrom . import version\nfrom zora.model import enums\n")
    (package / "leak.py").write_text("def f():\n    from zora_measure.checks import run_checks\n"
                                     "    import zora_web.api\n")
    monkeypatch.setattr(check, "REPO", tmp_path)
    assert check.sibling_imports(package) == ["zora/leak.py:2: imports zora_measure.checks",
                                              "zora/leak.py:3: imports zora_web.api"]


def test_an_absolute_zora_import_is_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    check = _check_imports()
    package = tmp_path / "zora" / "rom"
    package.mkdir(parents=True)
    (package / "clean.py").write_text("from ..model.enums import Item\nfrom . import layout\nimport zipfile\n")
    (package / "leak.py").write_text("import zora.model\n\n\ndef f():\n    from zora.flags import codec\n")
    monkeypatch.setattr(check, "REPO", tmp_path)
    assert check.absolute_imports(tmp_path / "zora") == ["zora/rom/leak.py:1: imports zora.model",
                                                         "zora/rom/leak.py:5: imports zora.flags"]
