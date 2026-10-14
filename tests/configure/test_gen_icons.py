import importlib.util, struct, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from PIL import Image
except ImportError:  # Pillow is a dev-only dependency of the icon script
    Image = None

def load_module():
    spec = importlib.util.spec_from_file_location("gen_icons", ROOT / "tools/icons/gen-icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

@unittest.skipIf(Image is None, "Pillow not installed")
class GenIconsTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.tmp = Path(tempfile.mkdtemp())
        self.master = Image.new("RGBA", (1024, 1024), (40, 90, 200, 255))

    def test_icns_has_png_entries_for_every_size(self):
        out = self.tmp / "a.icns"
        self.mod.write_icns(out, self.master)
        data = out.read_bytes()
        self.assertEqual(data[:4], b"icns")
        self.assertEqual(struct.unpack(">I", data[4:8])[0], len(data))
        types, pos = set(), 8
        while pos < len(data):
            t, n = data[pos:pos+4], struct.unpack(">I", data[pos+4:pos+8])[0]
            self.assertEqual(data[pos+8:pos+16], b"\x89PNG\r\n\x1a\n")
            types.add(t); pos += n
        self.assertEqual(types, {b"icp4", b"icp5", b"icp6", b"ic07", b"ic08", b"ic09", b"ic10",
                                 b"ic11", b"ic12", b"ic13", b"ic14"})

    def test_ico_sizes(self):
        out = self.tmp / "a.ico"
        self.mod.write_ico(out, self.master)
        with Image.open(out) as ico:
            self.assertEqual(set(ico.info["sizes"]),
                             {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)})

    def test_hicolor_tree(self):
        self.mod.write_hicolor(self.tmp, "com.example.x", self.master)
        for s in (16, 22, 24, 32, 48, 64, 128, 256, 512):
            p = self.tmp / f"{s}x{s}/apps/com.example.x.png"
            self.assertTrue(p.exists(), p)
            with Image.open(p) as im:
                self.assertEqual(im.size, (s, s))

    def test_rejects_non_square_and_small_master(self):
        for size in ((1024, 512), (512, 512)):
            p = self.tmp / f"m{size[0]}x{size[1]}.png"
            Image.new("RGBA", size).save(p)
            with self.assertRaises(SystemExit):
                self.mod.load_master(p)

if __name__ == "__main__":
    unittest.main()
