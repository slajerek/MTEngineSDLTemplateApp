#!/bin/bash
#
# CLI Test Runner for MTEngineSDLTemplateApp
#
# Runs BOTH suites by default -- the CTestSuite integration tests (--run-suite)
# and the imgui_test_engine UI tests (--run-tests) -- and fails if either does.
# Until 2026-08-23 it ran only the first, so the imgui suite executed only when
# somebody drove the binary by hand, which is how a suite goes quiet rather than
# red. Both write tests/results/last_run.txt in the same format.
#
# Usage:
#   tests/run_test.sh [OPTIONS] [TestName]
#
# Options:
#   --suite         Run only the CTestSuite integration tests
#   --imgui         Run only the imgui_test_engine UI tests
#   --skip-build    Skip the build step. REQUIRED off macOS, where this script
#                   does not build: run ./build-linux.sh or .\build-windows.ps1
#                   first and this finds the binary it produced.
#   --package       Run the newest release package under platform/*/prod/
#                   (a FINAL build, ./build-<os>.sh --prod): its own executable,
#                   from its own directory, instead of the development binary
#                   from the git root. An error when there is none -- never a
#                   fallback.
#   --binary PATH   Use this binary instead of building/searching for one.
#                   Seldom needed -- the search below knows where each
#                   platform's build script leaves the binary -- but it is how
#                   you run one built somewhere else. Implies --skip-build, and
#                   with --package it keeps the package's directory while
#                   overriding the executable.
#   --timeout N     Timeout in seconds per suite (default: 120)
#   --log-dir DIR   Log output directory (default: /tmp)
#
# Examples:
#   tests/run_test.sh                        # both suites
#   tests/run_test.sh --suite AppStartup     # one CTestSuite test by name
#   tests/run_test.sh --skip-build           # Linux/Windows, after ./build-<os>.sh
#   tests/run_test.sh --binary ./build/MTEngineSDLTemplateApp

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_BUILD=false
TIMEOUT=120
TEST_NAME=""
LOG_DIR="/tmp"
APP_BINARY=""
RUN_SUITE=true
RUN_IMGUI=true
RUN_PACKAGE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --suite)      RUN_SUITE=true;  RUN_IMGUI=false; shift ;;
        --imgui)      RUN_SUITE=false; RUN_IMGUI=true;  shift ;;
        --skip-build) SKIP_BUILD=true; shift ;;
        --package)    RUN_PACKAGE=true; shift ;;
        --binary)     APP_BINARY="$2"; SKIP_BUILD=true; shift 2 ;;
        --timeout)    TIMEOUT="$2"; shift 2 ;;
        --log-dir)    LOG_DIR="$2"; shift 2 ;;
        -h|--help)    sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            TEST_NAME="$1"; shift ;;
    esac
done

# A named test is a CTestSuite concept; there is no per-test selector on the
# imgui path. Asking for one and silently running the whole other suite as well
# would report a pass nobody asked for.
if [ -n "$TEST_NAME" ]; then
    RUN_IMGUI=false
    RUN_SUITE=true
fi

RESULTS_DIR="$PROJECT_DIR/tests/results"
RESULTS_FILE="$RESULTS_DIR/last_run.txt"
XCODE_PROJECT="$PROJECT_DIR/platform/MacOS/MTEngineSDLTemplateApp.xcodeproj"

# Build and run a single, explicit configuration so we never launch a stale
# binary from the other configuration. `xcodebuild -scheme ...` defaults to
# Debug for the build action, so match that here.
CONFIGURATION="Debug"

mkdir -p "$RESULTS_DIR"

# stat(1) is not portable: GNU/Linux and Git Bash want -c %Y, BSD/macOS -f %m.
# The engine's appbuild-lib.sh carries the same two lines (mt_appbuild_mtime);
# they are repeated rather than sourced because everything except --package
# must keep working with no engine checkout present.
mt_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null; }

# ---------------------------------------------------------------------------
# WHICH BINARY RUNS -- exactly one of these three, in this order:
#
#   1. --binary PATH   the caller named it; nothing else is consulted.
#   2. --package       the PACKAGED executable, from the package
#                      mt_appbuild_prod_binary() finds. --package exists to
#                      verify a FINAL build, so running a development binary
#                      that merely stood inside the package directory would
#                      report a green for code the package does not contain.
#                      It did exactly that until 2026-09-06: the helper answers
#                      "<dir>|<binary>" and only the directory half was read.
#   3. otherwise       the development binary this platform's build script
#                      produced -- built here first, on macOS only.
# ---------------------------------------------------------------------------
PROD_RUN_DIR=""
MTENGINE_DIR="${MTENGINE_DIR:-$PROJECT_DIR/../MTEngineSDL}"

if [ "$RUN_PACKAGE" = true ]; then
    [ -f "$MTENGINE_DIR/tools/appbuild/appbuild-lib.sh" ] \
        || { echo "ERROR: --package needs the engine at $MTENGINE_DIR (appbuild-lib.sh)"; exit 2; }
    . "$MTENGINE_DIR/tools/appbuild/appbuild-lib.sh"
    PROD_HIT="$(mt_appbuild_prod_binary "$PROJECT_DIR" "MTEngineSDLTemplateApp" || true)"
    if [ -z "$PROD_HIT" ]; then
        # AN ERROR, NOT A FALLBACK. Silently running from the root instead
        # would report a green that verified no package at all.
        echo "ERROR: --package given but no release package under platform/*/prod/."
        echo "       Build one first: ./build-<os>.sh --prod"
        exit 2
    fi
    PROD_RUN_DIR="${PROD_HIT%%|*}"
    [ -n "$APP_BINARY" ] || APP_BINARY="${PROD_HIT#*|}"
elif [ "$SKIP_BUILD" = false ]; then
    if [ "$(uname -s)" != "Darwin" ]; then
        echo "ERROR: this runner BUILDS only on macOS (it drives xcodebuild)."
        echo "       On Linux/Windows build with that platform's script first:"
        echo "           ./build-linux.sh    |    .\\build-windows.ps1"
        echo "       then:  tests/run_test.sh --skip-build"
        echo "       which finds the binary that build produced. --binary PATH"
        echo "       still overrides, for one built somewhere else."
        exit 2
    fi
    echo "=== Building MTEngineSDLTemplateApp ($CONFIGURATION) ==="
    # -derivedDataPath build-macos: the same product tree the engine driver
    # pins ./build-macos.sh to. Without it this build landed in the global
    # DerivedData while the search below looks in build-macos/ first, so a
    # build-macos/ binary from an earlier ./build-macos.sh --debug won the
    # search and ran instead of the one just built.
    if ! xcodebuild -project "$XCODE_PROJECT" -scheme MTEngineSDLTemplateApp -configuration "$CONFIGURATION" \
            -derivedDataPath "$PROJECT_DIR/build-macos" -quiet 2>&1; then
        echo "BUILD FAILED"
        exit 2
    fi
    echo "=== Build succeeded ==="
fi

SEARCH_HINT=""
if [ -z "$APP_BINARY" ]; then
    # WHICH CONFIGURATIONS TO SEARCH.
    #
    # When this script BUILT, it built exactly one configuration and must run
    # that one: picking the newest across both could launch a stale binary from
    # a build this script did not do.
    #
    # Under --skip-build there is no "configuration we just built", and pinning
    # Debug is actively wrong: ./build-macos.sh builds RELEASE, so
    # `./build-macos.sh && tests/run_test.sh --skip-build` silently tested a
    # stale Debug binary and reported a pass for code that was never in it.
    # (Found the hard way, 2026-08-24, while adding the HDR bench: the suite
    # reported 3/3 and 8/8 for a binary that contained neither new test.)
    # Search both and take the newest -- there is no configuration to be
    # faithful to, only a most-recent build.
    if [ "$SKIP_BUILD" = true ]; then
        SEARCH_CONFIGS="Debug Release"
    else
        SEARCH_CONFIGS="$CONFIGURATION"
    fi

    # WHERE EACH PLATFORM'S BUILD SCRIPT LEAVES THE DEVELOPMENT BINARY.
    #
    # Until 2026-09-06 this looked in Xcode's DerivedData and nowhere else, so
    # every run without --binary died on Linux and Windows with "no binary
    # found" -- including every script that drives
    # `run_test.sh --skip-build`, such as a run per capability combination. The two new
    # paths are the engine app-build driver's own, not guesses:
    #   Linux    app-build-linux.sh     $APP_DIR/build/$MT_CMAKE_TARGET
    #   Windows  app-build-windows.ps1  $APP_DIR\platform\Windows\bin\<plat>\<cfg>\<exe>
    # Only Windows keys a directory on the configuration, so SEARCH_CONFIGS
    # narrows the search there and on macOS; Linux overwrites one path and has
    # nothing to choose between.
    CANDIDATES=""
    case "$(uname -s)" in
        Darwin)
            # build-macos/ FIRST. The engine driver pins the products there
            # (app-build-macos.sh passes -derivedDataPath "$APP_DIR/build-macos"),
            # so that is where ./build-macos.sh leaves the binary. Without it
            # --skip-build found nothing at all in a fresh checkout, and in an
            # older one silently ran a stale binary from the global DerivedData.
            # The two DerivedData paths stay for IDE builds.
            SEARCH_HINT="build-macos, platform/MacOS/DerivedData, ~/Library/Developer/Xcode/DerivedData ($SEARCH_CONFIGS)"
            for search_path in \
                "$PROJECT_DIR/build-macos" \
                "$PROJECT_DIR/platform/MacOS/DerivedData" \
                "$HOME/Library/Developer/Xcode/DerivedData"; do
                for cfg in $SEARCH_CONFIGS; do
                    CANDIDATES="$CANDIDATES
$(find "$search_path" \
            -name "MTEngineSDLTemplateApp" -type f -perm -111 \
            -path "*/Build/Products/$cfg/*" 2>/dev/null \
            | grep -v "\.dSYM" || true)"
                done
                # The first path with a hit wins outright: the project's own
                # trees before the shared DerivedData, which is consulted only
                # when neither holds one.
                [ -n "$(echo "$CANDIDATES" | grep -v '^$' || true)" ] && break
            done
            ;;
        Linux)
            SEARCH_HINT="build/MTEngineSDLTemplateApp"
            CANDIDATES="$PROJECT_DIR/build/MTEngineSDLTemplateApp"
            ;;
        MINGW* | MSYS* | CYGWIN*)
            SEARCH_HINT="platform/Windows/bin/<x64|ARM64>/{$(echo $SEARCH_CONFIGS | tr ' ' ',')}/MTEngineSDLTemplateApp.exe"
            for cfg in $SEARCH_CONFIGS; do
                for f in "$PROJECT_DIR"/platform/Windows/bin/*/"$cfg"/MTEngineSDLTemplateApp.exe; do
                    CANDIDATES="$CANDIDATES
$f"
                done
            done
            ;;
        *)
            SEARCH_HINT="nowhere -- $(uname -s) is not a platform this runner knows"
            ;;
    esac

    # Newest wins, across everything the platform offered. A heredoc rather
    # than a pipe, so the winner survives the loop: `... | while read` runs the
    # body in a subshell and every assignment in it is discarded.
    BEST=""
    BEST_MTIME=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        [ -f "$f" ] && [ -x "$f" ] || continue
        m="$(mt_mtime "$f")" || continue
        [ -n "$m" ] || continue
        if [ "$m" -gt "$BEST_MTIME" ]; then
            BEST_MTIME="$m"
            BEST="$f"
        fi
    done <<EOF
$CANDIDATES
EOF
    APP_BINARY="$BEST"
fi

if [ -z "$APP_BINARY" ] || [ ! -x "$APP_BINARY" ]; then
    echo "ERROR: no MTEngineSDLTemplateApp binary found. Build first, or pass --binary."
    [ -n "$SEARCH_HINT" ] && echo "       Looked in: $SEARCH_HINT"
    exit 2
fi

echo "=== Using binary: $APP_BINARY ==="
# ---------------------------------------------------------------------------
# WHERE THE BINARY RUNS FROM -- the git root, unless --package.
#
# An MTEngineSDL app finds its assets through the CURRENT WORKING DIRECTORY and
# nothing else; the executable's own location is never consulted. A DEVELOPMENT
# build therefore runs from the git root, which holds assets/ and every payload
# directory as tracked. A FINAL build (./build-<os>.sh --prod) is verified from
# its package with --package, and that is the ONLY time this runner goes near
# platform/*/prod/. Nothing is ever copied into a package to make a test work:
# fixtures are reached through CTest::ResolveProjectPath(), which walks up
# from wherever the binary started, and MT_TEST_PROJECT_DIR below short-cuts
# the walk. The procedure is MTEngineSDL/docs/testing.md.
#
# Until 2026-09-05 this preferred the package whenever one existed and staged
# fixtures into it by copying -- 17 GB for one app -- and left kitchen
# directories inside release packages. Both are gone.
# ---------------------------------------------------------------------------
RUN_DIR="$PROJECT_DIR"
# MT_TEST_RUN_DIR pins the working directory outright. It exists for tests OF
# this runner, which fabricate binaries and results files. PROD_RUN_DIR is the
# package the binary above came out of -- resolved once, up there, because the
# two halves of that answer belong together.
if [ -n "${MT_TEST_RUN_DIR:-}" ]; then
    RUN_DIR="$MT_TEST_RUN_DIR"
    echo "=== Run directory pinned by MT_TEST_RUN_DIR: $RUN_DIR ==="
elif [ -n "$PROD_RUN_DIR" ]; then
    RUN_DIR="$PROD_RUN_DIR"
    echo "=== Running from release package: $RUN_DIR ==="
else
    echo "=== Running from the git root: $RUN_DIR ==="
fi
# The binary must be ABSOLUTE before the cd, or a relative one (notably
# --binary, which is documented as relative to where you stand) resolves
# against the wrong directory the moment we move.
case "$APP_BINARY" in
    /* | [A-Za-z]:[\/]*) ;;
    *) APP_BINARY="$(cd "$(dirname "$APP_BINARY")" && pwd)/$(basename "$APP_BINARY")" ;;
esac

# Where the repository is, for CTest::ResolveProjectPath() -- so a run from
# the package finds tests/ without walking, and a run from the root is exact.
export MT_TEST_PROJECT_DIR="$PROJECT_DIR"

export MT_TEST_RESULTS="$RESULTS_FILE"
mkdir -p "$RESULTS_DIR"
cd "$RUN_DIR"

# ---------------------------------------------------------------------------
# run_one <label> <flag...>
#
# Runs one suite under the watchdog, then parses tests/results/last_run.txt.
# Each suite is run separately and its results file consumed before the next
# starts, because both write the same path.
# ---------------------------------------------------------------------------
run_one() {
    local label="$1"; shift

    rm -f "$RESULTS_FILE"
    echo ""
    echo "=== Running $label ==="

    "$APP_BINARY" --headless --crash-reporter --log-dir "$LOG_DIR" "$@" --exit-after-tests &
    local pid=$!
    local elapsed=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            echo "TIMEOUT: $label did not complete within ${TIMEOUT}s"
            kill -TERM "$pid" 2>/dev/null || true
            sleep 3
            kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            return 3
        fi
    done
    wait "$pid" 2>/dev/null || true

    if [ ! -f "$RESULTS_FILE" ]; then
        echo "ERROR: $label wrote no results file at $RESULTS_FILE"
        echo "       The application may have crashed before writing results."
        return 1
    fi

    echo "--- $label results ---"
    cat "$RESULTS_FILE"

    local result_line
    result_line=$(grep "^RESULT:" "$RESULTS_FILE" || true)
    if [ -z "$result_line" ]; then
        echo "ERROR: no RESULT line in $label results"
        return 1
    fi

    local passed total
    passed=$(echo "$result_line" | sed 's/RESULT: \([0-9]*\)\/.*/\1/')
    total=$(echo  "$result_line" | sed 's/RESULT: [0-9]*\/\([0-9]*\).*/\1/')

    # A zero-test run is a failure, not a pass. That is the shape a suite takes
    # when it silently stops being registered.
    if [ "$passed" = "$total" ] && [ "$total" != "0" ]; then
        echo "$label: PASSED ($passed/$total)"
        SUMMARY="${SUMMARY}${label}: ${passed}/${total} PASS"$'\n'
        return 0
    fi
    echo "$label: FAILED ($passed/$total passed)"
    SUMMARY="${SUMMARY}${label}: ${passed}/${total} FAIL"$'\n'
    return 1
}

SUMMARY=""
STATUS=0

if [ "$RUN_SUITE" = true ]; then
    if [ -n "$TEST_NAME" ]; then
        run_one "CTestSuite[$TEST_NAME]" --run-test "$TEST_NAME" || STATUS=$?
    else
        run_one "CTestSuite" --run-suite || STATUS=$?
    fi
fi

if [ "$RUN_IMGUI" = true ]; then
    # THE UI SUITE NEEDS THE TEST ENGINE COMPILED IN, and a resolved capability
    # set can take it away without anyone asking: MT_CAP_TEST_ENGINE has a
    # commercial `capability-off` effect, so `--tier commercial` builds a binary
    # in which --run-tests registers nothing and never finishes. Before this
    # check that cost a 120-second timeout reported as a FAILURE, which is the
    # wrong answer twice over -- it is not a failure, and it is not a pass
    # either.
    #
    # Asked of the BINARY's symbols, not of a manifest: the manifest is one of
    # four ways MT_CAP_TEST_ENGINE can reach 0, and the binary is the only
    # thing that knows which one this build took. Same question, same method as
    # MTEngineSDL/tools/appbuild/scan-capability-symbols.sh.
    #
    # `grep -c`, NOT `grep -q`, and this script's `set -o pipefail` is why:
    # -q exits the moment it matches, nm gets SIGPIPE writing the rest of a
    # large symbol table, and pipefail reports the PIPELINE as failed even
    # though the match succeeded. Measured here -- the check skipped a build
    # that had the test engine, which is the one answer worse than not
    # checking. -c reads its input to the end, so nm always finishes.
    IMGUI_AVAILABLE=true
    TEST_ENGINE_ANSWERED=false

    if [ -x "$APP_BINARY" ] && command -v nm >/dev/null 2>&1; then
        NM_OUT="$(nm "$APP_BINARY" 2>/dev/null || true)"
        # AN EMPTY TABLE IS "NO ANSWER", NOT "NO TEST ENGINE". A stripped
        # binary lists nothing, and treating that as 0 matches would skip the
        # UI suite on a build that has it -- the one answer worse than not
        # checking. Only a table with something in it is allowed to say no.
        if [ -n "$NM_OUT" ]; then
            TEST_ENGINE_SYMS="$(printf '%s\n' "$NM_OUT" | grep -c 'ImGuiTestEngine_' || true)"
            [ "$TEST_ENGINE_SYMS" -eq 0 ] && IMGUI_AVAILABLE=false
            TEST_ENGINE_ANSWERED=true
        fi
    fi

    # WINDOWS CANNOT ANSWER THE QUESTION ABOVE AT ALL, and before this it was
    # not asked there: Git Bash has no `nm`, so `command -v nm` failed, the
    # probe was skipped whole, IMGUI_AVAILABLE stayed true, and a commercial
    # package spent 120 seconds timing out into a FAILURE -- precisely the
    # outcome the check above exists to prevent, in the one configuration that
    # provokes it. `dumpbin /symbols` is no substitute: on a release .exe it
    # prints a banner and a section summary and no symbols whatsoever.
    #
    # So fall back to what the build RESOLVED, from the LICENSES.txt mtcaps
    # generates: beside the binary in a package, and under $MT_CAPS_OUT for a
    # development build. That file is generated per build by the same resolve
    # that produced the binary, so it describes THIS build -- not the manifest,
    # which someone may have edited since. Still second choice, because it is
    # evidence about the build rather than about the artifact.
    #
    # `tail -1`, not `head -1`: head exits on its first line, grep takes
    # SIGPIPE writing the rest, and this script's `set -o pipefail` reports the
    # pipeline as failed. Same trap the nm probe documents above.
    if [ "$TEST_ENGINE_ANSWERED" = false ]; then
        for CAPS_FILE in "$(dirname "$APP_BINARY")/LICENSES.txt" \
                         "${MT_CAPS_OUT:-}/LICENSES.txt"; do
            [ -f "$CAPS_FILE" ] || continue
            CAPS_VAL="$(grep -o 'MT_CAP_TEST_ENGINE=[01]' "$CAPS_FILE" 2>/dev/null | tail -1 || true)"
            case "$CAPS_VAL" in
                MT_CAP_TEST_ENGINE=0) IMGUI_AVAILABLE=false ;;
                MT_CAP_TEST_ENGINE=1) IMGUI_AVAILABLE=true  ;;
                *) continue ;;
            esac
            TEST_ENGINE_ANSWERED=true
            break
        done
    fi

    if [ "$IMGUI_AVAILABLE" = true ]; then
        run_one "ImGuiTests" --run-tests || STATUS=$?
    else
        # SKIPPED, said out loud. A skip reported as a pass is a lie the
        # headline count repeats.
        SUMMARY="${SUMMARY}ImGuiTests: SKIPPED (this build resolved MT_CAP_TEST_ENGINE=0)"$'\n' 
        echo "ImGuiTests: SKIPPED -- this build resolved MT_CAP_TEST_ENGINE=0, so the UI suite cannot be registered"
    fi
fi

echo ""
echo "=== Summary ==="
printf '%s' "$SUMMARY"
if [ "$STATUS" -eq 0 ]; then
    echo "ALL SUITES PASSED"
else
    echo "FAILED (exit $STATUS)"
fi
exit "$STATUS"
