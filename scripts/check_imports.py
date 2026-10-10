"""zora/'s import rules (Archipelago Phase 1; docs/packaging.md "Packages"). Run from the repo root:

    python3 scripts/check_imports.py

zora/ holds generation only: it is what Archipelago copies in (as worlds.zora.zora, possibly
from a zip), without the sibling packages zora_export/, zora_measure/ and zora_web/. So:
1. no module under zora/ imports a sibling;
2. no module under zora/ imports zora absolutely (`from zora.x import y`, `import zora.x`):
   copied in under another name there is no top-level zora, so zora/ imports itself with
   relative imports (`from ..x import y`). Tests, scripts and the web keep absolute imports.
Every import (inside functions too) is read from the syntax tree, not matched as text.
Exit 1 on any finding; scripts/verify.sh runs it.
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "zora"
SIBLINGS = ("zora_export", "zora_measure", "zora_web")


def imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, module) for each absolute import in the tree; relative imports stay inside zora/."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
    return found


def _imports_of(package: Path, top_levels: tuple[str, ...]) -> list[str]:
    """Each absolute import under package of a module in top_levels, as "path:line: imports module"."""
    findings = []
    for path in sorted(package.rglob("*.py")):
        for line, module in imported_modules(ast.parse(path.read_text(), str(path))):
            if module.split(".")[0] in top_levels:
                findings.append(f"{path.relative_to(REPO).as_posix()}:{line}: imports {module}")
    return findings


def sibling_imports(package: Path = PACKAGE) -> list[str]:
    """Rule 1: each import of a sibling package under package."""
    return _imports_of(package, SIBLINGS)


def absolute_imports(package: Path = PACKAGE) -> list[str]:
    """Rule 2: each absolute import of zora itself under package."""
    return _imports_of(package, ("zora",))


def main() -> int:
    findings = ([f"{finding} (zora/ must not import {', '.join(SIBLINGS)})" for finding in sibling_imports()]
                + [f"{finding} (inside zora/, import zora relatively)" for finding in absolute_imports()])
    for finding in findings:
        print(f"check_imports: {finding}", file=sys.stderr)
    if findings:
        return 1
    print(f"check_imports: zora/ imports none of {', '.join(SIBLINGS)}, and itself only relatively")
    return 0


if __name__ == "__main__":
    sys.exit(main())
