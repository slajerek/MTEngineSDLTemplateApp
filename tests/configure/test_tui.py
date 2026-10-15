import sys, unittest
from pathlib import Path
from helpers import load_configure, make_workspace, TEMPLATE

try:
    import curses  # noqa: F401
except ImportError:          # Windows' Python has no curses; the wizard falls back there
    curses = None

cfg = load_configure()
if curses:
    sys.path.insert(0, str(TEMPLATE))
    import configure_tui as tui


class FakeScreen:
    """Enough of a curses window for Wizard.draw: a grid of characters."""
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.erase()

    def erase(self):
        self.rows = [[" "] * self.w for _ in range(self.h)]

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        assert 0 <= y < self.h and 0 <= x and x + len(text) <= self.w, (y, x, text)
        self.rows[y][x:x + len(text)] = list(text)

    def text(self):
        return "\n".join("".join(r) for r in self.rows)


ATTRS = {k: 0 for k in ("bg", "bgtitle", "win", "winbold", "wintitle", "windim", "winerr", "hl", "field",
                        "field_edit", "status", "err")}


@unittest.skipUnless(curses, "no curses on this Python")
class CapsModelTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.vocab = cfg.locate_engine(cfg.Options(name="X", out=self.parent / "X", title="X", settings_folder="X",
                                                   bundle_id="com.example.x", menu="imgui", template=self.tpl,
                                                   engine=self.engine))
        self.m = tui.CapsModel(self.vocab, tui.base_caps(self.tpl))

    def test_base_caps_are_the_templates_and_locked(self):
        self.assertEqual(self.m.state("MT_CAP_TEST_ENGINE"), "base")
        self.assertIn("every app", self.m.toggle("MT_CAP_TEST_ENGINE"))
        self.assertEqual(self.m.selected(), [])

    def test_implied_is_locked_while_its_cause_is_on(self):
        self.assertIsNone(self.m.toggle("MT_CAP_HTTPS"))
        self.assertEqual(self.m.state("MT_CAP_HTTP"), "implied")
        self.assertIn("HTTPS", self.m.toggle("MT_CAP_HTTP"))
        self.assertIsNone(self.m.toggle("MT_CAP_HTTPS"))
        self.assertEqual(self.m.state("MT_CAP_HTTP"), "off")

    def test_selected_is_what_options_take(self):
        self.m.toggle("MT_CAP_MIDI")
        self.m.toggle("MT_CAP_HTTPS")
        self.assertEqual(self.m.selected(), ["HTTPS", "MIDI"])

    def test_details_name_what_it_pulls_in(self):
        self.assertIn("Also turns on: HTTP.", self.m.details("MT_CAP_HTTPS"))

    def test_scroll_top(self):
        self.assertEqual(tui.scroll_top(0, 0, 5, 24), 0)
        self.assertEqual(tui.scroll_top(7, 0, 5, 24), 3)      # cursor below the window pulls it down
        self.assertEqual(tui.scroll_top(2, 3, 5, 24), 2)      # above pulls it up
        self.assertEqual(tui.scroll_top(23, 30, 5, 24), 19)   # never past the end
        self.assertEqual(tui.scroll_top(1, 0, 10, 3), 0)      # fewer items than rows


@unittest.skipUnless(curses, "no curses on this Python")
class WizardTest(unittest.TestCase):
    def setUp(self):
        self.parent, self.tpl, self.engine = make_workspace()
        self.ns = cfg.parse_args(["--template", str(self.tpl)])
        vocab = cfg.locate_engine(cfg.Options(name="X", out=self.parent / "X", title="X", settings_folder="X",
                                              bundle_id="com.example.x", menu="imgui", template=self.tpl,
                                              engine=self.engine))
        values = tui.initial_values(self.ns, self.tpl)
        values["engine_ref"] = cfg.DEFAULT_ENGINE_REF
        self.w = tui.Wizard(cfg, values, tui.CapsModel(vocab, tui.base_caps(self.tpl)), self.tpl, self.engine)

    def keys(self, *seq):
        for k in seq:
            for ch in ([k] if not isinstance(k, str) or len(k) <= 1 else list(k)):
                self.w.handle(ch)
                for size in ((18, 60), (24, 80), (40, 140)):
                    self.w.draw(FakeScreen(*size), ATTRS)

    def test_full_run_creates_options(self):
        self.keys("MyTool", "\n", tui.NEXT_KEY)
        self.assertEqual(self.w.screen, "caps")
        self.keys("/", "https", "\n", " ")
        self.assertEqual(self.w.caps.keys[self.w.cap_cursor], "MT_CAP_HTTPS")
        self.keys("\n")
        self.assertEqual(self.w.screen, "summary")
        self.keys("\n")
        o = self.w.result
        self.assertTrue(self.w.done)
        self.assertEqual((o.name, o.title, o.settings_folder, o.bundle_id), ("MyTool", "MyTool", "MyTool", "com.example.mytool"))
        self.assertEqual(o.out, (self.parent / "MyTool").resolve())
        self.assertEqual((o.caps, o.locales, o.menu, o.engine_ref), (["HTTPS"], ["en"], "imgui", "origin/devel"))
        cfg.validate(o)

    def test_derived_fields_follow_the_name_until_edited(self):
        self.keys("\t", "\n", "\x15", "Big Tool", "\n")        # the title: edit, Ctrl-U clears, type
        self.keys(tui.BTAB, "Agenda", "\n")                    # then the name
        self.assertEqual(self.w.values["title"], "Big Tool")
        self.assertEqual(self.w.values["bundle_id"], "com.example.agenda")
        self.assertEqual(self.w.values["out"], str(self.tpl.parent / "Agenda"))

    def test_moving_the_cursor_is_not_an_edit(self):
        # Opening a derived field and leaving it unchanged keeps it following the name.
        self.keys("Foo", "\n")
        self.w.focus = [f.key for f in tui.FIELDS].index("out")
        self.keys("\n", tui.END, tui.LEFT, tui.HOME, "\n")
        self.w.focus = 0
        self.keys("\n", "\x15", "Bar", "\n")
        self.assertEqual(self.w.values["out"], str(self.tpl.parent / "Bar"))

    def test_short_terminal_scrolls_the_form(self):
        # 18 rows cannot show every field: the focused one is always drawn.
        for i, f in enumerate(tui.FIELDS):
            self.w.focus = i
            scr = FakeScreen(18, 60)
            self.w.draw(scr, ATTRS)
            self.assertIn(f"< {f.label} >" if f.kind == "button" else f"{f.label}: ", scr.text(), f.key)

    def test_search_shows_a_cursor(self):
        self.keys("MyTool", "\n", tui.NEXT_KEY, "/", "mi")
        cur = self.w.draw(FakeScreen(24, 80), ATTRS)
        self.assertEqual(cur, (23, 9 + 2))

    def test_next_with_a_bad_name_stays_and_says_why(self):
        self.keys("myTool", "\n", tui.NEXT_KEY)
        self.assertEqual(self.w.screen, "form")
        self.assertEqual(tui.FIELDS[self.w.focus].key, "name")
        self.assertIn("PascalCase", self.w.message)

    def test_quit_asks_first(self):
        self.keys(tui.ESC, "n")
        self.assertFalse(self.w.done)
        self.keys(tui.ESC, "y")
        self.assertTrue(self.w.done)
        self.assertIsNone(self.w.result)

    def test_draws_the_list_and_the_description_panel(self):
        self.keys("MyTool", "\n", tui.NEXT_KEY, "/", "https", "\n", " ")
        for h, w in ((24, 80), (40, 140)):         # panel under the list, then beside it
            scr = FakeScreen(h, w)
            self.w.draw(scr, ATTRS)
            text = scr.text()
            self.assertIn("[x] HTTPS", text)
            self.assertIn("[*] HTTP ", text)
            self.assertIn("Also turns on: HTTP.", text)

    def test_long_list_scrolls(self):
        # More capabilities than rows: the cursor stays visible at the end.
        vocab = {f"MT_CAP_C{i:02d}": {"short": f"C{i:02d}", "description": f"Cap {i}."} for i in range(60)}
        self.w.caps = tui.CapsModel(vocab)
        self.w.screen = "caps"
        self.keys(tui.END)
        scr = FakeScreen(24, 80)
        self.w.draw(scr, ATTRS)
        self.assertIn("C59", scr.text())
        self.assertNotIn("C00 ", scr.text())

    def test_small_terminal_says_so(self):
        scr = FakeScreen(10, 40)
        self.w.draw(scr, ATTRS)
        self.assertIn("too small", scr.text())


@unittest.skipUnless(curses, "no curses on this Python")
class RunTest(unittest.TestCase):
    def test_unknown_caps_flag_fails_like_the_command_line(self):
        parent, tpl, engine = make_workspace()
        ns = cfg.parse_args(["--template", str(tpl), "--caps", "MIDDI"])
        vocab = cfg.locate_engine(cfg.Options(name="X", out=parent / "X", title="X", settings_folder="X",
                                              bundle_id="com.example.x", menu="imgui", template=tpl, engine=engine))
        with self.assertRaises(cfg.ConfigError) as e:
            tui.run(cfg, ns, tpl, engine, vocab)     # raises before curses starts
        self.assertIn("MIDDI", str(e.exception))


if __name__ == "__main__":
    unittest.main()
