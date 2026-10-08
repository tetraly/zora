#!/bin/sh
# Build the wheel and copy the static page into one directory, ready to
# serve or publish (the GitHub Pages workflow uses it; so can a local
# server outside a protected folder). Run from the repo root:
#   sh web/stage.sh OUT_DIR
set -eu
out=${1:?usage: sh web/stage.sh OUT_DIR}
sh web/build.sh
rm -rf "$out"
mkdir -p "$out/dist"
cp web/index.html web/zora-web.js web/zora-worker.js web/widgets.js "$out/"
cp web/flag-tabs.json "$out/"
cp web/fonts.css web/zora.css "$out/"
mkdir -p "$out/fonts"
cp web/fonts/*.woff2 web/fonts/OFL.txt "$out/fonts/"
cp web/dist/zora-*-py3-none-any.whl web/dist/wheel.json "$out/dist/"
# Never publish a ROM: the page reads the user's own file locally.
if find "$out" -iname '*.nes' | grep -q .; then
  echo "refusing: a .nes file is in $out" >&2
  exit 1
fi
ls -R "$out"
