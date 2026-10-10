#!/bin/sh
# Build the pure-Python zora wheel into web/dist/ for the Pyodide page.
# Run from the repo root:  sh web/build.sh
#
# The wheel is built from a clean, temporary folder holding only the
# committed packages (pyproject.toml, LICENSE, zora/ and its siblings zora_export/,
# zora_measure/ and zora_web/ at HEAD, by git archive), never
# from the working tree: setuptools' build/ folder keeps old modules, which
# would otherwise ship in the wheel. Uncommitted changes are not in it.
# scripts/check_wheel.py then refuses a wheel with any file the committed
# packages do not have, or without one of them.
set -eu
rm -rf web/dist
# A reproducible wheel: every member dated at HEAD's commit time, not the
# build time, so two builds of the same tree are byte-identical.
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct)}
export SOURCE_DATE_EPOCH
work=temp/wheel-build
rm -rf "$work"
mkdir -p "$work/src"
git -C "$(git rev-parse --show-toplevel)" archive --format=tar HEAD pyproject.toml LICENSE zora zora_export zora_measure zora_web | tar -x -C "$work/src"
python3 -m pip wheel "$work/src" --no-deps --quiet -w web/dist
# The wheel is named after ZORA's version (zora/version.py, the package's version).
wheel=$(basename web/dist/zora-*-py3-none-any.whl)
python3 scripts/check_wheel.py "web/dist/$wheel" "$work/src"
rm -rf "$work"
# The page reads the wheel's name from here (web/zora-web.js).
printf '{"wheel": "%s"}\n' "$wheel" > web/dist/wheel.json
ls "web/dist/$wheel" web/dist/wheel.json
