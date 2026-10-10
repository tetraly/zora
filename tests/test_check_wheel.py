"""scripts/check_wheel.py: a wheel may carry no file the packages it was built from lack,
and must carry zora/ and its sibling packages."""
import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_wheel.py"
SIBLINGS = ["zora_export/__init__.py", "zora_measure/__init__.py", "zora_web/__init__.py", "zora_web/api.py"]


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


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    for name in ["zora/__init__.py", "zora/generate/pipeline.py", *SIBLINGS]:
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text("")
    return source


def test_a_leftover_module_is_refused(tmp_path: Path) -> None:
    source = _source(tmp_path)
    check = _check_wheel()
    clean = _wheel(tmp_path / "clean.whl", ["zora/__init__.py", "zora/generate/pipeline.py", *SIBLINGS,
                                            "zora-0.0.1.dist-info/RECORD"])
    assert check.stray_members(clean, source) == []
    assert check.main([str(clean), str(source)]) == 0
    stale = _wheel(tmp_path / "stale.whl", ["zora/__init__.py", "zora/generate/pipeline.py", *SIBLINGS,
                                            "zora/generate/steps/item_passes.py", "zora_measure/old.py"])
    assert check.stray_members(stale, source) == ["zora/generate/steps/item_passes.py", "zora_measure/old.py"]
    assert check.main([str(stale), str(source)]) == 1


def test_a_missing_sibling_package_is_refused(tmp_path: Path) -> None:
    source = _source(tmp_path)
    check = _check_wheel()
    generator_only = _wheel(tmp_path / "zora-only.whl", ["zora/__init__.py", "zora/generate/pipeline.py"])
    assert check.missing_packages(generator_only) == ["zora_export", "zora_measure", "zora_web"]
    assert check.main([str(generator_only), str(source)]) == 1
