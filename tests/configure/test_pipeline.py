import io, os, subprocess, tempfile, unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock
from helpers import load_configure, make_workspace, git

cfg = load_configure()

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()

    def run_cfg(self, *argv):
        return cfg.main(["MyTool", "--template", str(self.tpl), "--yes", *argv])

    def test_end_to_end(self):
        self.assertEqual(self.run_cfg("--menu", "hybrid", "--caps", "HTTPS", "--locales", "en,pl"), 0)
        out = self.parent / "MyTool"
        self.assertTrue((out / "src/MyToolInit.cpp").exists())
        self.assertFalse((out / "configure.py").exists())
        claude = (out / "CLAUDE.md").read_text()
        self.assertNotIn("template-only", claude)
        self.assertNotIn("Template invariants", claude)
        self.assertIn("MyTool guide.", claude)
        self.assertIn("MT_CAP_HTTP=1", (out / "mtengine.caps").read_text())
        self.assertEqual(git(out, "config", "core.hooksPath").strip(), "claude/githooks")
        self.assertIn("Initial commit from MTEngineSDLTemplateApp", git(out, "log", "-1", "--format=%s"))
        self.assertIn("120000", git(out, "ls-files", "-s", "AGENTS.md"))
        self.assertEqual(git(self.tpl, "status", "--porcelain"), "")
        if os.name == "posix":
            umask = os.umask(0); os.umask(umask)
            self.assertEqual(out.stat().st_mode & 0o777, 0o777 & ~umask)

    def test_executable_bits_survive_a_host_without_chmod(self):
        # Windows: chmod is a no-op and Git for Windows has core.filemode=false,
        # so `git add` alone records 100644. Every 100755 file of the template,
        # under its renamed path, must still be 100755 in the app.
        for rel in ("build-TemplateApp.sh", "tools/com.example.templateapp-run.sh"):
            (self.tpl / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tpl / rel).write_text("#!/bin/sh\n")
            os.chmod(self.tpl / rel, 0o755)
        git(self.tpl, "add", "-A"); git(self.tpl, "commit", "-q", "-m", "scripts")
        template_execs = [l.split("\t", 1)[1] for l in git(self.tpl, "ls-files", "-s").splitlines()
                          if l.startswith("100755")]
        self.assertEqual(len(template_execs), 3)
        env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.filemode", GIT_CONFIG_VALUE_0="false")
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(os, "chmod", lambda *a, **kw: None):
            self.assertEqual(self.run_cfg("--bundle-id", "com.acme.mytool"), 0)
        out = self.parent / "MyTool"
        modes = {l.split("\t", 1)[1]: l.split()[0] for l in git(out, "ls-files", "-s").splitlines()}
        expected = {"claude/githooks/commit-msg", "build-MyTool.sh", "tools/com.acme.mytool-run.sh"}
        self.assertEqual({p for p, m in modes.items() if m == "100755"}, expected)
        self.assertEqual(modes["AGENTS.md"], "120000")

    def test_manifest_header_is_renamed(self):
        # The real mtengine.caps names the app in its header comment; the
        # manifest is built from the template's text, so it must be renamed too.
        caps = self.tpl / "mtengine.caps"
        caps.write_text("# MTEngineSDLTemplateApp -- capability manifest\n" + caps.read_text())
        git(self.tpl, "commit", "-q", "-am", "header")
        self.assertEqual(self.run_cfg(), 0)
        text = (self.parent / "MyTool/mtengine.caps").read_text()
        self.assertTrue(text.startswith("# MyTool -- capability manifest\n"), text[:60])

    def test_tracked_but_ignored_file_is_committed(self):
        # The app is the template's tracked set: a file the template tracks
        # although its .gitignore matches it must reach the initial commit.
        (self.tpl / ".gitignore").write_text("ignored/\n")
        (self.tpl / "ignored").mkdir()
        (self.tpl / "ignored/kept.txt").write_text("kept\n")
        git(self.tpl, "add", ".gitignore"); git(self.tpl, "add", "-f", "ignored/kept.txt")
        git(self.tpl, "commit", "-q", "-m", "tracked but ignored")
        self.assertEqual(self.run_cfg(), 0)
        out = self.parent / "MyTool"
        self.assertIn("ignored/kept.txt", git(out, "ls-files").split())
        self.assertEqual(git(out, "status", "--porcelain"), "")

    def test_resolver_inputs_do_not_reach_the_app(self):
        (self.tpl / "mtengine-app-licenses.json").write_text("[]\n")
        git(self.tpl, "add", "mtengine-app-licenses.json"); git(self.tpl, "commit", "-q", "-m", "lic")
        removed = []
        real_unlink = Path.unlink
        def spy(self_, *a, **kw):
            removed.append(self_.name); return real_unlink(self_, *a, **kw)
        with mock.patch.object(Path, "unlink", spy):
            self.assertEqual(self.run_cfg(), 0)
        self.assertIn("mtengine.caps.check", removed)
        self.assertIn("mtengine-app-licenses.json", removed)
        self.assertFalse((self.parent / "MyTool/mtengine.caps.check").exists())
        self.assertTrue((self.parent / "MyTool/mtengine-app-licenses.json").exists())   # the tracked copy

    def test_hook_rejects_attribution_in_generated_app(self):
        self.run_cfg()
        out = self.parent / "MyTool"
        (out / "x.txt").write_text("x")
        git(out, "add", "x.txt")
        # An explicit identity: CI runners have none, and git checks the author
        # before it runs the commit-msg hook.
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                            "commit", "-m", "x\n\nCo-Authored-By: A <a@b>"], cwd=out, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("COMMIT REJECTED", r.stderr)

    def complete_stage(self):
        # The smallest tree self_check accepts; each case below breaks one thing.
        stage = Path(tempfile.mkdtemp(dir=self.parent))
        for rel, text in {"claude/githooks/commit-msg": "#!/bin/sh\n", ".gitattributes": "x\n",
                          "platform/MacOS/MyTool.icns": "i", "platform/Windows/MyTool/MyTool.ico": "i",
                          "platform/Linux/icons/hicolor/16x16/apps/com.acme.mytool.png": "i"}.items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_text(text)
        cfg.self_check(stage, "MyTool")   # the baseline passes, or every case below is meaningless
        return stage

    def test_self_check_failures(self):
        # Every failure listed in spec #4.4: token in contents, token in a path,
        # a marker, a template-only path, and each required output missing.
        content_cases = {
            "src/a.cpp": "still Template_App here\n",
            "src/TemplateAppThing.cpp": "clean contents\n",
            "docs/b.md": "<!-- template-only:begin -->\n",
            "configure.py": "#\n",
            "tests/configure/test_x.py": "#\n",
        }
        for rel, text in content_cases.items():
            stage = self.complete_stage()
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_text(text)
            with self.assertRaises(cfg.ConfigError, msg=rel) as e:
                cfg.self_check(stage, "MyTool")
            self.assertIn(rel, str(e.exception))
        for missing, named in {"claude/githooks/commit-msg": "commit-msg",
                               ".gitattributes": ".gitattributes",
                               "platform/MacOS/MyTool.icns": "MyTool.icns",
                               "platform/Windows/MyTool/MyTool.ico": "MyTool.ico",
                               "platform/Linux/icons/hicolor/16x16/apps/com.acme.mytool.png": "hicolor"}.items():
            stage = self.complete_stage()
            (stage / missing).unlink()
            with self.assertRaises(cfg.ConfigError, msg=missing) as e:
                cfg.self_check(stage, "MyTool")
            self.assertIn(named, str(e.exception))
        stage = Path(tempfile.mkdtemp(dir=self.parent))   # empty: every required output is reported
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.self_check(stage, "MyTool")
        self.assertIn("commit-msg", str(e.exception))

    def test_real_template_files_come_out_clean(self):
        # Spec #5: stripping and the rename are proved on the template's real
        # CLAUDE.md, README.md and project files, not only on the fixtures that
        # make_workspace() writes. These are the files where an off-form token
        # or a stray marker is most likely to hide.
        real = ["CLAUDE.md", "README.md", "platform/MacOS/Info.plist",
                "platform/MacOS/MTEngineSDLTemplateApp.xcodeproj/project.pbxproj",
                "platform/MacOS/MTEngineSDLTemplateApp.xcodeproj/xcshareddata/xcschemes/MTEngineSDLTemplateApp.xcscheme",
                "platform/Windows/MTEngineSDLTemplateApp.sln",
                "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.vcxproj"]
        stage = Path(tempfile.mkdtemp(dir=self.parent))
        for rel in real:
            src = cfg.HERE / rel if (cfg.HERE / rel).exists() else None
            self.assertIsNotNone(src, rel)
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            data = src.read_bytes()
            if rel.endswith(".md"):
                data = cfg.strip_template_only(data.decode("utf-8"), rel).encode("utf-8")
            (stage / rel).write_bytes(data)
        cfg.rename_tree(stage, cfg.token_map("MyTool"))
        for p in stage.rglob("*"):
            if p.is_file():
                rel = p.relative_to(stage).as_posix()
                self.assertNotRegex(rel, r"(?i)template_?app", rel)
                text = p.read_text()
                self.assertNotRegex(text, r"(?i)template_?app", rel)
                self.assertNotIn("template-only", text, rel)
        import plistlib
        plist = plistlib.loads((stage / "platform/MacOS/Info.plist").read_bytes())
        self.assertIn("CFBundleShortVersionString", plist)
        self.assertIn("MyTool.xcodeproj", str(next(stage.glob("platform/MacOS/*.xcodeproj"))))
        self.assertIn('"MyTool"', (stage / "platform/Windows/MyTool.sln").read_text())

    def test_failure_leaves_no_output(self):
        with mock.patch.object(cfg, "regenerate_guids", side_effect=cfg.ConfigError("boom")):
            self.assertNotEqual(self.run_cfg(), 0)
        self.assertFalse((self.parent / "MyTool").exists())
        self.assertEqual([p for p in self.parent.iterdir() if p.name.startswith(".MyTool")], [])

    def test_missing_git_identity_still_commits(self):
        # REMOVE the identity variables; setting them to "" would override the
        # configurator's -c user.name= fallback and git would die on an empty ident.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
            env.pop(k, None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.run_cfg(), 0)
        self.assertEqual(git(self.parent / "MyTool", "log", "-1", "--format=%an").strip(), "MyTool")

    def test_git_failure_keeps_output_and_reports(self):
        real = cfg._git
        def failing(cwd, *args, **kw):
            if args and args[0] == "commit":
                raise subprocess.CalledProcessError(1, ["git", *args], stderr="nope")
            return real(cwd, *args, **kw)
        err = io.StringIO()
        with mock.patch.object(cfg, "_git", side_effect=failing), redirect_stderr(err):
            self.assertNotEqual(self.run_cfg(), 0)
        self.assertTrue((self.parent / "MyTool/src/MyToolInit.cpp").exists())
        # Spec #4.4: the failing command and what is left to run by hand.
        msg = err.getvalue()
        self.assertIn("git failed: git commit", msg)
        self.assertIn("nope", msg)
        self.assertIn("run by hand:", msg)
        self.assertIn('git commit -m "Initial commit from MTEngineSDLTemplateApp', msg)

    def test_resolver_error_is_passed_through(self):
        # Spec #5: the engine resolver rejects the manifest; its message reaches
        # the user verbatim and nothing is left behind.
        msg = "mtcaps: MT_CAP_HTTPS=1 requires MT_CAP_HTTP=1 (fixture rejection)"
        (self.engine / "tools/mtcaps/mtcaps.py").write_text(
            f"import sys\nsys.stderr.write({msg!r} + '\\n')\nsys.exit(1)\n")
        o = cfg.resolve_options(cfg.parse_args(["MyTool", "--template", str(self.tpl), "--yes"]), interactive=False)
        cfg.validate(o)
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.generate(o)
        self.assertIn(msg, str(e.exception))
        self.assertFalse((self.parent / "MyTool").exists())
        self.assertEqual([p for p in self.parent.iterdir() if p.name.startswith(".MyTool")], [])
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.run_cfg(), 2)
        self.assertIn(msg, err.getvalue())

    def test_git_add_failure_lists_the_mode_fix(self):
        real = cfg._git
        def failing(cwd, *args, **kw):
            if args and args[0] == "add":
                raise subprocess.CalledProcessError(1, ["git", *args], stderr="nope")
            return real(cwd, *args, **kw)
        err = io.StringIO()
        with mock.patch.object(cfg, "_git", side_effect=failing), redirect_stderr(err):
            self.assertNotEqual(self.run_cfg(), 0)
        msg = err.getvalue()
        self.assertIn("git add -A --force", msg)
        self.assertIn("git update-index --chmod=+x -- claude/githooks/commit-msg", msg)

if __name__ == "__main__":
    unittest.main()
