#!/usr/bin/env python3
"""Create a new MTEngineSDL app from this template.

    ./configure.py                              # full-screen wizard (curses)
    ./configure.py MyTool                       # the wizard, with the name filled in
    ./configure.py MyTool --menu hybrid --caps MIDI,HTTPS --locales en,pl --yes

The app is written to ../MyTool, next to the template and to MTEngineSDL. The
template is never modified. Standard library only.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from pathlib import Path

VERSION = "1"
HERE = Path(__file__).resolve().parent
TOKEN = "TemplateApp"
TEMPLATE_ONLY = ("configure.py", "configure_tui.py", "tests/configure/", ".github/workflows/configure.yml", "specs/")
NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
BUNDLE_RE = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+$")
FOLDER_RE = re.compile(r"^[A-Za-z0-9._-]+$")
LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
GENERATED_HEADERS = ("C{n}Menu.h", "C{n}I18n.h", "CView{n}Main.h", "C{n}TestSuite.h", "{n}Init.h", "{n}Version.h")
LEFTOVER_RE = re.compile(r"(?i)template_?app")


class ConfigError(Exception):
    pass


# The engine revision a new app's MTENGINE_REF names, which is what its CI
# clones from GitHub. `devel` is the public engine's live branch; its `master`
# lags until the next stable merge. Asked for, because this changes over time.
DEFAULT_ENGINE_REF = "origin/devel"
ENGINE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


@dataclass
class Options:
    name: str
    out: Path
    title: str
    settings_folder: str
    bundle_id: str
    menu: str
    caps: list = field(default_factory=list)
    locales: list = field(default_factory=lambda: ["en"])
    icon: Path = None
    ci: bool = True
    git: bool = True
    template: Path = HERE
    engine: Path = None
    engine_ref: str = DEFAULT_ENGINE_REF



def token_map(name):
    return [("MTEngineSDLTemplateApp", name), ("TemplateApp", name),
            ("templateapp", name.lower()), ("TEMPLATEAPP", name.upper())]


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="PascalCase app name, e.g. MyTool")
    ap.add_argument("--out", type=Path, help="output dir (default ../<Name>, beside MTEngineSDL)")
    ap.add_argument("--title", help="window title (default <Name>)")
    ap.add_argument("--settings-folder", help="settings folder name (default <Name>)")
    ap.add_argument("--bundle-id", help="reverse-DNS id (default com.example.<name>)")
    ap.add_argument("--menu", choices=["imgui", "hybrid"], help="imgui everywhere, or native on macOS/Windows")
    ap.add_argument("--engine-ref", help=f"engine branch, tag or SHA for MTENGINE_REF, which CI clones "
                                         f"(default {DEFAULT_ENGINE_REF})")
    ap.add_argument("--caps", help="capabilities to enable, comma-separated, without MT_CAP_ (e.g. MIDI,HTTPS)")
    ap.add_argument("--locales", help="comma-separated locale tags; en is always included")
    ap.add_argument("--icon", type=Path, help="square PNG >= 1024 px to use as the app icon (needs Pillow)")
    ap.add_argument("--no-ci", action="store_true", help="drop .github/workflows")
    ap.add_argument("--no-git", action="store_true", help="do not git init / commit")
    ap.add_argument("--yes", action="store_true", help="never prompt; use defaults for anything not given")
    ap.add_argument("--plain", action="store_true", help="ask line by line instead of the full-screen wizard")
    ap.add_argument("--template", type=Path, default=HERE, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def _split(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def resolve_options(ns, interactive, ask=input):
    def get(value, prompt, default, flag):
        if value is not None:
            return value
        if ns.yes:
            if default is None:
                raise ConfigError(f"{flag} is required")
            return default
        if not interactive:
            raise ConfigError(f"{flag} is required (no terminal to ask on; pass it, or --yes for defaults)")
        shown = f" [{default}]" if default not in (None, "") else ""
        answer = ask(f"{prompt}{shown}: ").strip()
        if not answer and default is None:
            raise ConfigError(f"{flag} is required")
        return answer or default

    template = ns.template.resolve()
    name = get(ns.name, "App name (PascalCase)", None, "name")
    parent = template.parent
    out = Path(get(str(ns.out) if ns.out else None, "Output directory", str(parent / name), "--out")).expanduser()
    title = get(ns.title, "Window title", name, "--title")
    folder = get(ns.settings_folder, "Settings folder", name, "--settings-folder")
    bundle = get(ns.bundle_id, "Bundle id", f"com.example.{name.lower()}", "--bundle-id")
    menu = get(ns.menu, "Menu (imgui/hybrid)", "imgui", "--menu")
    engine_ref = get(ns.engine_ref, "Engine branch for CI (MTENGINE_REF)", DEFAULT_ENGINE_REF, "--engine-ref")
    caps = _split(get(ns.caps, "Extra capabilities (comma-separated, e.g. MIDI,HTTPS)", "", "--caps"))
    locales = _split(get(ns.locales, "Locales (comma-separated)", "en", "--locales"))
    icon = get(str(ns.icon) if ns.icon else None, "Icon PNG (empty = placeholder)", "", "--icon")
    if ns.no_ci or ns.yes or not interactive:
        ci = not ns.no_ci
    else:
        ci = ask("Include CI workflows? [Y/n]: ").strip().lower() not in ("n", "no")
    if ns.no_git or ns.yes or not interactive:
        use_git = not ns.no_git
    else:
        use_git = ask("git init and first commit? [Y/n]: ").strip().lower() not in ("n", "no")
    if "en" not in locales:
        locales.insert(0, "en")
    else:
        locales.insert(0, locales.pop(locales.index("en")))
    return Options(name=name, out=out.resolve(), title=title, settings_folder=folder, bundle_id=bundle,
                   menu=menu, caps=[c.upper().removeprefix("MT_CAP_") for c in caps], locales=locales,
                   icon=Path(icon).expanduser().resolve() if icon else None, ci=ci, git=use_git,
                   template=template, engine=template.parent / "MTEngineSDL", engine_ref=engine_ref)


def validate(o):
    if not NAME_RE.match(o.name):
        raise ConfigError(f"name {o.name!r} must be PascalCase letters and digits, starting with a capital")
    if re.search(r"(?i)template_?app", o.name):
        raise ConfigError(f"name {o.name!r} must not contain the template's own token")
    for flag, value in (("--title", o.title), ("--settings-folder", o.settings_folder), ("--bundle-id", o.bundle_id)):
        if LEFTOVER_RE.search(value):
            raise ConfigError(f"{flag} {value!r} must not contain the template's own token (TemplateApp in any spelling)")
    if not (o.template / ".git").exists():
        raise ConfigError(f"{o.template} is not a git clone. Use `git clone` rather than a ZIP download; "
                          "the configurator copies `git ls-files` and needs symlinks as git stores them.")
    if o.out.exists():
        raise ConfigError(f"{o.out} already exists")
    if o.out.parent != o.template.parent:
        raise ConfigError(f"{o.out} must be next to the template and MTEngineSDL (in {o.template.parent}): "
                          "the build scripts and the .sln find the engine at ../MTEngineSDL")
    if not ENGINE_REF_RE.match(o.engine_ref):
        raise ConfigError(f"--engine-ref {o.engine_ref!r} must be a branch (origin/devel), tag or SHA")
    if not o.title.strip():
        raise ConfigError("title must not be empty")
    if any(ord(c) < 32 for c in o.title):
        raise ConfigError("title must be one line, without control characters")
    if not FOLDER_RE.match(o.settings_folder):
        raise ConfigError(f"settings folder {o.settings_folder!r} may only use letters, digits, '.', '_', '-'")
    if not BUNDLE_RE.match(o.bundle_id):
        raise ConfigError(f"bundle id {o.bundle_id!r} must be lowercase reverse-DNS, e.g. com.example.mytool")
    if o.menu not in ("imgui", "hybrid"):
        raise ConfigError("--menu must be imgui or hybrid")
    for tag in o.locales:
        if not LOCALE_RE.match(tag):
            raise ConfigError(f"locale tag {tag!r} is not a BCP-47 tag such as pl or pt-BR")
    if o.icon is not None and not o.icon.is_file():
        raise ConfigError(f"icon {o.icon} not found")
    engine_headers = set()
    if (o.engine / "src").is_dir():
        engine_headers = {p.name.lower() for p in (o.engine / "src").rglob("*.h")}
    for pattern in GENERATED_HEADERS:
        h = pattern.format(n=o.name)
        if h.lower() in engine_headers:
            raise ConfigError(f"name {o.name!r} generates {h}, which clashes with an engine header of the same name")



def locate_engine(o):
    vocab_path = o.engine / "tools/mtcaps/vocabulary.json"
    ref = o.engine_ref
    if o.engine.is_dir() and not vocab_path.is_file():
        raise ConfigError(
            f"{o.engine} exists but has no tools/mtcaps: it is probably on the wrong branch.\n"
            f"This template is built against MTENGINE_REF {ref}:\n"
            f"    git -C {o.engine} fetch && git -C {o.engine} checkout {ref.removeprefix('origin/')}")
    if not vocab_path.is_file():
        raise ConfigError(
            f"MTEngineSDL not found at {o.engine}. Clone it first:\n"
            f"    git clone https://github.com/slajerek/MTEngineSDL.git {o.engine}\n"
            f"    git -C {o.engine} checkout {ref.removeprefix('origin/')}")
    try:
        head = subprocess.run(["git", "-C", str(o.engine), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        # --verify --quiet: an unknown ref prints nothing (plain rev-parse echoes the name back).
        want = subprocess.run(["git", "-C", str(o.engine), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                              capture_output=True, text=True).stdout.strip()
        if want and head != want:
            print(f"warning: MTEngineSDL is at {head[:12]}, not at MTENGINE_REF {ref} ({want[:12]}); "
                  "the app is generated against the engine you have, CI builds against MTENGINE_REF", file=sys.stderr)
    except (OSError, subprocess.CalledProcessError):
        print(f"warning: could not compare MTEngineSDL HEAD with MTENGINE_REF {ref}", file=sys.stderr)
    return json.loads(vocab_path.read_text(encoding="utf-8"))["capabilities"]


def validate_caps(caps, vocab):
    unknown = [c for c in caps if f"MT_CAP_{c}" not in vocab]
    if unknown:
        valid = ", ".join(sorted(k.removeprefix("MT_CAP_") for k in vocab))
        raise ConfigError(f"unknown capabilities: {', '.join(unknown)}. Valid: {valid}")


def _comment(cap):
    desc = cap.get("description", "").split(".")[0]
    return f"# {cap.get('short', '')}: {desc}." if desc else f"# {cap.get('short', '')}"


def build_manifest(text, caps, vocab):
    notes = []
    wanted = set()
    stack = [f"MT_CAP_{c}" for c in caps]
    while stack:
        key = stack.pop()
        if key in wanted:
            continue
        wanted.add(key)
        for implied in vocab.get(key, {}).get("implies", []):
            if implied not in wanted and not any(n.startswith(f"{implied} enabled") for n in notes):
                notes.append(f"{implied} enabled: implied by {key}")
                stack.append(implied)

    present = set(re.findall(r"^(MT_CAP_[A-Z0-9_]+)=", text, flags=re.M))
    nl = "\r\n" if "\r\n" in text else "\n"   # keep the file's line endings
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(MT_CAP_[A-Z0-9_]+)=([01])(\r?\n?)$", line)
        if m and m.group(1) in wanted:
            out.append(f"{m.group(1)}=1{m.group(3)}")
        else:
            out.append(line)
    text = "".join(out)

    missing = sorted(k for k in vocab if k not in present)
    if missing:
        block = ""
        for key in missing:
            value = 1 if key in wanted else 0
            block += f"{_comment(vocab[key])}{nl}{key}={value}{nl}{nl}"
            notes.append(f"{key} added as {value}: new in the engine vocabulary")
        marker = nl + "# Licence tier."
        idx = text.find(marker)
        cut = idx + len(nl)
        text = text[:cut] + block + text[cut:] if idx >= 0 else text.rstrip("\r\n") + nl + nl + block
    return text, notes


def run_resolver(manifest, o):
    mtcaps = o.engine / "tools/mtcaps/mtcaps.py"
    if not mtcaps.is_file():
        return  # fixture engines in the unit tests have no resolver
    arch = {"arm64": "arm64", "aarch64": "arm64"}.get(os.uname().machine if hasattr(os, "uname") else "", "x86_64")
    with tempfile.TemporaryDirectory() as tmp:
        for platform in ("linux", "macos", "windows"):
            r = subprocess.run([sys.executable, str(mtcaps), "resolve", "--manifest", str(manifest),
                                "--app", o.name, "--platform", platform, "--arch", arch, "--config", "Release",
                                "--engine-dir", str(o.engine), "--out-dir", tmp, "--print", "resolved"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise ConfigError(f"mtcaps resolve ({platform}) rejected the manifest:\n{r.stderr.strip() or r.stdout.strip()}")


BEGIN = "<!-- template-only:begin -->"
END = "<!-- template-only:end -->"


def _is_template_only(path):
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in TEMPLATE_ONLY)


def tracked_entries(template):
    out = subprocess.run(["git", "-C", str(template), "ls-files", "-s", "-z"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    entries = []
    for rec in filter(None, out.split("\0")):
        meta, path = rec.split("\t", 1)
        mode, sha, _stage = meta.split()
        target = ""
        if mode == "120000":
            target = subprocess.run(["git", "-C", str(template), "cat-file", "blob", sha],
                                    capture_output=True, check=True).stdout.decode("utf-8")
        entries.append((path, mode, target))
    return entries


def copy_tree(o, staging):
    dirty = subprocess.run(["git", "-C", str(o.template), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        print("warning: the template has uncommitted changes; tracked files are copied with their "
              "working-tree content", file=sys.stderr)
    links, execs = [], []
    for path, mode, target in tracked_entries(o.template):
        if _is_template_only(path):
            continue
        dst = staging / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "120000":
            links.append(path)
            try:
                os.symlink(target, dst)
            except (OSError, NotImplementedError):
                dst.write_text(target)   # what git itself checks out without symlink support
            continue
        try:
            shutil.copyfile(o.template / path, dst)
        except FileNotFoundError:
            raise ConfigError(f"{path} is tracked but missing from the template's working tree; "
                              f"restore it (git -C {o.template} checkout -- {path}) or commit its removal")
        if mode == "100755":
            execs.append(path)
            dst.chmod(dst.stat().st_mode | 0o111)   # a no-op on Windows: git_init records the mode
    return links, execs


def strip_template_only(text, path):
    out, depth, start = [], 0, 0
    for i, line in enumerate(text.splitlines(keepends=True), 1):
        s = line.strip()
        if s == BEGIN:
            if depth:
                raise ConfigError(f"{path}:{i}: nested template-only begin (opened at line {start})")
            depth, start = 1, i
            continue
        if s == END:
            if not depth:
                raise ConfigError(f"{path}:{i}: template-only end without begin")
            depth = 0
            continue
        if not depth:
            out.append(line)
    if depth:
        raise ConfigError(f"{path}:{start}: template-only begin without end")
    if not start:
        return text   # no markers: the file is returned byte-for-byte
    # Close the gap a removed block leaves; keep the file's own line endings.
    result = re.sub(r"(\r?\n)(?:\r?\n){2,}", r"\1\1", "".join(out))
    return result.lstrip("\r\n")


def _is_text(data):
    return b"\0" not in data[:8192]


def _replace_all(s, mapping):
    for old, new in mapping:
        s = s.replace(old, new)
    return s


def rename_tree(staging, mapping):
    # Contents first (paths do not change file identity).
    for p in staging.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        data = p.read_bytes()
        if not _is_text(data):
            continue
        text = data.decode("utf-8", errors="surrogateescape")
        new = _replace_all(text, mapping)
        if new != text:
            p.write_bytes(new.encode("utf-8", errors="surrogateescape"))
    # Then paths, deepest first; case-only renames go through a temporary name.
    for p in sorted(staging.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        new_name = _replace_all(p.name, mapping)
        if new_name == p.name:
            continue
        target = p.with_name(new_name)
        if new_name.lower() == p.name.lower():
            tmp = p.with_name(p.name + ".cfgtmp")
            os.rename(p, tmp)
            os.rename(tmp, target)
        else:
            os.rename(p, target)


def _read(path):
    # newline="": no translation in either direction, so a file keeps its line
    # endings on every OS (spec #4.3 step 5). Path.read_text/write_text would
    # turn LF into CRLF on Windows.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _sub_once(path, pattern, repl, what):
    text = _read(path)
    new, n = re.subn(pattern, repl, text)
    if n == 0:
        raise ConfigError(f"{path}: could not find {what} to set")
    _write(path, new)


def apply_values(o, staging, manifest_text):
    name = o.name
    default_id = f"com.example.{name.lower()}"
    if o.bundle_id != default_id:
        # Every text file, not a list of known ones: the id also lives in
        # CMakeLists.txt (install of the .desktop) and tools/icons/gen-icons.py
        # (APP_ID), and a file added to the template later must not be missed.
        # First, so that the explicit sets below see the final id: a chosen id
        # that contains the default one (com.example.x.pro) must not be renamed twice.
        rename_tree(staging, [(default_id, o.bundle_id)])

    init = staging / f"src/{name}Init.cpp"
    q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    _sub_once(init, r'(kWindowTitle\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{q(o.title)}"', "kWindowTitle")
    _sub_once(init, r'(kSettingsFolder\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{q(o.settings_folder)}"', "kSettingsFolder")
    _sub_once(init, r'(kAppId\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{o.bundle_id}"', "kAppId")
    mode = "Native" if o.menu == "hybrid" else "ImGui"
    _sub_once(init, r"(kMenuBarMode\s*=\s*EMTMenuBarMode::)\w+", lambda m: m.group(1) + mode, "kMenuBarMode")

    # The title is also the name the user sees outside the window: the macOS
    # app menu and Dock (CFBundleName, CFBundleDisplayName) and the Linux
    # launcher (the .desktop Name=). The class name stays the executable's.
    xml = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    plist = staging / "platform/MacOS/Info.plist"
    for key in ("CFBundleName", "CFBundleDisplayName"):
        _sub_once(plist, rf"(<key>{key}</key>\s*<string>)[^<]*(</string>)",
                  lambda m: m.group(1) + xml(o.title) + m.group(2), key)
    _sub_once(staging / f"platform/Linux/{o.bundle_id}.desktop", r"(?m)^Name=.*$",
              lambda m: "Name=" + o.title, ".desktop Name=")

    pbx = staging / f"platform/MacOS/{name}.xcodeproj/project.pbxproj"
    _sub_once(pbx, r"PRODUCT_BUNDLE_IDENTIFIER = [^;]+;", f"PRODUCT_BUNDLE_IDENTIFIER = {o.bundle_id};", "PRODUCT_BUNDLE_IDENTIFIER")

    _write(staging / "mtengine.caps", manifest_text)
    # Only the value line: the comment above it explains branch vs pin.
    _sub_once(staging / "MTENGINE_REF", r"(?m)^(?![ \t]*#)[ \t]*\S+[ \t]*$", lambda m: o.engine_ref, "the MTENGINE_REF line")

    en_path = staging / "assets/locale/en.json"
    # The About window shows app.title: it is the --title, not the class name.
    # A targeted edit, so the rest of en.json keeps its bytes.
    _sub_once(en_path, r'("app\.title"\s*:\s*)"(?:[^"\\]|\\.)*"',
              lambda m: m.group(1) + json.dumps(o.title, ensure_ascii=False), '"app.title"')
    en = json.loads(_read(en_path))
    for tag in o.locales:
        if tag == "en":
            continue
        doc = json.loads(json.dumps(en))
        doc["meta"].update({"locale": tag, "displayName": tag, "fallbacks": ["en"]})
        _write(staging / f"assets/locale/{tag}.json", json.dumps(doc, indent=4, ensure_ascii=False) + "\n")

    if not o.ci:
        shutil.rmtree(staging / ".github/workflows", ignore_errors=True)
        gh = staging / ".github"
        if gh.exists() and not any(gh.iterdir()):
            gh.rmdir()

    # After the bundle-id rename: gen-icons.py names the Linux PNGs after APP_ID.
    if o.icon is not None:
        shutil.copyfile(o.icon, staging / "tools/icons/master.png")
        r = subprocess.run([sys.executable, str(staging / "tools/icons/gen-icons.py")], capture_output=True, text=True)
        if r.returncode != 0:
            raise ConfigError(f"icon generation failed:\n{r.stderr.strip() or r.stdout.strip()}")


GUID_RE = r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}"


def regenerate_guids(staging, name):
    vcx = staging / f"platform/Windows/{name}/{name}.vcxproj"
    sln = staging / f"platform/Windows/{name}.sln"
    vtext = _read(vcx)
    m = re.search(rf"<ProjectGuid>({GUID_RE})</ProjectGuid>", vtext)
    if not m:
        raise ConfigError(f"{vcx}: no <ProjectGuid>")
    old = m.group(1)
    new = "{" + str(uuid.uuid4()).upper() + "}"
    files = [vcx, sln] + list((staging / f"platform/Windows/{name}").glob("*.filters"))
    for p in files:
        t = _read(p)
        t = re.sub(re.escape(old), new, t, flags=re.I)
        if p == sln:
            t = re.sub(rf"(SolutionGuid = ){GUID_RE}", lambda mm: mm.group(1) + "{" + str(uuid.uuid4()).upper() + "}", t)
        _write(p, t)


def write_template_config(o, staging, engine_sha):
    sha = subprocess.run(["git", "-C", str(o.template), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    doc = {"configurator_version": VERSION, "template_sha": sha, "engine_sha": engine_sha,
           "options": {"name": o.name, "title": o.title, "settings_folder": o.settings_folder,
                       "bundle_id": o.bundle_id, "menu": o.menu, "caps": o.caps, "locales": o.locales,
                       "icon": bool(o.icon), "ci": o.ci, "git": o.git, "engine_ref": o.engine_ref}}
    _write(staging / "template-config.json", json.dumps(doc, indent=2) + "\n")


MARKER_RE = re.compile(r"template-only:(begin|end)")


class GitStepError(Exception):
    def __init__(self, command, remaining):
        super().__init__(command)
        self.command, self.remaining = command, remaining


def self_check(staging, name):
    problems = []
    for p in staging.rglob("*"):
        rel = p.relative_to(staging).as_posix()
        if rel == "template-config.json" or rel.startswith(".git/"):
            continue
        if LEFTOVER_RE.search(rel):
            problems.append(f"{rel}: token in path")
        if _is_template_only(rel) or (p.is_dir() and _is_template_only(rel + "/")):
            problems.append(f"{rel}: template-only path")
        if p.is_symlink() or not p.is_file():
            continue
        data = p.read_bytes()
        if not _is_text(data):
            continue
        for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if LEFTOVER_RE.search(line):
                problems.append(f"{rel}:{i}: leftover token")
            if MARKER_RE.search(line):
                problems.append(f"{rel}:{i}: template-only marker")
    for required in ("claude/githooks/commit-msg", ".gitattributes",
                     f"platform/MacOS/{name}.icns", f"platform/Windows/{name}/{name}.ico"):
        if not (staging / required).exists():
            problems.append(f"{required}: missing")
    # The Linux icons are named by bundle id, which self_check does not take:
    # any PNG in the hicolor ladder proves the ladder was written.
    if not any(staging.glob("platform/Linux/icons/hicolor/*/apps/*.png")):
        problems.append("platform/Linux/icons/hicolor: missing")
    if problems:
        raise ConfigError("self-check failed:\n  " + "\n  ".join(sorted(problems)))


def move_into_place(staging, out):
    # mkdtemp creates 0700 and os.replace keeps it: give the app the mode a
    # plain mkdir would have had.
    umask = os.umask(0)
    os.umask(umask)
    staging.chmod(0o777 & ~umask)
    for attempt in range(5):
        try:
            os.replace(staging, out)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))   # antivirus holding a file (Windows)


def _git(cwd, *args, extra=None):
    return subprocess.run(["git", *(extra or []), *args], cwd=cwd, check=True, capture_output=True, text=True)


def final_paths(o, paths):
    """Template paths as they are named in the app: the token rename, then the
    bundle-id rename apply_values does when the id is not the default one."""
    out = [_replace_all(p, token_map(o.name)) for p in paths]
    default_id = f"com.example.{o.name.lower()}"
    if o.bundle_id != default_id:
        out = [p.replace(default_id, o.bundle_id) for p in out]
    return out


def git_init(o, links, execs=()):
    out = o.out
    sha = subprocess.run(["git", "-C", str(o.template), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    steps = [("init", "-q"), ("symbolic-ref", "HEAD", "refs/heads/main"),
             ("config", "core.hooksPath", "claude/githooks"),
             # --force: the app is the template's tracked set, and the template
             # tracks files its own .gitignore matches. Staging holds only that
             # set plus template-config.json, so nothing unwanted is added.
             ("add", "-A", "--force")]
    if execs:
        # chmod is a no-op on Windows and Git for Windows runs with
        # core.filemode=false, so `add` alone would record 100644 and the build
        # scripts and the commit-msg hook would lose their executable bit.
        steps.append(("update-index", "--chmod=+x", "--", *execs))
    done = []
    try:
        for step in steps:
            _git(out, *step); done.append(step)
        for link in links:
            if not (out / link).is_symlink():   # written as a file: record it as a symlink anyway
                blob = _git(out, "hash-object", "-w", link).stdout.strip()
                _git(out, "update-index", "--add", "--cacheinfo", f"120000,{blob},{link}")
        ident = []
        name_set = subprocess.run(["git", "config", "user.name"], cwd=out, capture_output=True, text=True).stdout.strip()
        mail_set = subprocess.run(["git", "config", "user.email"], cwd=out, capture_output=True, text=True).stdout.strip()
        if not name_set or not mail_set:
            ident = ["-c", f"user.name={o.name}", "-c", f"user.email={o.name.lower()}@users.noreply.invalid"]
            print(f"note: no git identity configured; the initial commit is authored as {o.name}", file=sys.stderr)
        _git(out, "commit", "-q", "-m", f"Initial commit from MTEngineSDLTemplateApp {sha}", extra=ident)
    except subprocess.CalledProcessError as e:
        remaining = [" ".join(["git", *s]) for s in steps if s not in done]
        remaining.append(f'git commit -m "Initial commit from MTEngineSDLTemplateApp {sha}"')
        raise GitStepError(" ".join(map(str, e.cmd)) + (f": {e.stderr.strip()}" if e.stderr else ""), remaining)


def generate(o):
    vocab = locate_engine(o)
    validate_caps(o.caps, vocab)
    manifest, notes = build_manifest(_read(o.template / "mtengine.caps"), o.caps, vocab)
    for n in notes:
        print(f"caps: {n}")
    staging = Path(tempfile.mkdtemp(prefix=f".{o.name}-", dir=o.out.parent))
    try:
        mpath = staging / "mtengine.caps.check"
        _write(mpath, manifest)
        # mtcaps reads the app's licence rows from this file beside the manifest.
        lic = o.template / "mtengine-app-licenses.json"
        lic_copy = staging / lic.name
        if lic.is_file():
            shutil.copy2(lic, lic_copy)
        run_resolver(mpath, o)
        mpath.unlink()
        if lic_copy.exists():
            lic_copy.unlink()   # copy_tree writes the tracked copy back, if the template tracks it
        links, execs = copy_tree(o, staging)
        for p in staging.rglob("*.md"):
            if p.is_file() and not p.is_symlink():
                text = _read(p)
                stripped = strip_template_only(text, p.relative_to(staging).as_posix())
                if stripped != text:
                    _write(p, stripped)
        rename_tree(staging, token_map(o.name))
        # The manifest was built from the template's text: rename it like every other file.
        apply_values(o, staging, _replace_all(manifest, token_map(o.name)))
        regenerate_guids(staging, o.name)
        engine_sha = subprocess.run(["git", "-C", str(o.engine), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        write_template_config(o, staging, engine_sha)
        self_check(staging, o.name)
        move_into_place(staging, o.out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final_paths(o, links), final_paths(o, execs)


def load_tui():
    """The wizard module, or None where curses is missing (Windows' Python)."""
    try:
        import curses  # noqa: F401
    except ImportError:
        print("note: the full-screen wizard needs curses; on Windows: py -m pip install windows-curses\n"
              "      asking line by line instead.", file=sys.stderr)
        return None
    sys.path.insert(0, str(HERE))
    import configure_tui
    return configure_tui


def main(argv=None):
    if sys.version_info < (3, 9):
        sys.exit("configure.py needs Python 3.9+")
    try:
        ns = parse_args(sys.argv[1:] if argv is None else argv)
        interactive = sys.stdin.isatty()
        tui = None if ns.yes or ns.plain or not (interactive and sys.stdout.isatty()) else load_tui()
        if tui:
            template = ns.template.resolve()
            engine = template.parent / "MTEngineSDL"
            vocab = locate_engine(SimpleNamespace(engine=engine, engine_ref=ns.engine_ref or DEFAULT_ENGINE_REF))
            o = tui.run(sys.modules[__name__], ns, template, engine, vocab)
            if o is None:
                print("cancelled; nothing was created", file=sys.stderr)
                return 1
        else:
            o = resolve_options(ns, interactive=interactive)
        validate(o)
        links, execs = generate(o)
        if o.git:
            git_init(o, links, execs)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except GitStepError as e:
        print(f"error: the app is complete in {o.out}, but git failed: {e.command}\n"
              f"run by hand:\n  cd {o.out}\n  " + "\n  ".join(e.remaining), file=sys.stderr)
        return 3
    print(f"\nCreated {o.out}\n\nNext:\n  cd {o.out}\n  ./build-macos.sh      # or ./build-linux.sh / .\\build-windows.ps1")
    if not o.git:
        print("  git init && git config core.hooksPath claude/githooks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
