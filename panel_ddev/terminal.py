"""Terminal tabs (VTE) where DDEV commands run.
They are real terminals: if something asks for a password, type it there."""

import os
import tempfile

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

from . import ddev  # noqa: E402
from .i18n import _  # noqa: E402

_SCRIPT_DIR = os.path.join(GLib.get_user_runtime_dir() or tempfile.gettempdir(), "panel-ddev")


def _rgba(spec):
    c = Gdk.RGBA()
    c.parse(spec)
    return c


# (foreground, background) per theme; the 16-colour palette is left to VTE
TERMINAL_COLORS = {
    False: ("#2e3436", "#fafafa"),
    True: ("#e6e6e6", "#1e1e1e"),
}


class TerminalTabs(Gtk.Notebook):
    def __init__(self):
        super().__init__()
        self.set_scrollable(True)
        self.dark = True
        self._terms = []
        self._placeholder = Gtk.Label(label=_("The output of each action shows up here."))
        self._placeholder.get_style_context().add_class("dim-label")
        self.append_page(self._placeholder, Gtk.Label(label=_("Output")))

    def set_dark(self, dark):
        self.dark = dark
        for term in self._terms:
            self._apply_colors(term)

    def _apply_colors(self, term):
        fg, bg = TERMINAL_COLORS[bool(self.dark)]
        term.set_colors(_rgba(fg), _rgba(bg), None)

    def run(self, title, script, cwd=None, on_done=None):
        """Runs a bash script in a new tab."""
        os.makedirs(_SCRIPT_DIR, mode=0o700, exist_ok=True)
        fd, path = tempfile.mkstemp(suffix=".sh", dir=_SCRIPT_DIR)
        with os.fdopen(fd, "w") as f:
            f.write(script)
        self._spawn(title, ddev.shell_argv(f"bash {path}; rm -f {path}"), cwd, on_done)

    def interactive(self, title, command, cwd=None, on_done=None):
        """Opens an interactive session (ddev ssh, logs -f…). Returns the Vte.Terminal."""
        return self._spawn(title, ddev.shell_argv(command), cwd, on_done)

    @staticmethod
    def text_of(term):
        """Visible text of a terminal (get_text() is deprecated in recent VTE)."""
        try:
            return term.get_text_format(Vte.Format.TEXT) or ""
        except (AttributeError, TypeError):
            return term.get_text(None, None)[0] or ""

    def running_count(self):
        return sum(1 for t in self._terms if getattr(t, "running", False))

    def _spawn(self, title, argv, cwd, on_done):
        if self._placeholder.get_parent():
            self.remove_page(self.page_num(self._placeholder))

        term = Vte.Terminal()
        term.set_scrollback_lines(10000)
        term.set_font(Pango.FontDescription("Monospace 10"))
        term.set_size_request(-1, 120)
        self._apply_colors(term)
        self._terms.append(term)
        scroll = Gtk.ScrolledWindow()
        scroll.add(term)

        spinner = Gtk.Spinner()
        spinner.start()
        label = Gtk.Label(label=title)
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_tooltip_text(_("Close tab"))
        head = Gtk.Box(spacing=6)
        for w in (spinner, label, close):
            head.pack_start(w, False, False, 0)
        head.show_all()

        scroll.show_all()
        idx = self.append_page(scroll, head)
        self.set_tab_reorderable(scroll, True)
        self.set_current_page(idx)
        term.grab_focus()
        term.running = True

        def on_exit(_term, status):
            term.running = False
            spinner.stop()
            spinner.hide()
            try:
                code = os.waitstatus_to_exitcode(status)
            except ValueError:
                code = status
            label.set_markup(f"{GLib.markup_escape_text(title)} {'✔' if code == 0 else '✘'}")
            if on_done:
                on_done(code)

        def on_close(_btn):
            if term.running:
                dlg = Gtk.MessageDialog(
                    transient_for=self.get_toplevel(),
                    modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text=_("This action is still running. Close it and stop it?"),
                )
                answer = dlg.run()
                dlg.destroy()
                if answer != Gtk.ResponseType.YES:
                    return
            self._terms.remove(term)
            self.remove_page(self.page_num(scroll))
            if self.get_n_pages() == 0:
                self.append_page(self._placeholder, Gtk.Label(label=_("Output")))
                self._placeholder.show()

        term.connect("child-exited", on_exit)
        close.connect("clicked", on_close)
        term.spawn_async(
            Vte.PtyFlags.DEFAULT,
            cwd or str(ddev.HOME),
            argv,
            None,
            GLib.SpawnFlags.SEARCH_PATH,
            None,
            None,
            -1,
            None,
            None,
        )
        return term
