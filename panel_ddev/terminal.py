"""Pestañas de terminal (VTE) donde se ejecutan los comandos de DDEV.
Son terminales reales: si algo pide contraseña, se escribe ahí mismo."""

import os
import tempfile

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import GLib, Gtk, Pango, Vte  # noqa: E402

from . import ddev  # noqa: E402

_SCRIPT_DIR = os.path.join(GLib.get_user_runtime_dir() or tempfile.gettempdir(), "panel-ddev")


class TerminalTabs(Gtk.Notebook):
    def __init__(self):
        super().__init__()
        self.set_scrollable(True)
        self._placeholder = Gtk.Label(label="Aquí verás lo que hace cada acción.")
        self._placeholder.get_style_context().add_class("dim-label")
        self.append_page(self._placeholder, Gtk.Label(label="Salida"))

    def run(self, title, script, cwd=None, on_done=None):
        """Ejecuta un script de bash en una pestaña nueva."""
        os.makedirs(_SCRIPT_DIR, mode=0o700, exist_ok=True)
        fd, path = tempfile.mkstemp(suffix=".sh", dir=_SCRIPT_DIR)
        with os.fdopen(fd, "w") as f:
            f.write(script)
        self._spawn(title, ddev.shell_argv(f"bash {path}; rm -f {path}"), cwd, on_done)

    def interactive(self, title, command, cwd=None, on_done=None):
        """Abre una sesión interactiva (ddev ssh, logs -f…)."""
        self._spawn(title, ddev.shell_argv(command), cwd, on_done)

    def _spawn(self, title, argv, cwd, on_done):
        if self._placeholder.get_parent():
            self.remove_page(self.page_num(self._placeholder))

        term = Vte.Terminal()
        term.set_scrollback_lines(10000)
        term.set_font(Pango.FontDescription("Monospace 10"))
        term.set_size_request(-1, 120)
        scroll = Gtk.ScrolledWindow()
        scroll.add(term)

        spinner = Gtk.Spinner()
        spinner.start()
        label = Gtk.Label(label=title)
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_tooltip_text("Cerrar pestaña")
        head = Gtk.Box(spacing=6)
        for w in (spinner, label, close):
            head.pack_start(w, False, False, 0)
        head.show_all()

        scroll.show_all()
        idx = self.append_page(scroll, head)
        self.set_tab_reorderable(scroll, True)
        self.set_current_page(idx)
        term.grab_focus()

        state = {"running": True}

        def on_exit(_term, status):
            state["running"] = False
            spinner.stop()
            spinner.hide()
            try:
                code = os.waitstatus_to_exitcode(status)
            except ValueError:
                code = status
            label.set_markup(
                f"{GLib.markup_escape_text(title)} {'✔' if code == 0 else '✘'}"
            )
            if on_done:
                on_done(code)

        def on_close(_btn):
            if state["running"]:
                dlg = Gtk.MessageDialog(
                    transient_for=self.get_toplevel(),
                    modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text="Esta acción sigue en marcha. ¿Cerrar y detenerla?",
                )
                answer = dlg.run()
                dlg.destroy()
                if answer != Gtk.ResponseType.YES:
                    return
            self.remove_page(self.page_num(scroll))
            if self.get_n_pages() == 0:
                self.append_page(self._placeholder, Gtk.Label(label="Salida"))
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
