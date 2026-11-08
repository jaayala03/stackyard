"""Editor for the project's .env files with light syntax highlighting."""

import os
import re
import shutil
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from .i18n import _  # noqa: E402

ENV_GLOB = ".env*"
LINE_RE = re.compile(r"^(\s*)(export\s+)?([A-Za-z_][A-Za-z0-9_.]*)(\s*=)(.*)$")


def env_files(approot):
    """The .env-style files in the project root, `.env` first."""
    root = Path(approot)
    files = sorted(p.name for p in root.glob(ENV_GLOB) if p.is_file() and not p.name.endswith((".bak", ".swp")))
    if ".env" in files:
        files.remove(".env")
        files.insert(0, ".env")
    return files


def save_file(path, text):
    """Atomic write that keeps the previous version as <name>.bak."""
    path = Path(path)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


class EnvDialog(Gtk.Dialog):
    """After run() == OK: `saved` is True and `clear_cache` tells whether to
    clear the framework config cache."""

    def __init__(self, parent, project):
        super().__init__(title=_("Environment file · {name}").format(name=project["name"]), transient_for=parent, modal=True)
        self.project = project
        self.root = Path(project["approot"])
        self.saved = False
        self.clear_cache = False
        self._dirty = False
        self.set_default_size(760, 560)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.save_btn = self.add_button(_("Save"), Gtk.ResponseType.OK)
        self.save_btn.get_style_context().add_class("suggested-action")

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        top = Gtk.Box(spacing=8)
        top.pack_start(Gtk.Label(label=_("File")), False, False, 0)
        self.files = Gtk.ComboBoxText()
        self.files.connect("changed", self._on_file_changed)
        top.pack_start(self.files, False, False, 0)
        self.create_btn = Gtk.Button(label=_("Create .env from .env.example"))
        self.create_btn.connect("clicked", self._create_from_example)
        top.pack_start(self.create_btn, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.view = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.NONE, top_margin=6, left_margin=8)
        buf = self.view.get_buffer()
        buf.create_tag("key", weight=Pango.Weight.BOLD, foreground="#3584e4")
        buf.create_tag("comment", foreground="#9a9996", style=Pango.Style.ITALIC)
        buf.connect("changed", self._on_changed)
        self.view.connect("key-press-event", self._on_key)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.add(self.view)
        frame = Gtk.Frame()
        frame.add(scroll)
        box.pack_start(frame, True, True, 0)

        self.is_laravel = (self.root / "artisan").exists()
        self.cache_check = Gtk.CheckButton(label=_("Clear the Laravel config cache after saving (artisan config:clear)"), active=True)
        if self.is_laravel:
            box.pack_start(self.cache_check, False, False, 0)
        hint = Gtk.Label(label=_("A copy of the previous version is kept as .env.bak. Ctrl+S saves."), xalign=0)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        self.current = None
        self._reload_files()
        self.show_all()
        self.create_btn.set_visible(".env" not in env_files(self.root) and (self.root / ".env.example").exists())

    # ------------------------------------------------------------ files
    def _reload_files(self, select=None):
        names = env_files(self.root)
        self.files.remove_all()
        for n in names:
            self.files.append(n, n)
        has_env = ".env" in names
        self.create_btn.set_visible(not has_env and (self.root / ".env.example").exists())
        if names:
            self.files.set_active_id(select or names[0])
        else:
            self._set_text(_("# This project has no .env file yet.\n# Type here and press Save to create .env\n"))
            self.current = self.root / ".env"
            self._dirty = False

    def _on_file_changed(self, combo):
        name = combo.get_active_id()
        if not name or (getattr(self, "current", None) and self.current.name == name):
            return
        if self._dirty and not self._confirm_discard():
            combo.handler_block_by_func(self._on_file_changed)
            combo.set_active_id(self.current.name)  # stay on the edited file
            combo.handler_unblock_by_func(self._on_file_changed)
            return
        self.current = self.root / name
        try:
            self._set_text(self.current.read_text())
        except (OSError, UnicodeDecodeError) as exc:
            self._set_text(f"# {exc}\n")
        self._dirty = False

    def _create_from_example(self, _btn):
        shutil.copy2(self.root / ".env.example", self.root / ".env")
        self._dirty = False
        self._reload_files(".env")

    def _confirm_discard(self):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.YES_NO, text=_("Discard unsaved changes?"))
        ok = dlg.run() == Gtk.ResponseType.YES
        dlg.destroy()
        return ok

    # ------------------------------------------------------------ text
    def _set_text(self, text):
        buf = self.view.get_buffer()
        buf.handler_block_by_func(self._on_changed)
        buf.set_text(text)
        buf.handler_unblock_by_func(self._on_changed)
        self._highlight()

    def get_text(self):
        buf = self.view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def _on_changed(self, _buf):
        self._dirty = True
        self._highlight()

    def _highlight(self):
        buf = self.view.get_buffer()
        buf.remove_all_tags(buf.get_start_iter(), buf.get_end_iter())
        for i, line in enumerate(self.get_text().split("\n")):
            start = buf.get_iter_at_line(i)
            if line.lstrip().startswith("#"):
                end = start.copy()
                end.forward_to_line_end()
                buf.apply_tag_by_name("comment", start, end)
                continue
            m = LINE_RE.match(line)
            if m:
                key_start = buf.get_iter_at_line_offset(i, m.start(3))
                key_end = buf.get_iter_at_line_offset(i, m.end(3))
                buf.apply_tag_by_name("key", key_start, key_end)

    def _on_key(self, _w, event):
        if event.keyval in (Gdk.KEY_s, Gdk.KEY_S) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.response(Gtk.ResponseType.OK)
            return True
        return False

    # ------------------------------------------------------------ result
    def save(self):
        """Writes the current file; returns an error message or None."""
        try:
            save_file(self.current, self.get_text())
        except OSError as exc:
            return str(exc)
        self.saved = True
        self.clear_cache = self.is_laravel and self.cache_check.get_active() and self.current.name == ".env"
        return None
