#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_release-common.sh"
ROOT="$(tr_repo_root)"; VERSION="$(tr_version "$ROOT")"; ARCH="$(tr_arch)"
PROD="$ROOT/platform/Linux/prod/$ARCH"
[[ -f "$PROD/LICENSES.txt" ]] || { echo "ERROR: no package in $PROD -- run ./build-linux.sh --prod first" >&2; exit 1; }
SUFFIX=""; ls "$PROD" | grep -q -- '-nc$' && SUFFIX="-nc"
ZIP="$ROOT/releases/MTEngineSDLTemplateApp-$VERSION-linux-$ARCH$SUFFIX.zip"
mkdir -p "$ROOT/releases"; rm -f "$ZIP"
tr_zip "$PROD" "$ZIP"
tr_emit "$ZIP"
