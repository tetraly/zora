"""The oldest Python ZORA's Archipelago world must run on: 3.11, the oldest Archipelago supports
(docs/releasing.md "Python versions"). mypy checks zora/ and its siblings for 3.11
(pyproject.toml), but never the world's own files (archipelago/, which import Archipelago's
modules); and a newer interpreter accepts syntax 3.11 refuses (PEP 695's `type` and generics,
3.12's f-strings). So a real 3.11 compiles every file the .apworld ships and imports every zora/
module, and the floor is the same wherever pyproject.toml names it."""
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FLOOR = (3, 11)
FLOOR_PYTHON = Path.home() / ".pyenv/versions/3.11.16/bin/python"
SHIPPED_FOLDERS = ("zora", "archipelago")      # the .apworld's Python (scripts/build_apworld.py)
COMPILE_ALL = """
import sys
failed = []
for path in sys.stdin.read().splitlines():
    try:
        compile(open(path, encoding="utf-8").read(), path, "exec", dont_inherit=True)
    except SyntaxError as error:
        failed.append(f"{path}:{error.lineno}: {error.msg}")
print("\\n".join(failed))
"""
IMPORT_ALL = """
import importlib, pkgutil, sys
sys.path.insert(0, sys.argv[1])
import zora
failed = []
for module in pkgutil.walk_packages(zora.__path__, "zora."):
    try:
        importlib.import_module(module.name)
    except Exception as error:
        failed.append(f"{module.name}: {type(error).__name__}: {error}")
print("\\n".join(failed))
"""


def floor_python() -> Path:
    if not FLOOR_PYTHON.exists():
        pytest.skip(f"Python {FLOOR_PYTHON.parent.parent.name} missing")
    return FLOOR_PYTHON


def shipped_files() -> list[Path]:
    return sorted(path for folder in SHIPPED_FOLDERS for path in (REPO / folder).rglob("*.py"))


def test_pyproject_names_one_floor() -> None:
    """requires-python, mypy's python_version and ruff's target-version all say 3.11."""
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    floor = ".".join(map(str, FLOOR))
    assert pyproject["project"]["requires-python"] == f">={floor}"
    assert pyproject["tool"]["mypy"]["python_version"] == floor
    assert pyproject["tool"]["ruff"]["target-version"] == "py" + floor.replace(".", "")


def test_every_shipped_file_compiles_on_the_floor() -> None:
    files = shipped_files()
    assert len(files) > 100
    done = subprocess.run([str(floor_python()), "-I", "-c", COMPILE_ALL], input="\n".join(map(str, files)),
                          capture_output=True, text=True, check=True)
    assert done.stdout.strip() == ""


def test_every_zora_module_imports_on_the_floor() -> None:
    """Catches a standard-library name 3.11 lacks imported by name (from typing import override, from
    itertools import batched, ...); mypy, which checks zora/ for 3.11, catches the attribute uses."""
    done = subprocess.run([str(floor_python()), "-I", "-c", IMPORT_ALL, str(REPO)], capture_output=True, text=True,
                          check=True, cwd=REPO)
    assert done.stdout.strip() == ""


def test_this_interpreter_is_not_below_the_floor() -> None:
    assert sys.version_info[:2] >= FLOOR
