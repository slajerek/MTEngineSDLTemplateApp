import json, unittest
from helpers import load_configure, make_workspace

cfg = load_configure()

class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.vocab = json.loads((self.engine / "tools/mtcaps/vocabulary.json").read_text())["capabilities"]
        self.text = (self.tpl / "mtengine.caps").read_text()

    def test_unknown_cap_lists_valid_names(self):
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.validate_caps(["NOPE"], self.vocab)
        self.assertIn("MIDI", str(e.exception))

    def test_enable_with_implications(self):
        out, notes = cfg.build_manifest(self.text, ["HTTPS"], self.vocab)
        self.assertIn("MT_CAP_HTTPS=1\n", out)
        self.assertIn("MT_CAP_HTTP=1\n", out)
        self.assertTrue(any("MT_CAP_HTTP" in n and "implied" in n for n in notes))
        self.assertIn("MT_CAP_MIDI=0\n", out)

    def test_missing_vocab_key_added_as_zero_with_comment(self):
        out, notes = cfg.build_manifest(self.text, [], self.vocab)
        self.assertIn("# New: Added later.\nMT_CAP_NEW=0\n", out)
        self.assertTrue(any("MT_CAP_NEW" in n for n in notes))

    def test_new_keys_go_before_licence_block(self):
        text = self.text.replace("MT_COMMERCIAL_BUILD=0", "# Licence tier. Keep 0.\nMT_COMMERCIAL_BUILD=0")
        out, _ = cfg.build_manifest(text, [], self.vocab)
        self.assertLess(out.index("MT_CAP_NEW=0"), out.index("# Licence tier."))

    def test_licence_keys_untouched(self):
        out, _ = cfg.build_manifest(self.text, ["MIDI"], self.vocab)
        self.assertIn("MT_COMMERCIAL_BUILD=0\n", out)
        self.assertIn("MT_PRIVATE_BUILD=0\n", out)

    def test_engine_absent_prints_clone_command(self):
        import shutil
        shutil.rmtree(self.engine)
        o = cfg.Options(name="MyTool", out=self.parent / "MyTool", title="t", settings_folder="f",
                        bundle_id="com.example.mytool", menu="imgui", template=self.tpl, engine=self.engine)
        with self.assertRaises(cfg.ConfigError) as e:
            cfg.locate_engine(o)
        self.assertIn("git clone https://github.com/slajerek/MTEngineSDL.git", str(e.exception))

if __name__ == "__main__":
    unittest.main()
