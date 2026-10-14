#!/usr/bin/env bash
# Shared helpers for make-release-{macos,linux}.sh. Source it; it does not run alone.
# The packages themselves are produced by the engine driver (./build-<os>.sh --prod)
# under platform/<P>/prod/<arch>/, with LICENSES.txt beside the app. On macOS the
# driver re-signs only the stripped executable; make-release-macos.sh signs the
# whole bundle after stamping Info.plist. These scripts stamp, sign and zip.

tr_repo_root() { ( cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd ); }

tr_version() {
  sed -n 's/^#define[[:space:]]*TEMPLATEAPP_VERSION[[:space:]]*"\([^"]*\)".*/\1/p' "$1/src/TemplateAppVersion.h"
}

tr_arch() { uname -m; }

# tr_zip <dir-to-zip> <zip-path>: zips the directory's CONTENTS under one top folder.
tr_zip() {
  local src="$1" zip="$2" top
  top="$(basename "${zip%.zip}")"
  local stage; stage="$(mktemp -d)"
  cp -R "$src" "$stage/$top"
  ( cd "$stage" && zip -qry "$zip" "$top" )
  rm -rf "$stage"
}

tr_emit() { echo "zip_path=$1"; [[ -n "${GITHUB_OUTPUT:-}" ]] && echo "zip_path=$1" >> "$GITHUB_OUTPUT"; return 0; }
