import json, re, tempfile, unittest
import importlib.util
from pathlib import Path
from helpers import load_configure, make_workspace

cfg = load_configure()

class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.o = cfg.Options(name="MyTool", out=self.parent / "MyTool", title="My Tool", settings_folder="MyToolData",
                             bundle_id="com.acme.mytool", menu="hybrid", locales=["en", "pl"], ci=False,
                             template=self.tpl, engine=self.engine)
        self.stage = Path(tempfile.mkdtemp(dir=self.parent))
        cfg.copy_tree(self.o, self.stage)
        cfg.rename_tree(self.stage, cfg.token_map("MyTool"))

    def test_values(self):
        cfg.apply_values(self.o, self.stage, "MT_CAP_MIDI=1\n")
        init = (self.stage / "src/MyToolInit.cpp").read_text()
        self.assertIn('kWindowTitle    = "My Tool"', init)
        self.assertIn('kSettingsFolder = "MyToolData"', init)
        self.assertIn('kAppId = "com.acme.mytool"', init)
        self.assertIn("EMTMenuBarMode::Native", init)
        pbx = (self.stage / "platform/MacOS/MyTool.xcodeproj/project.pbxproj").read_text()
        self.assertEqual(pbx.count("PRODUCT_BUNDLE_IDENTIFIER = com.acme.mytool;"), 2)
        self.assertTrue((self.stage / "platform/Linux/com.acme.mytool.desktop").exists())
        desktop = (self.stage / "platform/Linux/com.acme.mytool.desktop").read_text()
        self.assertIn("Icon=com.acme.mytool", desktop)
        # The title is what the user sees in the launcher, the Dock and the app menu.
        self.assertIn("Name=My Tool\n", desktop)
        plist = (self.stage / "platform/MacOS/Info.plist").read_text()
        self.assertIn("<key>CFBundleName</key>\n\t<string>My Tool</string>", plist)
        self.assertIn("<key>CFBundleDisplayName</key>\n\t<string>My Tool</string>", plist)
        self.assertTrue((self.stage / "platform/Linux/icons/hicolor/16x16/apps/com.acme.mytool.png").exists())
        self.assertEqual((self.stage / "mtengine.caps").read_bytes(), b"MT_CAP_MIDI=1\n")
        self.assertFalse((self.stage / ".github/workflows").exists())
        # A custom bundle id reaches every file that names the default one.
        self.assertIn("com.acme.mytool.desktop", (self.stage / "CMakeLists.txt").read_text())
        self.assertIn('APP_ID = "com.acme.mytool"', (self.stage / "tools/icons/gen-icons.py").read_text())
        self.assertFalse(any("com.example.mytool" in p.name for p in self.stage.rglob("*")))

    def test_title_is_escaped_for_the_plist(self):
        o = cfg.Options(**{**self.o.__dict__, "title": "R&D <Tool>"})
        cfg.apply_values(o, self.stage, "MT_CAP_MIDI=1\n")
        plist = (self.stage / "platform/MacOS/Info.plist").read_text()
        self.assertEqual(plist.count("<string>R&amp;D &lt;Tool&gt;</string>"), 2)
        self.assertIn("Name=R&D <Tool>\n", (self.stage / "platform/Linux/com.acme.mytool.desktop").read_text())

    def test_line_endings_untouched(self):
        cfg.apply_values(self.o, self.stage, "MT_CAP_MIDI=1\r\n")
        self.assertEqual((self.stage / "platform/Windows/MyTool.rc.crlf").read_bytes(),
                         b'IDI_ICON1 ICON "MyTool.ico"\r\n')
        self.assertEqual((self.stage / "mtengine.caps").read_bytes(), b"MT_CAP_MIDI=1\r\n")
        self.assertNotIn(b"\r", (self.stage / "src/MyToolInit.cpp").read_bytes())

    def test_locale_copy_meta(self):
        cfg.apply_values(self.o, self.stage, "x\n")
        pl = json.loads((self.stage / "assets/locale/pl.json").read_text())
        self.assertEqual(pl["meta"]["locale"], "pl")
        self.assertEqual(pl["meta"]["displayName"], "pl")
        self.assertEqual(pl["meta"]["fallbacks"], ["en"])
        self.assertEqual(pl["strings"]["app.title"], "My Tool")
        en = json.loads((self.stage / "assets/locale/en.json").read_text())
        self.assertEqual(en["strings"]["app.title"], "My Tool")

    def test_guids(self):
        cfg.regenerate_guids(self.stage, "MyTool")
        sln = (self.stage / "platform/Windows/MyTool.sln").read_text()
        vcx = (self.stage / "platform/Windows/MyTool/MyTool.vcxproj").read_text()
        self.assertNotIn("11111111-2222-3333-4444-555555555555", sln + vcx)
        self.assertNotIn("99999999-8888-7777-6666-555555555555", sln)
        self.assertIn("{E93D3B41-0000-0000-0000-000000000000}", sln)
        self.assertIn("{E93D3B41-0000-0000-0000-000000000000}", vcx)
        new = re.search(r"<ProjectGuid>(\{[0-9A-F-]+\})</ProjectGuid>", vcx).group(1)
        self.assertEqual(sln.count(new), 2)

    def test_template_config(self):
        cfg.write_template_config(self.o, self.stage, "abc123")
        tc = json.loads((self.stage / "template-config.json").read_text())
        self.assertEqual(tc["options"]["name"], "MyTool")
        self.assertEqual(tc["engine_sha"], "abc123")
        self.assertRegex(tc["template_sha"], r"^[0-9a-f]{40}$")

    def test_bundle_id_with_default_as_prefix(self):
        bid = self.o.bundle_id = "com.example.mytool.pro"
        cfg.apply_values(self.o, self.stage, "x\n")
        init = (self.stage / "src/MyToolInit.cpp").read_text()
        self.assertIn(f'kAppId = "{bid}";', init)
        pbx = (self.stage / "platform/MacOS/MyTool.xcodeproj/project.pbxproj").read_text()
        self.assertEqual(pbx.count(f"PRODUCT_BUNDLE_IDENTIFIER = {bid};"), 2)
        desk = self.stage / f"platform/Linux/{bid}.desktop"
        self.assertTrue(desk.exists())
        text = desk.read_text()
        self.assertIn(f"Icon={bid}\n", text)
        self.assertIn(f"StartupWMClass={bid}\n", text)
        self.assertTrue((self.stage / f"platform/Linux/icons/hicolor/16x16/apps/{bid}.png").exists())
        names = "".join(p.name for p in self.stage.rglob("*"))
        self.assertNotIn(bid + ".pro", names)
        cm = (self.stage / "CMakeLists.txt").read_text()
        self.assertIn(f"{bid}.desktop", cm)
        self.assertNotIn(bid + ".pro", cm)


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow not installed")
class IconTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.o = cfg.Options(name="MyTool", out=self.parent / "MyTool", title="My Tool", settings_folder="MyToolData",
                             bundle_id="com.acme.mytool", menu="imgui", locales=["en"], ci=False,
                             template=self.tpl, engine=self.engine)
        self.stage = Path(tempfile.mkdtemp(dir=self.parent))
        cfg.copy_tree(self.o, self.stage)
        cfg.rename_tree(self.stage, cfg.token_map("MyTool"))
        # The fixture's gen-icons.py is a stub: use the real one, renamed like the template.
        real = (Path(__file__).resolve().parents[2] / "tools/icons/gen-icons.py").read_text()
        for old, new in cfg.token_map("MyTool"):
            real = real.replace(old, new)
        (self.stage / "tools/icons/gen-icons.py").write_text(real)

    def _png(self, size):
        from PIL import Image
        p = self.parent / f"icon{size}.png"
        Image.new("RGBA", (size, size), (200, 30, 30, 255)).save(p)
        return p

    def test_custom_icon(self):
        self.o.icon = self._png(1024)
        cfg.apply_values(self.o, self.stage, "x\n")
        icns = self.stage / "platform/MacOS/MyTool.icns"
        ico = self.stage / "platform/Windows/MyTool/MyTool.ico"
        png = self.stage / "platform/Linux/icons/hicolor/256x256/apps/com.acme.mytool.png"
        for p in (icns, ico, png):
            self.assertTrue(p.exists(), p)
            self.assertNotEqual(p.read_bytes(), b"PNG")
        self.assertTrue(icns.read_bytes().startswith(b"icns"))
        self.assertGreater(ico.stat().st_size, 100)
        self.assertFalse(any("com.example" in p.name for p in self.stage.rglob("*")))

    def test_small_icon_rejected(self):
        self.o.icon = self._png(512)
        with self.assertRaises(cfg.ConfigError) as cm:
            cfg.apply_values(self.o, self.stage, "x\n")
        self.assertIn("1024", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
