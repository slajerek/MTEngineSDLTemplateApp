#!/usr/bin/env python3
"""Regenerate every platform icon from tools/icons/master.png.

    python3 tools/icons/gen-icons.py                 # from tools/icons/master.png
    python3 tools/icons/gen-icons.py --master my.png

The master is a square PNG, at least 1024x1024, full-bleed artwork.
Transparency is allowed. It lives outside assets/ because assets/ ships inside
the app. Outputs are committed; nothing in the build runs this script. Needs
Pillow (python3 -m pip install --user Pillow).

  macOS    platform/MacOS/MTEngineSDLTemplateApp.icns    PNG-encoded entries, artwork inset
                                                         to Apple's 824/1024 grid
  Windows  platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.ico
                                                         the only ICON in the .rc; SDL3
                                                         takes the first RT_GROUP_ICON
  Linux    platform/Linux/icons/hicolor/<s>x<s>/apps/com.example.templateapp.png
                                                         Icon= in the .desktop file
"""
import argparse, io, struct, sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("gen-icons.py needs Pillow: python3 -m pip install --user Pillow")

ROOT = Path(__file__).resolve().parents[2]
MASTER = Path(__file__).resolve().parent / "master.png"
APP_ID = "com.example.templateapp"
MAC_ICNS = ROOT / "platform/MacOS/MTEngineSDLTemplateApp.icns"
WIN_ICO = ROOT / "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.ico"
LINUX_HICOLOR = ROOT / "platform/Linux/icons/hicolor"

MAC_INSET = 824 / 1024
ICNS_TYPES = [(b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128), (b"ic08", 256),
              (b"ic09", 512), (b"ic10", 1024), (b"ic11", 32), (b"ic12", 64), (b"ic13", 256),
              (b"ic14", 512)]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
HICOLOR_SIZES = [16, 22, 24, 32, 48, 64, 128, 256, 512]


def load_master(path):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if w != h:
        raise SystemExit(f"{path}: master must be square, got {w}x{h}")
    if w < 1024:
        raise SystemExit(f"{path}: master must be at least 1024x1024, got {w}x{h}")
    return img


def resized(master, size, inset=1.0):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = max(1, round(size * inset))
    art = master.resize((inner, inner), Image.LANCZOS)
    off = (size - inner) // 2
    canvas.alpha_composite(art, (off, off))
    return canvas


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_icns(path, master):
    chunks = b""
    for kind, size in ICNS_TYPES:
        data = png_bytes(resized(master, size, MAC_INSET))
        chunks += kind + struct.pack(">I", len(data) + 8) + data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def write_ico(path, master):
    path.parent.mkdir(parents=True, exist_ok=True)
    resized(master, 256).save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])


def write_hicolor(root, app_id, master):
    for s in HICOLOR_SIZES:
        out = Path(root) / f"{s}x{s}" / "apps" / f"{app_id}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        resized(master, s).save(out, format="PNG")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", type=Path, default=MASTER)
    args = ap.parse_args(argv)
    master = load_master(args.master)
    write_icns(MAC_ICNS, master)
    write_ico(WIN_ICO, master)
    write_hicolor(LINUX_HICOLOR, APP_ID, master)
    print(f"wrote {MAC_ICNS.relative_to(ROOT)}, {WIN_ICO.relative_to(ROOT)}, {LINUX_HICOLOR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
