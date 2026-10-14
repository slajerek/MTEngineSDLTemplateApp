#!/usr/bin/env python3
"""Register a source file in all three MTEngineSDLTemplateApp build systems at once.

CLAUDE.md requires CMakeLists.txt, the Xcode project, and the VS project (plus
its .filters) to be updated in the SAME commit whenever a source file is added,
removed, or renamed. All three use explicit file lists with no auto-discovery,
so doing it by hand is four separate edits and an easy thing to half-finish.

Usage (from repo root):
    python3 tools/add_source_file.py src/Views/CMyView.cpp

Pass the .cpp; the matching .h is picked up automatically when it exists.
Header-only files may be passed directly -- they are registered everywhere
except CMake (which needs no entry) and the Xcode Sources build phase (headers
are not compiled).

Idempotent: re-running for an already-registered file is a no-op.

The Xcode UUID is derived from a hash of the filename, so repeated runs produce
the same identifier and a re-run never creates a duplicate object.
"""

import hashlib
import os
import sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[1])

CMAKE = os.path.join(REPO, "CMakeLists.txt")
PBXPROJ = os.path.join(REPO, "platform/MacOS/MTEngineSDLTemplateApp.xcodeproj/project.pbxproj")
VCXPROJ = os.path.join(REPO, "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.vcxproj")
FILTERS = os.path.join(REPO, "platform/Windows/MTEngineSDLTemplateApp/MTEngineSDLTemplateApp.vcxproj.filters")

# Anchor file that already exists in every build system. New entries are
# inserted directly after it, which keeps the lists grouped and the diffs small.
# The CMake, vcxproj and .filters anchors are the lines containing ANCHOR_REL
# (with backslashes on Windows); the Xcode anchor is its file name.
ANCHOR_REL = "src/Tests/CTestAppStartup.cpp"
ANCHOR = os.path.basename(ANCHOR_REL)
ANCHOR_WIN = ANCHOR_REL.replace("/", "\\")


def uuid_for(name, salt):
    """Deterministic 24-hex-char Xcode object identifier."""
    h = hashlib.sha1((name + "|" + salt).encode()).hexdigest().upper()
    return h[:24]


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def add_cmake(rel):
    s = read(CMAKE)
    entry = '    "${CMAKE_CURRENT_SOURCE_DIR}/%s"' % rel
    if entry in s:
        return False
    anchor = [l for l in s.splitlines() if ANCHOR_REL in l]
    if not anchor:
        sys.exit("CMake anchor not found: " + ANCHOR_REL)
    write(CMAKE, s.replace(anchor[0], anchor[0] + "\n" + entry, 1))
    return True


def add_xcode(rel, is_header, group_hint):
    s = read(PBXPROJ)
    name = os.path.basename(rel)
    if "/* %s */ = {isa = PBXFileReference" % name in s:
        return False

    ref = uuid_for(name, "ref")
    xcode_rel = "../../" + rel
    ftype = "sourcecode.c.h" if is_header else "sourcecode.cpp.cpp"

    fileref = ('\t\t%s /* %s */ = {isa = PBXFileReference; fileEncoding = 4; '
               'lastKnownFileType = %s; name = %s; path = %s; '
               'sourceTree = "<group>"; };' % (ref, name, ftype, name, xcode_rel))

    a_ref_line = [l for l in s.splitlines()
                  if "/* %s */ = {isa = PBXFileReference" % ANCHOR in l][0]
    s = s.replace(a_ref_line, a_ref_line + "\n" + fileref, 1)

    # PBXGroup children -- insert next to the anchor's group entry.
    a_grp = [l for l in s.splitlines()
             if l.strip().startswith(a_ref_line.strip().split()[0])
             and l.strip().endswith("*/,")]
    if a_grp:
        grp_line = a_grp[0]
        s = s.replace(grp_line,
                      grp_line + "\n\t\t\t\t%s /* %s */," % (ref, name), 1)

    if not is_header:
        build = uuid_for(name, "build")
        bf = ('\t\t%s /* %s in Sources */ = {isa = PBXBuildFile; fileRef = '
              '%s /* %s */; };' % (build, name, ref, name))
        a_bf = [l for l in s.splitlines()
                if "/* %s in Sources */ = {isa = PBXBuildFile" % ANCHOR in l][0]
        s = s.replace(a_bf, a_bf + "\n" + bf, 1)

        a_src = [l for l in s.splitlines()
                 if "/* %s in Sources */," % ANCHOR in l][0]
        s = s.replace(a_src,
                      a_src + "\n\t\t\t\t%s /* %s in Sources */," % (build, name), 1)

    write(PBXPROJ, s)
    return True


def add_vs(rel, is_header, group_hint):
    win = "..\\..\\..\\" + rel.replace("/", "\\")
    tag = "ClInclude" if is_header else "ClCompile"

    s = read(VCXPROJ)
    if win in s:
        return False
    anchor = [l for l in s.splitlines() if ANCHOR_WIN in l]
    if not anchor:
        sys.exit("vcxproj anchor not found: " + ANCHOR_WIN)
    s = s.replace(anchor[0],
                  anchor[0] + '\n    <%s Include="%s" />' % (tag, win), 1)
    write(VCXPROJ, s)

    f = read(FILTERS)
    if win not in f:
        idx = f.find(ANCHOR_WIN)
        if idx < 0:
            sys.exit("filters anchor not found")
        end = f.find("</ClCompile>", idx) + len("</ClCompile>")
        block = ('\n    <%s Include="%s">\n      <Filter>%s</Filter>\n    </%s>'
                 % (tag, win, group_hint, tag))
        f = f[:end] + block + f[end:]
        write(FILTERS, f)
    return True


def register(rel):
    is_header = rel.endswith(".h")
    # VS filter names mirror the on-disk layout, e.g. "Source Files\src\Views".
    group_hint = "Source Files\\" + os.path.dirname(rel).replace("/", "\\")

    changed = []
    if not is_header and add_cmake(rel):
        changed.append("cmake")
    if add_xcode(rel, is_header, group_hint):
        changed.append("xcode")
    if add_vs(rel, is_header, group_hint):
        changed.append("vs")
    print("%s: %s" % (rel, ", ".join(changed) if changed else "already registered"))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        rel = os.path.relpath(os.path.abspath(arg), REPO).replace("\\", "/")
        if not os.path.exists(os.path.join(REPO, rel)):
            sys.exit("no such file: " + rel)
        register(rel)
        if rel.endswith(".cpp"):
            hdr = rel[:-4] + ".h"
            if os.path.exists(os.path.join(REPO, hdr)):
                register(hdr)


if __name__ == "__main__":
    main()
