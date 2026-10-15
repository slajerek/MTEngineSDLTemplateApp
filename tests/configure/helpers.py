import importlib.util, json, os, shutil, subprocess, tempfile
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2]

def load_configure():
    spec = importlib.util.spec_from_file_location("configure", TEMPLATE / "configure.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def git(cwd, *args, env=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout

def make_workspace():
    """A scratch parent dir holding a fake engine and a git clone of a mini template.

    Returns (parent, template_dir, engine_dir). The mini template is a real git
    repo with the shapes the configurator touches, so tests never write near
    the real template."""
    # resolve(): on macOS mkdtemp returns /var/..., which resolve_options turns
    # into /private/var/...; compare like with like.
    parent = Path(tempfile.mkdtemp(prefix="cfgtest-")).resolve()
    engine = parent / "MTEngineSDL"
    (engine / "tools/mtcaps").mkdir(parents=True)
    (engine / "src/Engine/GUI").mkdir(parents=True)
    (engine / "src/Engine/GUI/CGuiMain.h").write_text("// engine header\n")
    (engine / "tools/mtcaps/vocabulary.json").write_text(json.dumps({
        "capabilities": {
            "MT_CAP_CRASH_REPORTER": {"short": "Crash reporter", "description": "Crash reports.", "default": 1},
            "MT_CAP_TEST_ENGINE": {"short": "Test engine", "description": "UI tests.", "default": 1},
            "MT_CAP_HTTP": {"short": "HTTP", "description": "HTTP client.", "default": 1},
            "MT_CAP_HTTPS": {"short": "HTTPS", "description": "TLS.", "default": 1, "implies": ["MT_CAP_HTTP"]},
            "MT_CAP_MIDI": {"short": "MIDI", "description": "MIDI.", "default": 1},
            "MT_CAP_NEW": {"short": "New", "description": "Added later.", "default": 1},
        }}))
    tpl = parent / "MTEngineSDLTemplateApp"
    files = {
        "src/TemplateAppInit.cpp":
            'static const EMTMenuBarMode kMenuBarMode = EMTMenuBarMode::ImGui;\n'
            'static const char *kAppId = "com.example.templateapp";\n'
            'static const char *kWindowTitle    = "TemplateApp";\n'
            'static const char *kSettingsFolder = "MTEngineSDLTemplateApp";\n',
        "src/TemplateAppVersion.h": '#ifndef _TEMPLATEAPPVERSION_H_\n#define TEMPLATEAPP_VERSION "0.1.0"\n#endif\n',
        "src/Views/CViewTemplateAppMain.h": "class CViewTemplateAppMain {};\n",
        "assets/locale/en.json": json.dumps({"meta": {"locale": "en", "displayName": "English", "fallbacks": [],
                                   "version": 1}, "strings": {"app.title": "TemplateApp"}}, indent=4) + "\n",
        "mtengine.caps": "# CR\nMT_CAP_CRASH_REPORTER=1\n\n# TE\nMT_CAP_TEST_ENGINE=1\n\n# HTTP\nMT_CAP_HTTP=0\n\n"
                         "# HTTPS\nMT_CAP_HTTPS=0\n\n# MIDI\nMT_CAP_MIDI=0\n\nMT_COMMERCIAL_BUILD=0\n\nMT_PRIVATE_BUILD=0\n",
        "MTENGINE_REF": "origin/master\n",
        "platform/MacOS/MTEngineSDLTemplateApp.xcodeproj/project.pbxproj":
            "PRODUCT_BUNDLE_IDENTIFIER = com.example.templateapp;\nPRODUCT_BUNDLE_IDENTIFIER = com.example.templateapp;\n",
        "platform/Windows/MTEngineSDLTemplateApp.sln":
            'Project("{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}") = "MTEngineSDLTemplateApp", "MTEngineSDLTemplateApp\\MTEngineSDLTemplateApp.vcxproj", "{11111111-2222-3333-4444-555555555555}"\n'
            'Project("{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}") = "MTEngineSDL", "..\\..\\MTEngineSDL\\MTEngineSDL.vcxproj", "{E93D3B41-0000-0000-0000-000000000000}"\n'
            "\t\t{11111111-2222-3333-4444-555555555555}.Debug|x64.ActiveCfg = Debug|x64\n"
            "\t\tSolutionGuid = {99999999-8888-7777-6666-555555555555}\n",
        "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.vcxproj":
            "<ProjectGuid>{11111111-2222-3333-4444-555555555555}</ProjectGuid>\n"
            "<ProjectReference><Project>{E93D3B41-0000-0000-0000-000000000000}</Project></ProjectReference>\n",
        "platform/Linux/com.example.templateapp.desktop": "Name=TemplateApp\nIcon=com.example.templateapp\nStartupWMClass=com.example.templateapp\n",
        "platform/Linux/icons/hicolor/16x16/apps/com.example.templateapp.png": "PNG",
        "platform/MacOS/Info.plist": "<dict>\n\t<key>CFBundleDisplayName</key>\n\t<string>TemplateApp</string>\n"
                                     "\t<key>CFBundleName</key>\n\t<string>TemplateApp</string>\n</dict>\n",
        "platform/MacOS/MTEngineSDLTemplateApp.icns": "ICNS",
        "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.ico": "ICO",
        "tools/icons/master.png": "PNG",
        "tools/icons/gen-icons.py": 'APP_ID = "com.example.templateapp"\n',
        "CMakeLists.txt": "install(FILES platform/Linux/com.example.templateapp.desktop DESTINATION share/applications)\n",
        "platform/Windows/MTEngineSDLTemplateApp.rc.crlf": "IDI_ICON1 ICON \"MTEngineSDLTemplateApp.ico\"\r\n",
        ".github/workflows/build-linux.yml": "name: Linux build\n",
        ".github/workflows/configure.yml": "name: configure\n",
        "claude/githooks/commit-msg": (TEMPLATE / "claude/githooks/commit-msg").read_text(),
        ".gitattributes": "claude/githooks/* text eol=lf\n",
        "CLAUDE.md": "# CLAUDE.md\n\n<!-- template-only:begin -->\nTemplate invariants.\n<!-- template-only:end -->\n\nTemplateApp guide.\n",
        "README.md": "<!-- template-only:begin -->\n# MTEngineSDLTemplateApp\n<!-- template-only:end -->\n# TemplateApp\n",
        "configure.py": "# configurator\n",
        "configure_tui.py": "# wizard\n",
        "tests/configure/test_x.py": "# test\n",
        "specs/superpowers/specs/x.md": "internal\n",
        "LICENSE": "MIT\n",
    }
    for rel, text in files.items():
        p = tpl / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))   # exact bytes on every OS: the tests check line endings
    os.chmod(tpl / "claude/githooks/commit-msg", 0o755)
    git(tpl, "init", "-q")
    git(tpl, "config", "user.name", "t"); git(tpl, "config", "user.email", "t@t.invalid")
    (tpl / "AGENTS.md").symlink_to("CLAUDE.md")
    git(tpl, "add", "-A"); git(tpl, "commit", "-q", "-m", "mini template")
    return parent, tpl, engine
