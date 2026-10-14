import unittest
from pathlib import Path
from helpers import load_configure, make_workspace

cfg = load_configure()

def ns(argv):
    return cfg.parse_args(argv)

class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.base = ["--template", str(self.tpl), "--yes"]

    def opts(self, *argv):
        o = cfg.resolve_options(ns([*argv, *self.base]), interactive=False)
        cfg.validate(o)
        return o

    def test_defaults(self):
        o = self.opts("MyTool")
        self.assertEqual(o.out, self.parent / "MyTool")
        self.assertEqual(o.title, "MyTool")
        self.assertEqual(o.settings_folder, "MyTool")
        self.assertEqual(o.bundle_id, "com.example.mytool")
        self.assertEqual(o.menu, "imgui")
        self.assertEqual(o.locales, ["en"])
        self.assertTrue(o.ci and o.git)

    def test_bad_names(self):
        for bad in ("myTool", "My-Tool", "1Tool", "TemplateAppX", "MyTEMPLATEAPP", "Templateapp"):
            with self.assertRaises(cfg.ConfigError, msg=bad):
                self.opts(bad)

    def test_token_in_other_values(self):
        # A value carrying the template token would fail the self-check with a
        # confusing leftover-token message; validation names the flag instead.
        for argv, flag in ((["--title", "TemplateApp Pro"], "--title"),
                           (["--settings-folder", "Template_App"], "--settings-folder"),
                           (["--bundle-id", "com.acme.templateapp"], "--bundle-id")):
            with self.assertRaises(cfg.ConfigError, msg=flag) as e:
                self.opts("MyTool", *argv)
            self.assertIn(flag, str(e.exception))

    def test_name_clashing_with_engine_header(self):
        # Name "Gui" generates CGuiMenu.h; give the fake engine a header of that name.
        (self.engine / "src/Engine/GUI/CGuiMenu.h").write_text("// engine\n")
        with self.assertRaises(cfg.ConfigError) as e:
            self.opts("Gui")
        self.assertIn("CGuiMenu.h", str(e.exception))

    def test_out_must_not_exist(self):
        (self.parent / "MyTool").mkdir()
        with self.assertRaises(cfg.ConfigError):
            self.opts("MyTool")

    def test_out_parent_must_be_engine_parent(self):
        with self.assertRaises(cfg.ConfigError) as e:
            self.opts("MyTool", "--out", str(self.parent / "sub" / "MyTool"))
        self.assertIn("MTEngineSDL", str(e.exception))

    def test_bundle_id_and_locales(self):
        with self.assertRaises(cfg.ConfigError):
            self.opts("MyTool", "--bundle-id", "Com.Example.X")
        with self.assertRaises(cfg.ConfigError):
            self.opts("MyTool", "--locales", "pl,../x")
        o = self.opts("MyTool", "--locales", "pl,pt-BR")
        self.assertEqual(o.locales, ["en", "pl", "pt-BR"])

    def test_no_tty_without_yes_names_the_flag(self):
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.resolve_options(ns(["--template", str(self.tpl)]), interactive=False)
        self.assertIn("name", str(e.exception))

    def test_interactive_prompts_use_answers_and_defaults(self):
        answers = iter(["MyTool", "", "My Tool", "", "", "hybrid", "MIDI", "pl", "", "y", "y"])
        o = cfg.resolve_options(ns(["--template", str(self.tpl)]), interactive=True, ask=lambda _p: next(answers))
        self.assertEqual((o.name, o.title, o.menu, o.caps, o.locales), ("MyTool", "My Tool", "hybrid", ["MIDI"], ["en", "pl"]))

    def test_template_must_be_git_clone(self):
        import shutil
        shutil.rmtree(self.tpl / ".git")
        with self.assertRaises(cfg.ConfigError) as e:
            self.opts("MyTool")
        self.assertIn("git clone", str(e.exception))

    def test_token_map(self):
        self.assertEqual(cfg.token_map("MyTool"),
                         [("MTEngineSDLTemplateApp", "MyTool"), ("TemplateApp", "MyTool"),
                          ("templateapp", "mytool"), ("TEMPLATEAPP", "MYTOOL")])

if __name__ == "__main__":
    unittest.main()
