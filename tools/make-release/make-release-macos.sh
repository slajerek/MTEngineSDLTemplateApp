#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_release-common.sh"
ROOT="$(tr_repo_root)"; VERSION="$(tr_version "$ROOT")"; ARCH="$(tr_arch)"
PROD="$ROOT/platform/MacOS/prod/$ARCH"
APP="$(find "$PROD" -maxdepth 1 -name 'MTEngineSDLTemplateApp*.app' | head -1)"
[[ -d "$APP" ]] || { echo "ERROR: no .app in $PROD -- run ./build-macos.sh --prod first" >&2; exit 1; }
SUFFIX=""; [[ "$(basename "$APP")" == *-nc.app ]] && SUFFIX="-nc"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST"
# Editing Info.plist breaks the driver's ad-hoc signature: sign again.
codesign --force --deep -s - "$APP" && codesign --verify "$APP"
ZIP="$ROOT/releases/MTEngineSDLTemplateApp-$VERSION-macos-$ARCH$SUFFIX.zip"
mkdir -p "$ROOT/releases"; rm -f "$ZIP"
tr_zip "$PROD" "$ZIP"
tr_emit "$ZIP"
