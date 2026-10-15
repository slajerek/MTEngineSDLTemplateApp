"""The full-screen wizard behind ./configure.py, in the style of menuconfig.

Standard library only: curses. Three screens -- a form, a scrolling
capability checklist with a description panel, and a summary -- and nothing
else: every value it collects goes through the same Options and validate()
as the command-line path, so the two cannot disagree about what is valid.

The Wizard class is pure: it takes keys and draws on any object with
addstr/getmaxyx, so tests drive it end to end on a fake screen. Only run()
touches curses itself.
"""
import curses, textwrap
from pathlib import Path

# --------------------------------------------------------------------------
# Keys. get_wch() returns a str for a character and an int for a special key.

UP, DOWN, LEFT, RIGHT = curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT
PGUP, PGDN, HOME, END = curses.KEY_PPAGE, curses.KEY_NPAGE, curses.KEY_HOME, curses.KEY_END
BACKSPACE_KEYS = (curses.KEY_BACKSPACE, "\x7f", "\b", "\x08")
DELETE = curses.KEY_DC
ENTER_KEYS = ("\n", "\r", curses.KEY_ENTER)
ESC = "\x1b"
TAB, BTAB = "\t", curses.KEY_BTAB
RESIZE = curses.KEY_RESIZE

MIN_W, MIN_H = 60, 18

# --------------------------------------------------------------------------
# Capabilities


def first_sentence(text):
    text = " ".join(text.split())
    end = text.find(". ")
    return text if end < 0 else text[:end + 1]


class CapsModel:
    """Which capabilities are on, and why.

    base    on in every app (the template's mtengine.caps); locked here, and
            turned off later in mtengine.caps if ever needed
    chosen  what the user ticked
    implied what something on pulls in (HTTPS -> HTTP); locked while it is
    """

    def __init__(self, vocab, base_on=(), chosen=()):
        self.vocab = vocab
        self.keys = sorted(vocab, key=lambda k: vocab[k].get("short", k))
        self.base = {k for k in base_on if k in vocab}
        self.chosen = {k for k in chosen if k in vocab} - self.base

    def short(self, key):
        return self.vocab[key].get("short", key.removeprefix("MT_CAP_"))

    def _closure(self, roots):
        seen, stack = set(), list(roots)
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            stack.extend(self.vocab.get(k, {}).get("implies", []))
        return seen

    def on(self):
        return self._closure(self.base | self.chosen)

    def state(self, key):
        if key in self.base:
            return "base"
        if key in self.chosen:
            return "on"
        if key in self.on():
            return "implied"
        return "off"

    def implied_by(self, key):
        return sorted(self.short(k) for k in self.base | self.chosen
                      if k != key and key in self._closure({k}))

    def toggle(self, key):
        """Flip a capability. Returns None, or why it cannot change."""
        st = self.state(key)
        if st == "base":
            return f"{self.short(key)} is on in every app; turn it off later in mtengine.caps"
        if st == "implied":
            return f"{self.short(key)} is required by {', '.join(self.implied_by(key))}"
        if st == "on":
            self.chosen.discard(key)
        else:
            self.chosen.add(key)
        return None

    def selected(self):
        """What goes to Options.caps: the ticked ones, without MT_CAP_."""
        return [k.removeprefix("MT_CAP_") for k in self.keys if k in self.chosen]

    def details(self, key):
        """The description panel's lines (unwrapped paragraphs)."""
        cap = self.vocab[key]
        out = [" ".join(cap.get("description", "").split())]
        st = self.state(key)
        out.append({"base": "On in every app (the template's default).",
                    "on": "On.",
                    "implied": f"On: required by {', '.join(self.implied_by(key))}.",
                    "off": "Off."}[st])
        implies = [self.short(k) for k in cap.get("implies", [])]
        if implies:
            out.append("Also turns on: " + ", ".join(implies) + ".")
        deps = cap.get("dependencies", [])
        if deps:
            out.append("Libraries: " + "; ".join(f"{d.get('name')} ({d.get('licence')})" for d in deps) + ".")
            size = sum(d.get("size_mb", 0) or 0 for d in deps)
            if size:
                out.append(f"First build downloads about {size:g} MB.")
        effect = cap.get("commercial", {}).get("effect")
        if effect == "capability-off":
            out.append("Commercial builds turn it off.")
        elif effect == "variant":
            out.append("Commercial builds use a different variant of it.")
        return out


def base_caps(template):
    """The capabilities the template's mtengine.caps turns on."""
    path = Path(template) / "mtengine.caps"
    on = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("MT_CAP_") and line.endswith("=1"):
            on.append(line.split("=", 1)[0])
    return on


def scroll_top(cursor, top, height, count):
    """Keep the cursor inside a window of `height` rows over `count` items."""
    if height <= 0:
        return 0
    if cursor < top:
        top = cursor
    elif cursor >= top + height:
        top = cursor - height + 1
    return max(0, min(top, max(0, count - height)))

# --------------------------------------------------------------------------
# The form


class Field:
    def __init__(self, key, label, kind, help, choices=None):
        self.key, self.label, self.kind, self.help, self.choices = key, label, kind, help, choices


FIELDS = [
    Field("name", "App name", "text", "PascalCase letters and digits, e.g. MyTool. Classes and files are named after it."),
    Field("title", "Title", "text", "What the user sees: window title, About, the macOS app menu and Dock, the Linux launcher."),
    Field("settings_folder", "Settings folder", "text", "Folder for the app's settings, in the user's settings directory."),
    Field("bundle_id", "Bundle id", "text", "Lowercase reverse-DNS, e.g. com.example.mytool."),
    Field("out", "Output directory", "text", "Must be next to this template and MTEngineSDL."),
    Field("menu", "Menu bar", "choice", "imgui: an ImGui menu bar everywhere. hybrid: native on macOS and Windows, ImGui on Linux.",
          ["imgui", "hybrid"]),
    Field("engine_ref", "Engine branch (CI)", "text",
          "MTENGINE_REF: the engine branch, tag or SHA the app's CI clones from GitHub. devel is the live branch."),
    Field("locales", "Locales", "text", "Comma-separated tags, e.g. en,pl,pt-BR. en is always included; others start as English copies."),
    Field("icon", "Icon PNG", "text", "A square PNG of at least 1024 px (needs Pillow). Empty: the placeholder icon."),
    Field("ci", "GitHub workflows", "bool", "Build and release workflows for macOS, Linux and Windows."),
    Field("git", "git init + commit", "bool", "Create the repository with a first commit and the commit-msg hook."),
    Field("next", "Next", "button", "Check the values and go on to the capabilities."),
]
NEXT_KEY = "\x0e"   # Ctrl-N: Next from anywhere on the form
DERIVED = ("title", "settings_folder", "bundle_id", "out")   # follow the name until edited


def derived_value(key, name, template):
    if key == "title" or key == "settings_folder":
        return name
    if key == "bundle_id":
        return f"com.example.{name.lower()}" if name else ""
    if key == "out":
        return str(Path(template).parent / name) if name else ""
    return ""


def field_error(cfg, key, values, template):
    """The one-line error for a field, or None. The full validate() runs on Next."""
    v = values[key]
    if key == "name":
        if not cfg.NAME_RE.match(v):
            return "PascalCase letters and digits, starting with a capital"
        if cfg.LEFTOVER_RE.search(v):
            return "must not contain the template's own token"
    elif key in ("title", "settings_folder", "bundle_id") and cfg.LEFTOVER_RE.search(v):
        return "must not contain the template's own token"
    if key == "title":
        if not v.strip():
            return "must not be empty"
        if any(ord(c) < 32 for c in v):
            return "one line, without control characters"
    elif key == "settings_folder" and not cfg.FOLDER_RE.match(v):
        return "letters, digits, '.', '_', '-' only"
    elif key == "bundle_id" and not cfg.BUNDLE_RE.match(v):
        return "lowercase reverse-DNS, e.g. com.example.mytool"
    elif key == "out":
        p = Path(v).expanduser()
        if not v:
            return "required"
        if p.resolve().parent != Path(template).resolve().parent:
            return f"must be in {Path(template).resolve().parent}"
        if p.exists():
            return "already exists"
    elif key == "engine_ref" and not cfg.ENGINE_REF_RE.match(v):
        return "a branch (origin/devel), tag or SHA"
    elif key == "locales":
        bad = [t for t in split_list(v) if not cfg.LOCALE_RE.match(t)]
        if bad:
            return f"not a locale tag: {', '.join(bad)}"
    elif key == "icon" and v and not Path(v).expanduser().is_file():
        return "file not found"
    return None


def split_list(s):
    return [x.strip() for x in s.split(",") if x.strip()]


def to_options(cfg, values, caps, template, engine):
    locales = split_list(values["locales"])
    if "en" in locales:
        locales.remove("en")
    locales.insert(0, "en")
    icon = values["icon"].strip()
    return cfg.Options(name=values["name"], out=Path(values["out"]).expanduser().resolve(), title=values["title"],
                       settings_folder=values["settings_folder"], bundle_id=values["bundle_id"], menu=values["menu"],
                       caps=caps.selected(), locales=locales,
                       icon=Path(icon).expanduser().resolve() if icon else None,
                       ci=values["ci"], git=values["git"], template=Path(template), engine=Path(engine),
                       engine_ref=values["engine_ref"])

# --------------------------------------------------------------------------
# The wizard


class Wizard:
    """Screens: form -> caps -> summary. done is set when the user creates or quits."""

    def __init__(self, cfg, values, caps, template, engine, touched=()):
        self.cfg, self.values, self.caps = cfg, values, caps
        self.template, self.engine = template, engine
        self.touched = set(touched)   # derived fields given on the command line or edited
        self.screen = "form"
        self.focus = 0          # form field
        self.editing = None     # cursor position while a text field is being edited
        self.cap_cursor = self.cap_top = 0
        self.sum_top = 0
        self.message = ""       # one-line status (errors, locked capabilities)
        self.searching = None   # the search prompt's text while typing it
        self.last_search = ""
        self.confirm_quit = False
        self.tried_next = False
        self.result = None      # Options on create
        self.done = False

    # ---- input --------------------------------------------------------

    def handle(self, key):
        if key == RESIZE:
            return
        if self.confirm_quit:
            self.confirm_quit = False
            if key in ("y", "Y"):
                self.done = True
            else:
                self.message = ""
            return
        if self.searching is not None:
            return self._search_key(key)
        if self.editing is not None:
            return self._edit_key(key)
        getattr(self, f"_{self.screen}_key")(key)

    def _ask_quit(self):
        self.confirm_quit = True
        self.message = "Quit without creating the app? (y/n)"

    def _form_key(self, key):
        f = FIELDS[self.focus]
        if key in (UP, BTAB):
            self.focus = (self.focus - 1) % len(FIELDS)
        elif key in (DOWN, TAB):
            self.focus = (self.focus + 1) % len(FIELDS)
        elif key in (HOME,):
            self.focus = 0
        elif key in (END,):
            self.focus = len(FIELDS) - 1
        elif key == ESC:
            self._ask_quit()
        elif key == NEXT_KEY or (f.kind == "button" and key in (" ", *ENTER_KEYS)):
            self._next_from_form()
        elif f.kind == "text" and key in ENTER_KEYS:
            self.editing = len(self.values[f.key])
            self.message = ""
        elif f.kind == "choice" and key in (" ", LEFT, RIGHT, *ENTER_KEYS):
            i = f.choices.index(self.values[f.key])
            self.values[f.key] = f.choices[(i + (-1 if key == LEFT else 1)) % len(f.choices)]
        elif f.kind == "bool" and key in (" ", *ENTER_KEYS):
            self.values[f.key] = not self.values[f.key]
        elif f.kind == "text" and isinstance(key, str) and key.isprintable():
            # Typing on a text field starts editing it at the end.
            self.editing = len(self.values[f.key])
            self.message = ""
            self._edit_key(key)

    def _set(self, key, value):
        if self.values[key] == value:   # moving the cursor is not an edit
            return
        self.values[key] = value
        if key == "name":
            for d in DERIVED:
                if d not in self.touched:
                    self.values[d] = derived_value(d, value, self.template)
        elif key in DERIVED:
            self.touched.add(key)

    def _edit_key(self, key):
        f = FIELDS[self.focus]
        v, pos = self.values[f.key], self.editing
        if key in ENTER_KEYS or key == ESC:      # done; stay on the field
            self.editing = None
            return
        if key in (TAB, DOWN, UP, BTAB):          # done; move
            self.editing = None
            self.focus = (self.focus + (-1 if key in (UP, BTAB) else 1)) % len(FIELDS)
            return
        if key == NEXT_KEY:
            self.editing = None
            self._next_from_form()
            return
        if key in BACKSPACE_KEYS and pos > 0:
            v, pos = v[:pos - 1] + v[pos:], pos - 1
        elif key == DELETE:
            v = v[:pos] + v[pos + 1:]
        elif key == LEFT:
            pos = max(0, pos - 1)
        elif key == RIGHT:
            pos = min(len(v), pos + 1)
        elif key == HOME or key == "\x01":
            pos = 0
        elif key == END or key == "\x05":
            pos = len(v)
        elif key == "\x15":                       # Ctrl-U clears the field
            v, pos = "", 0
        elif isinstance(key, str) and key.isprintable():
            v, pos = v[:pos] + key + v[pos:], pos + 1
        self.editing = pos
        self._set(f.key, v)

    def form_errors(self):
        return {f.key: e for f in FIELDS if f.kind == "text"
                for e in [field_error(self.cfg, f.key, self.values, self.template)] if e}

    def _next_from_form(self):
        self.tried_next = True
        errors = self.form_errors()
        if errors:
            first = next(i for i, f in enumerate(FIELDS) if f.key in errors)
            self.focus = first
            self.message = f"{FIELDS[first].label}: {errors[FIELDS[first].key]}"
            return
        try:
            self.cfg.validate(self.options())
        except self.cfg.ConfigError as e:
            self.message = str(e)
            return
        self.message = ""
        self.screen = "caps"

    def options(self):
        return to_options(self.cfg, self.values, self.caps, self.template, self.engine)

    def _caps_key(self, key):
        n = len(self.caps.keys)
        page = max(1, self._list_height - 1) if hasattr(self, "_list_height") else 10
        moved = True
        if key in (UP, "k"):
            self.cap_cursor = max(0, self.cap_cursor - 1)
        elif key in (DOWN, "j"):
            self.cap_cursor = min(n - 1, self.cap_cursor + 1)
        elif key == PGUP:
            self.cap_cursor = max(0, self.cap_cursor - page)
        elif key == PGDN:
            self.cap_cursor = min(n - 1, self.cap_cursor + page)
        elif key in (HOME, "g"):
            self.cap_cursor = 0
        elif key in (END, "G"):
            self.cap_cursor = n - 1
        else:
            moved = False
        if moved:
            self.message = ""
            return
        if key in (" ", "x"):
            self.message = self.caps.toggle(self.caps.keys[self.cap_cursor]) or ""
        elif key == "/":
            self.searching = ""
            self.message = ""
        elif key == "n" and self.last_search:
            self._find(self.last_search, self.cap_cursor + 1)
        elif key in ENTER_KEYS or key in (TAB, RIGHT):
            self.message = ""
            self.screen = "summary"
        elif key in (ESC, BTAB, LEFT, "b"):
            self.message = ""
            self.screen = "form"
        elif key == "q":
            self._ask_quit()

    def _search_key(self, key):
        if key == ESC:
            self.searching = None
        elif key in ENTER_KEYS:
            self.last_search = self.searching
            self.searching = None
            if self.last_search:
                self._find(self.last_search, self.cap_cursor)
        elif key in BACKSPACE_KEYS:
            self.searching = self.searching[:-1]
        elif isinstance(key, str) and key.isprintable():
            self.searching += key

    def _find(self, text, start):
        t = text.lower()
        keys = self.caps.keys
        for i in list(range(start, len(keys))) + list(range(0, start)):
            cap = self.caps.vocab[keys[i]]
            if t in cap.get("short", "").lower() or t in cap.get("description", "").lower():
                self.cap_cursor = i
                self.message = ""
                return
        self.message = f"not found: {text}"

    def summary_lines(self):
        v, caps = self.values, self.caps
        lines = [("App name", v["name"]), ("Title", v["title"]), ("Settings folder", v["settings_folder"]),
                 ("Bundle id", v["bundle_id"]), ("Output directory", v["out"]), ("Menu bar", v["menu"]),
                 ("Engine branch (CI)", v["engine_ref"]),
                 ("Locales", ", ".join(to_options(self.cfg, v, caps, self.template, self.engine).locales)),
                 ("Icon", v["icon"] or "placeholder"), ("GitHub workflows", "yes" if v["ci"] else "no"),
                 ("git init + commit", "yes" if v["git"] else "no")]
        on = caps.on()
        names = []
        for k in caps.keys:
            if k in on:
                st = caps.state(k)
                names.append(caps.short(k) + {"base": "", "on": "", "implied": " (implied)"}[st])
        lines.append(("Capabilities", ", ".join(names)))
        return lines

    def _summary_key(self, key):
        if key in ENTER_KEYS or key == "c":
            try:
                o = self.options()
                self.cfg.validate(o)
                self.cfg.validate_caps(o.caps, self.caps.vocab)
            except self.cfg.ConfigError as e:
                self.message = str(e)
                return
            self.result = o
            self.done = True
        elif key in (ESC, BTAB, LEFT, "b"):
            self.message = ""
            self.screen = "caps"
        elif key in (UP, "k"):
            self.sum_top = max(0, self.sum_top - 1)
        elif key in (DOWN, "j"):
            self.sum_top += 1
        elif key == "q":
            self._ask_quit()

    # ---- drawing ------------------------------------------------------

    def draw(self, scr, attrs):
        h, w = scr.getmaxyx()
        scr.erase()
        a = attrs
        if h < MIN_H or w < MIN_W:
            put(scr, 0, 0, f"Terminal too small: {w}x{h}, need {MIN_W}x{MIN_H}.", a["bg"])
            return None
        fill(scr, 0, 0, h, w, a["bg"])
        put(scr, 0, 1, f"MTEngineSDL app configurator  -  {self.template}"[:w - 2], a["bgtitle"])
        top, left, bh, bw = 2, 2, h - 4, w - 4
        fill(scr, top, left, bh, bw, a["win"])
        box(scr, top, left, bh, bw, a["win"])
        steps = [("form", "1 App"), ("caps", "2 Capabilities"), ("summary", "3 Summary")]
        x = left + 2
        for key, label in steps:
            s = f" {label} "
            put(scr, top, x, s, a["hl"] if key == self.screen else a["wintitle"])
            x += len(s) + 1
        inner = (top + 1, left + 2, bh - 2, bw - 4)
        cursor = getattr(self, f"_draw_{self.screen}")(scr, a, *inner)
        cursor = self._draw_status(scr, a, h, w) or cursor
        return cursor

    def _draw_status(self, scr, a, h, w):
        keys = {
            "form": "Up/Down move  Enter/type edit  Space toggle  Ctrl-N Next  Esc quit",
            "caps": "Up/Down/PgUp/PgDn move  Space toggle  / search  Enter Next  Esc Back  q quit",
            "summary": "Enter create  Esc Back  q quit",
        }[self.screen]
        if self.editing is not None:
            keys = "Type to edit  Left/Right  Ctrl-U clear  Enter/Tab done  Esc stop editing"
        if self.searching is not None:
            put(scr, h - 1, 0, f" Search: {self.searching}".ljust(w - 1)[:w - 1], a["status"])
            return (h - 1, min(w - 2, 9 + len(self.searching)))
        fill(scr, h - 1, 0, 1, w, a["status"])
        put(scr, h - 1, 1, keys[:w - 2], a["status"])
        if self.message:
            put(scr, h - 2, 2, (" " + self.message + " ")[:w - 4], a["err"])

    def _draw_form(self, scr, a, y, x, hgt, wid):
        put(scr, y, x, "Describe the new app. Fields after the name follow it until you edit them."[:wid], a["win"])
        label_w = max(len(f.label) for f in FIELDS) + 2
        val_w = max(10, min(44, wid - label_w - 2))
        err_x = x + label_w + val_w + 1
        errors = self.form_errors()
        # One row per field, and a blank row before the button; scrolled like
        # the capability list so a short terminal still reaches every field.
        rows = []
        for i, f in enumerate(FIELDS):
            if f.kind == "button":
                rows.append(None)
            rows.append(i)
        view = max(1, hgt - 5)
        focus_row = rows.index(self.focus)
        self.form_top = scroll_top(focus_row, getattr(self, "form_top", 0), view, len(rows))
        if self.form_top > 0:
            glyph(scr, y + 1, x + wid - 2, "up", a["winbold"])
        if self.form_top + view < len(rows):
            glyph(scr, y + 1 + view, x + wid - 2, "down", a["winbold"])
        cursor = None
        for r, i in enumerate(rows[self.form_top:self.form_top + view]):
            if i is None:
                continue
            row, f = y + 2 + r, FIELDS[i]
            focused = i == self.focus
            if f.kind == "button":
                put(scr, row, x + label_w, f"< {f.label} >", a["hl"] if focused else a["winbold"])
                continue
            put(scr, row, x, f.label.rjust(label_w - 2) + ": ", a["winbold"] if focused else a["win"])
            v = self.values[f.key]
            if f.kind == "text":
                start = 0
                if focused and self.editing is not None and self.editing > val_w - 1:
                    start = self.editing - val_w + 1
                put(scr, row, x + label_w, v[start:start + val_w].ljust(val_w),
                    a["field_edit"] if focused and self.editing is not None else a["hl"] if focused else a["field"])
                if focused and self.editing is not None:
                    cursor = (row, x + label_w + self.editing - start)
            elif f.kind == "choice":
                s = "  ".join(f"({'*' if c == v else ' '}) {c}" for c in f.choices)
                put(scr, row, x + label_w, s[:val_w], a["hl"] if focused else a["win"])
            elif f.kind == "bool":
                put(scr, row, x + label_w, f"[{'x' if v else ' '}]", a["hl"] if focused else a["win"])
            # Beside the field, not inside it; an empty field is not an error until Next.
            if f.key in errors and (v or self.tried_next) and x + wid - err_x >= 12:
                put(scr, row, err_x, ("! " + errors[f.key])[:x + wid - err_x], a["winerr"])
        help_lines = textwrap.wrap(FIELDS[self.focus].help, wid)[:2]
        for i, line in enumerate(help_lines):
            put(scr, y + hgt - 2 + i - (len(help_lines) - 1), x, line, a["win"])
        return cursor

    def _draw_caps(self, scr, a, y, x, hgt, wid):
        put(scr, y, x, "Engine capabilities. [x] on, [*] required by another, [ ] off."[:wid], a["win"])
        wide = wid >= 100
        list_w = wid * 11 // 20 if wide else wid
        list_h = hgt - 2 if wide else max(3, hgt - 2 - 8)
        self._list_height = list_h
        keys = self.caps.keys
        self.cap_top = scroll_top(self.cap_cursor, self.cap_top, list_h, len(keys))
        name_w = max(len(self.caps.short(k)) for k in keys) + 1
        for r in range(list_h):
            i = self.cap_top + r
            if i >= len(keys):
                break
            k = keys[i]
            st = self.caps.state(k)
            mark = {"base": "[x]", "on": "[x]", "implied": "[*]", "off": "[ ]"}[st]
            desc = first_sentence(self.caps.vocab[k].get("description", ""))
            line = f"{mark} {self.caps.short(k).ljust(name_w)}| {desc}"
            attr = a["hl"] if i == self.cap_cursor else a["windim"] if st in ("base", "implied") else a["win"]
            put(scr, y + 2 + r, x, line[:list_w - 1].ljust(list_w - 1), attr)
        if self.cap_top > 0:
            glyph(scr, y + 1, x + list_w - 4, "up", a["winbold"])
        if self.cap_top + list_h < len(keys):
            glyph(scr, y + 1 + list_h, x + list_w - 4, "down", a["hl"] if self.cap_cursor == self.cap_top + list_h - 1
                else a["winbold"])
        # The description panel: right of the list, or under it.
        key = keys[self.cap_cursor]
        if wide:
            px, py, pw, ph = x + list_w + 1, y + 2, wid - list_w - 1, hgt - 2
            for r in range(ph):
                vline(scr, py + r, px - 1, a["windim"])
        else:
            px, py, pw, ph = x, y + 3 + list_h, wid, hgt - 3 - list_h
            hline(scr, py - 1, x, wid, a["windim"])
        lines = [(self.caps.short(key), a["winbold"])]
        for para in self.caps.details(key):
            lines += [(l, a["win"]) for l in textwrap.wrap(para, max(10, pw - 2))]
        for r, (text, attr) in enumerate(lines[:ph]):
            put(scr, py + r, px + 1, text[:pw - 2], attr)
        return None

    def _draw_summary(self, scr, a, y, x, hgt, wid):
        put(scr, y, x, "Ready to create the app. Enter creates it; Esc goes back."[:wid], a["win"])
        label_w = max(len(k) for k, _ in self.summary_lines()) + 2
        rows = []
        for k, v in self.summary_lines():
            wrapped = textwrap.wrap(v, max(10, wid - label_w)) or [""]
            rows.append((k.rjust(label_w - 2) + ": ", wrapped[0]))
            rows += [("", more) for more in wrapped[1:]]
        view = hgt - 2
        self.sum_top = max(0, min(self.sum_top, len(rows) - view))
        for r, (k, v) in enumerate(rows[self.sum_top:self.sum_top + view]):
            put(scr, y + 2 + r, x, k.rjust(label_w), a["winbold"])
            put(scr, y + 2 + r, x + label_w, v, a["win"])
        return None

# --------------------------------------------------------------------------
# Drawing helpers: clip everything, so a small or resized terminal never raises.


def put(scr, y, x, text, attr=0):
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w or x < 0:
        return
    text = text[:max(0, w - x - (1 if y == h - 1 else 0))]
    if not text:
        return
    try:
        scr.addstr(y, x, text, attr)
    except curses.error:
        pass


def fill(scr, y, x, hgt, wid, attr):
    for r in range(hgt):
        put(scr, y + r, x, " " * wid, attr)


# Lines use the terminal's own line-drawing set (curses ACS), not Unicode box
# characters: those are "ambiguous width" and some terminals and fonts draw
# them double-wide or not at all. A fake screen without addch gets Unicode.
ACS = {"h": ("ACS_HLINE", "\u2500"), "v": ("ACS_VLINE", "\u2502"), "ul": ("ACS_ULCORNER", "\u250c"),
       "ur": ("ACS_URCORNER", "\u2510"), "ll": ("ACS_LLCORNER", "\u2514"), "lr": ("ACS_LRCORNER", "\u2518"),
       "up": ("ACS_UARROW", "\u25b2"), "down": ("ACS_DARROW", "\u25bc")}


def glyph(scr, y, x, name, attr=0):
    h, w = scr.getmaxyx()
    if not (0 <= y < h and 0 <= x < w) or (y == h - 1 and x == w - 1):
        return
    acs_name, text = ACS[name]
    if hasattr(scr, "addch") and hasattr(curses, acs_name):
        try:
            scr.addch(y, x, getattr(curses, acs_name), attr)
        except curses.error:
            pass
    else:
        put(scr, y, x, text, attr)


def hline(scr, y, x, n, attr):
    for i in range(n):
        glyph(scr, y, x + i, "h", attr)


def vline(scr, y, x, attr):
    glyph(scr, y, x, "v", attr)


def box(scr, y, x, hgt, wid, attr):
    glyph(scr, y, x, "ul", attr)
    hline(scr, y, x + 1, wid - 2, attr)
    glyph(scr, y, x + wid - 1, "ur", attr)
    for r in range(1, hgt - 1):
        vline(scr, y + r, x, attr)
        vline(scr, y + r, x + wid - 1, attr)
    glyph(scr, y + hgt - 1, x, "ll", attr)
    hline(scr, y + hgt - 1, x + 1, wid - 2, attr)
    glyph(scr, y + hgt - 1, x + wid - 1, "lr", attr)


def make_attrs():
    """menuconfig's layout: blue screen, white window, blue highlight."""
    names = ("bg", "bgtitle", "win", "winbold", "wintitle", "windim", "winerr", "hl", "field", "field_edit", "status", "err")
    if not curses.has_colors():
        r = curses.A_REVERSE
        return dict(zip(names, (0, curses.A_BOLD, 0, curses.A_BOLD, curses.A_BOLD, curses.A_DIM, curses.A_BOLD,
                                r, curses.A_UNDERLINE, r | curses.A_BOLD, r, curses.A_BOLD)))
    curses.start_color()
    # Contrast first: dark text on the brightest background the terminal has,
    # light text only on blue or black. Bright colours (8-15) where available.
    bright = curses.COLORS >= 16
    WHITE = curses.COLOR_WHITE + 8 if bright else curses.COLOR_WHITE
    YELLOW = curses.COLOR_YELLOW + 8 if bright else curses.COLOR_YELLOW
    B, K, BL, R, C = curses.COLOR_BLUE, curses.COLOR_BLACK, curses.COLOR_BLUE, curses.COLOR_RED, curses.COLOR_CYAN
    pairs = {"bg": (WHITE, B), "win": (K, WHITE), "winerr": (R, WHITE), "windim": (BL, WHITE),
             "hl": (WHITE, B), "field": (WHITE, K), "field_edit": (YELLOW, K), "status": (K, C), "err": (WHITE, R)}
    ids = {}
    for i, (k, (fg, bgc)) in enumerate(pairs.items(), start=1):
        curses.init_pair(i, fg, bgc)
        ids[k] = curses.color_pair(i)
    return {"bg": ids["bg"], "bgtitle": ids["bg"] | curses.A_BOLD, "win": ids["win"],
            "winbold": ids["win"] | curses.A_BOLD, "wintitle": ids["win"] | curses.A_BOLD, "windim": ids["windim"],
            "winerr": ids["winerr"] | curses.A_BOLD, "hl": ids["hl"] | curses.A_BOLD, "field": ids["field"],
            "field_edit": ids["field_edit"] | curses.A_BOLD, "status": ids["status"], "err": ids["err"] | curses.A_BOLD}

# --------------------------------------------------------------------------
# Entry point


def initial_values(ns, template):
    name = ns.name or ""
    v = {"name": name}
    given = {"title": ns.title, "settings_folder": ns.settings_folder, "bundle_id": ns.bundle_id,
             "out": str(ns.out) if ns.out else None}
    for k in DERIVED:
        v[k] = given[k] if given[k] is not None else derived_value(k, name, template)
    v["menu"] = ns.menu or "imgui"
    v["engine_ref"] = ns.engine_ref or None
    v["locales"] = ns.locales or "en"
    v["icon"] = str(ns.icon) if ns.icon else ""
    v["ci"] = not ns.no_ci
    v["git"] = not ns.no_git
    return v


def run(cfg, ns, template, engine, vocab):
    """Show the wizard. Returns Options, or None when the user quits."""
    values = initial_values(ns, template)
    if values["engine_ref"] is None:
        values["engine_ref"] = cfg.DEFAULT_ENGINE_REF
    given = [c.strip().upper().removeprefix("MT_CAP_") for c in (ns.caps or "").split(",") if c.strip()]
    cfg.validate_caps(given, vocab)          # the same error as the command-line path, before the screen opens
    chosen = [f"MT_CAP_{c}" for c in given]
    touched = [k for k, given in (("title", ns.title), ("settings_folder", ns.settings_folder),
                                   ("bundle_id", ns.bundle_id), ("out", ns.out)) if given is not None]
    wiz = Wizard(cfg, values, CapsModel(vocab, base_caps(template), chosen), template, engine, touched)

    def main(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        curses.set_escdelay(25) if hasattr(curses, "set_escdelay") else None
        attrs = make_attrs()
        while not wiz.done:
            cur = wiz.draw(stdscr, attrs)
            try:
                if cur:
                    curses.curs_set(1)
                    stdscr.move(*cur)
                else:
                    curses.curs_set(0)
            except curses.error:
                pass
            stdscr.refresh()
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                return
            wiz.handle(key)

    curses.wrapper(main)
    return wiz.result
