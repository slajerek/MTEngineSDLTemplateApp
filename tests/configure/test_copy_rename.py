import io, os, contextlib, tempfile, unittest
from pathlib import Path
from helpers import load_configure, make_workspace, git

cfg = load_configure()

class CopyRenameTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.o = cfg.Options(name="MyTool", out=self.parent / "MyTool", title="My Tool", settings_folder="MyTool",
                             bundle_id="com.acme.mytool", menu="imgui", template=self.tpl, engine=self.engine)
        self.stage = Path(tempfile.mkdtemp(dir=self.parent))

    def test_template_only_paths_excluded_and_bytes_preserved(self):
        (self.tpl / "LICENSE").write_bytes(b"MIT\r\n")
        git(self.tpl, "commit", "-qam", "crlf")
        cfg.copy_tree(self.o, self.stage)
        for p in ("configure.py", "tests/configure/test_x.py", ".github/workflows/configure.yml", "specs/superpowers/specs/x.md"):
            self.assertFalse((self.stage / p).exists(), p)
        self.assertTrue((self.stage / ".github/workflows/build-linux.yml").exists())
        self.assertEqual((self.stage / "LICENSE").read_bytes(), b"MIT\r\n")
        self.assertTrue(os.access(self.stage / "claude/githooks/commit-msg", os.X_OK))

    def test_symlink_recreated_from_index(self):
        links, execs = cfg.copy_tree(self.o, self.stage)
        self.assertEqual(links, ["AGENTS.md"])
        self.assertEqual(execs, ["claude/githooks/commit-msg"])
        p = self.stage / "AGENTS.md"
        self.assertTrue(p.is_symlink() or p.read_text() == "CLAUDE.md")

    def test_dirty_template_warns_and_copies_working_tree(self):
        (self.tpl / "LICENSE").write_text("edited\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cfg.copy_tree(self.o, self.stage)
        self.assertIn("uncommitted", err.getvalue())
        self.assertEqual((self.stage / "LICENSE").read_text(), "edited\n")

    def test_strip_template_only(self):
        s = "a\n\n<!-- template-only:begin -->\nx\n<!-- template-only:end -->\n\n\nb\n"
        self.assertEqual(cfg.strip_template_only(s, "R.md"), "a\n\nb\n")
        crlf = s.replace("\n", "\r\n")
        self.assertEqual(cfg.strip_template_only(crlf, "R.md"), "a\r\n\r\nb\r\n")
        plain = "a\n\n\n\nb"   # no markers: returned exactly, blank runs included
        self.assertIs(cfg.strip_template_only(plain, "R.md"), plain)
        for bad in ("<!-- template-only:begin -->\nx\n",
                    "x\n<!-- template-only:end -->\n",
                    "<!-- template-only:begin -->\n<!-- template-only:begin -->\n<!-- template-only:end -->\n"):
            with self.assertRaises(cfg.ConfigError) as e:
                cfg.strip_template_only(bad, "R.md")
            self.assertIn("R.md:", str(e.exception))

    def test_rename_all_forms_in_paths_and_contents(self):
        cfg.copy_tree(self.o, self.stage)
        cfg.rename_tree(self.stage, cfg.token_map("MyTool"))
        self.assertTrue((self.stage / "src/MyToolInit.cpp").exists())
        self.assertTrue((self.stage / "platform/MacOS/MyTool.xcodeproj/project.pbxproj").exists())
        self.assertTrue((self.stage / "platform/Linux/com.example.mytool.desktop").exists())
        v = (self.stage / "src/MyToolVersion.h").read_text()
        self.assertIn("_MYTOOLVERSION_H_", v)
        self.assertIn("MYTOOL_VERSION", v)
        init = (self.stage / "src/MyToolInit.cpp").read_text()
        self.assertIn('"MyTool"', init)
        self.assertNotRegex(init, r"(?i)templateapp")

    def test_case_only_rename(self):
        (self.stage / "src").mkdir()
        (self.stage / "src/templateapp.txt").write_text("x")
        cfg.rename_tree(self.stage, [("templateapp", "TemplateApp")])   # differs only in case
        self.assertEqual(sorted(p.name for p in (self.stage / "src").iterdir()), ["TemplateApp.txt"])

if __name__ == "__main__":
    unittest.main()
