<!-- template-only:begin -->
# MTEngineSDLTemplateApp

The empty starting point for an [MTEngineSDL](https://github.com/slajerek/MTEngineSDL) app.

    git clone https://github.com/slajerek/MTEngineSDLTemplateApp
    git clone -b devel https://github.com/slajerek/MTEngineSDL   # sibling directory
    cd MTEngineSDLTemplateApp
    ./configure.py MyTool                                        # creates ../MyTool
    cd ../MyTool && ./build-macos.sh

**Check out the engine branch named in `MTENGINE_REF`.** The template is built
against the branch that file names (`origin/devel` means the engine's `devel`),
and it may need engine API that the other branch does not have yet. A plain
`git clone` checks out the engine's default branch, which can be the wrong one.
The build scripts clone the engine at `MTENGINE_REF` only when `../MTEngineSDL`
is missing; they never move an existing checkout. `configure.py` warns when the
checkout is not at `MTENGINE_REF`.

`./configure.py --help` lists the options: window title, settings folder,
bundle id, menu mode (`imgui` or `hybrid`), the engine branch the app's CI
builds against (`MTENGINE_REF`, default `origin/devel`), capabilities, locales,
icon, CI and git. The template itself is never modified; it also builds as-is.

<!-- template-only:end -->
# TemplateApp

An MTEngineSDL application, started from the MTEngineSDL template app: one main
view, workspaces, Settings (theme / renderer / GUI scale), Help, i18n, a smoke
test and CI for macOS, Linux and Windows.

## Prerequisites

- **All:** git, Python 3.9+ (Pillow only to regenerate the icon).
- **macOS:** Xcode and its command-line tools, `nasm` (`brew install nasm`).
- **Linux:** a compiler, CMake, `nasm` and the SDL/GTK development packages;
  `.github/workflows/build-linux.yml` has the full `apt-get` list.
- **Windows:** Visual Studio 2022 or newer with C++, and MSYS2 with `make diffutils
  pkgconf` (the codec builds use it). Run Python as `py`, and allow local
  scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

The first build compiles the engine and its libraries and takes a while; later
builds are incremental.

## Build

    ./build-macos.sh        # macOS
    ./build-linux.sh        # Linux
    .\build-windows.ps1     # Windows (PowerShell)

MTEngineSDL must be checked out next to this repository (`../MTEngineSDL`); the
build scripts clone it if it is missing.

`MTENGINE_REF` names the engine branch this branch builds against, and the two
are paired: `origin/devel` on a `devel` branch, `origin/master` on `master`.
The build scripts clone that branch when the engine is missing but never switch
an existing checkout, so keep `../MTEngineSDL` on the matching branch yourself.
CI runs on `master`, `main` and `devel` and clones the engine at `MTENGINE_REF`.

## Run the tests

    tests/run_test.sh                                # macOS: builds, then runs
    ./build-linux.sh && tests/run_test.sh --skip-build   # Linux (likewise build-windows on Windows)

`tests/run_test.sh` builds only on macOS; on Linux and Windows build with
`./build-<os>.sh` first and pass `--skip-build`. Run it from the repository
root; the app always runs with the repository root as its working directory.

## Install on Linux

`cmake --install` installs the binary, the `.desktop` entry and the icons, but
not `assets/`. The app finds `assets/` through its working directory, so an
installed launcher works only when it starts the app in a directory that holds
`assets/`. This is a known limitation for now.

## Add a source file

    python3 tools/add_source_file.py src/Views/CMyView.cpp

This registers the file in CMake, the Xcode project and the Visual Studio
project. A new `src/` subdirectory must also be added to the include paths.

## Capabilities

`mtengine.caps` lists every engine capability, on or off. Turn one on by
setting it to `1`, together with everything it implies; see
`MTEngineSDL/docs/CAPABILITIES.md`. No project edit is needed. Keep
`MT_COMMERCIAL_BUILD=0`; the commercial tier is chosen by the
`build-*-prod-commercial` scripts.

## App icon

Replace `tools/icons/master.png` (square, at least 1024x1024), run
`python3 tools/icons/gen-icons.py` (needs Pillow), and commit the generated
files.

## Release

Set the version in `src/TemplateAppVersion.h` and push the tag `v<version>`.
The release workflow builds all three platforms and attaches the archives to a
GitHub Release.

## License

MIT, see `LICENSE`. Copyright (c) 2026 Marcin Skoczylas.

<!-- template-only:begin -->
### Manual checks before a template release
- Windows, `kMenuBarMode = Native`: the Win32 menu shows Workspace / Settings / Help / File with working items, and no empty menu strip appears in `ImGui` mode.
- Linux: the ImGui menu bar works with mouse and keyboard.
<!-- template-only:end -->
