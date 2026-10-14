<#
.SYNOPSIS
    FINAL build, COMMERCIAL tier -- the one that may actually be sold or shipped.
.DESCRIPTION
    Wrapper over build-windows.ps1. -Tier commercial is the whole of it, but
    that one switch moves several things at once and this script exists to
    record them in the place someone will look.

    WHAT -Tier commercial SETS. MT_COMMERCIAL_BUILD=1 and MT_PRIVATE_BUILD=0,
    together -- the two are mutually exclusive halves of one question, and an
    artifact is either sold or never distributed. Setting both is a
    configure-time error naming both keys.

    "FULL" MEANS "EVERYTHING A COMMERCIAL LICENCE PERMITS", WHICH IS LESS THAN
    EVERYTHING. MT_COMMERCIAL_BUILD is not a whole-capability veto; per
    capability it either does nothing, turns an effect off, or is refused
    outright. Two consequences worth knowing before you read the summary and
    wonder what happened:

      * NONFREE IS FORCED OFF, and this script deliberately does NOT try to set
        it. The vocabulary marks MT_CAP_OPENCV_NONFREE `commercial: capability-
        off` -- "a commercial build must not carry a patented algorithm" -- so
        resolve turns it off BEFORE the fragments, LICENSES.txt and the out_dir
        hash are written. THE SYMBOL GATE IS NOT PART OF THIS BUILD, and an
        earlier version of this comment said it was: no app-build driver on any
        platform invokes scan-capability-symbols. Run it by
        hand as
          MTEngineSDL\tools\appbuild\scan-capability-symbols.ps1 <binary> $env:MT_CAPS_OUT
        The resolver is what keeps SURF out; the gate is how you PROVE it, and
        proving it is a separate step someone has to take. Measured: resolving this manifest with
        --set MT_COMMERCIAL_BUILD=1 --set MT_CAP_OPENCV_NONFREE=1 returns
        MT_CAP_OPENCV_NONFREE=0 and exit code 0 -- SILENTLY OVERRULED, not
        refused, so asking for it here would look like it worked. If you need
        SURF, it takes a private-tier build (MT_PRIVATE_BUILD=1, every
        capability on), and that package may never be distributed.
      * MT_CAP_TEST_ENGINE GOES OFF TOO, for the same class of reason: a shipped
        build carries no imgui test engine. So `tests/run_test.sh --package`
        against this tier runs the CTestSuite half only and reports
        "ImGuiTests: SKIPPED (this build resolved MT_CAP_TEST_ENGINE=0)" -- the
        runner detects the missing symbols and says so rather than passing
        silently. That is correct, not a regression; exercise the UI suite on
        the development build instead.
      * DISTRIBUTION-RESTRICTED DEPENDENCIES ARE DROPPED, because they ride on
        MT_PRIVATE_BUILD=1 and this tier sets it to 0. FFmpeg is additionally
        rebuilt in `commercial` mode, and the driver's licence gate REFUSES to
        link an app of this tier against an FFmpeg install marked otherwise --
        so the first run here rebuilds FFmpeg and takes a while.

    Anything the deny-list still catches is a hard error naming the key, not a
    warning: a commercial resolve that would enable a dependency marked
    commercial_safe:false stops the build.

    SYMBOLS ARE OFF AND CANNOT BE TURNED ON. -Prod defaults MT_RELEASE_SYMBOLS
    to 0, and the driver REFUSES -Symbols on together with -Tier commercial: a
    store build never ships symbols. The PDB is still kept, outside the package,
    under $MT_OUT\symbols.
.PARAMETER Jobs
    Caps build parallelism (MT_BUILD_JOBS). Leave unset for every core. Set it
    on a machine with little RAM per core: an out-of-memory kill during a
    build reports as a failure with no diagnostic.
#>
param(
    # NO DEFAULT ON PURPOSE. Unset means "this machine": the parameter is only
    # forwarded when you give one, and the engine's Resolve-MTPlatform then
    # auto-detects. Hardcoding x64 here would silently cross-build on an ARM64
    # host, and re-detecting the host in this script would duplicate the
    # engine's own answer -- which is the thing build-systems.md warns about,
    # since PROCESSOR_ARCHITECTURE describes the PROCESS, not the machine.
    [ValidateSet('x64','ARM64')]
    [string]$Platform,
    [ValidateSet('Debug','Release')]
    [string]$Configuration = 'Release',
    [ValidateSet('Clang','MSVC')]
    [string]$Compiler = 'Clang',
    [ValidateSet('on','off')]
    [string]$Logs,
    [int]$Jobs,
    [Parameter(ValueFromRemainingArguments)][string[]]$Rest
)
$ErrorActionPreference = 'Stop'

if ($PSBoundParameters.ContainsKey('Jobs')) {
    if ($Jobs -lt 1) { throw "-Jobs must be a positive integer, got '$Jobs'" }
    $env:MT_BUILD_JOBS = "$Jobs"
}

Write-Host ''
Write-Host '  COMMERCIAL build: MT_COMMERCIAL_BUILD=1, MT_PRIVATE_BUILD=0.' -ForegroundColor Cyan
Write-Host '  NONFREE (SURF) is forced off by the RESOLVER, before the fragments,' -ForegroundColor Cyan
Write-Host '  LICENSES.txt and the out-dir hash are written. This build does NOT' -ForegroundColor Cyan
Write-Host '  run the symbol gate -- to prove the binary carries no xfeatures2d, run' -ForegroundColor Cyan
Write-Host '  MTEngineSDL\tools\appbuild\scan-capability-symbols.ps1 against it.' -ForegroundColor Cyan
Write-Host '  Distribution-restricted dependencies are dropped with the private tier.' -ForegroundColor Cyan
Write-Host ''

# MT_ENABLE_FFMPEG=0 IS NOT OPTIONAL HERE, AND THE RESOLVER NOW SAYS SO. Since
# engine 7758e6f2 FFmpeg is commercial_safe: false, so a commercial resolve that
# would enable it is REFUSED outright rather than quietly allowed:
#
#   mtcaps: MT_COMMERCIAL_BUILD=1 would enable 'FFmpeg' (licence: LGPL-2.1
#   (GPL components excluded)), which is marked commercial_safe: false in the
#   vocabulary. It is pulled in by MT_CAP_VIDEO_PLAYBACK via MT_ENABLE_FFMPEG.
#
# Without this line the wrapper cannot produce a store build at all: it stops at
# the resolve, before a single object is compiled.
#
# THE FLAG, NOT THE CAPABILITY. The error offers "turn that capability off",
# which would take video playback down with it -- and video playback WITHOUT
# FFmpeg is the entire point of the media-codecs programme. MT_CAP_VIDEO_PLAYBACK
# stays 1 and decoding goes through the OS (Media Foundation on Windows,
# AVFoundation on macOS), which is the configuration the tracker calls the store
# configuration.
$argsToStub = @{
    Configuration = $Configuration
    Compiler      = $Compiler
    Prod          = $true
    Tier          = 'commercial'
    Set           = @('MT_ENABLE_FFMPEG=0')
}
if ($Platform) { $argsToStub.Platform = $Platform }
if ($Logs)     { $argsToStub.Logs     = $Logs }

# NOT @Rest DIRECTLY. Under `powershell.exe -File` with no arguments,
# ValueFromRemainingArguments splats a single EMPTY STRING -- which binds
# POSITIONALLY to the stub's second parameter, Compiler, and dies on its
# ValidateSet with `The argument "" does not belong to the set "Clang,MSVC"`.
# Filtering first is what makes a bare `.\build-windows-prod-commercial.ps1`
# work. A scriptblock test does NOT reproduce it: an explicitly $null $Rest
# splats nothing, so this only appears through the -File entry point the .sh
# uses.
$extra = @($Rest | Where-Object { $_ })

& (Join-Path $PSScriptRoot 'build-windows.ps1') @argsToStub @extra
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# REPORT WHAT WAS ACTUALLY PRODUCED rather than recomputing the path. -Platform
# may have been unset and resolved by the driver, so this script does not know
# the architecture. (A commercial deploy carries no -nc suffix; the driver names
# it after MT_WINDOWS_EXE.) Finding the newest exe answers both without this
# file having to predict either.
Write-Host ''
$pkgExe = Get-ChildItem (Join-Path $PSScriptRoot 'platform\Windows\prod') -Recurse -Filter '*.exe' `
              -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($pkgExe) { Write-Host "Package: $($pkgExe.FullName)" -ForegroundColor Green }
else         { Write-Host "Package: under $(Join-Path $PSScriptRoot 'platform\Windows\prod')" -ForegroundColor Green }
Write-Host '  Check the resolve summary above for what the tier withheld.' -ForegroundColor Cyan
Write-Host '  Verify it from the package, not the git root:  tests/run_test.sh --package' -ForegroundColor Cyan
exit 0
