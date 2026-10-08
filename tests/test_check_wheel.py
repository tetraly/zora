"""scripts/check_wheel.py: a wheel may carry no file the package it was built from lacks."""
import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_wheel.py"


def _check_wheel() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_wheel", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel(path: Path, members: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in members:
            archive.writestr(name, "")
    return path


def test_a_leftover_module_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "src"
    (source / "zora" / "generate").mkdir(parents=True)
    (source / "zora" / "__init__.py").write_text("")
    (source / "zora" / "generate" / "pipeline.py").write_text("")
    check = _check_wheel()
    clean = _wheel(tmp_path / "clean.whl", ["zora/__init__.py", "zora/generate/pipeline.py",
                                            "zora-0.0.1.dist-info/RECORD"])
    assert check.stray_members(clean, source) == []
    assert check.main([str(clean), str(source)]) == 0
    stale = _wheel(tmp_path / "stale.whl", ["zora/__init__.py", "zora/generate/pipeline.py",
                                            "zora/generate/steps/item_passes.py"])
    assert check.stray_members(stale, source) == ["zora/generate/steps/item_passes.py"]
    assert check.main([str(stale), str(source)]) == 1
