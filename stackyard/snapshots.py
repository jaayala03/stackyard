"""Database snapshots (ddev snapshot): list, create, restore and delete."""

import re
import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import ddev  # noqa: E402
from .i18n import _  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def list_snapshots(project):
    raw = ddev._run_json("ddev snapshot --list -j", cwd=project["approot"], timeout=120)
    items = (raw or {}).get(project["name"]) or []
    return sorted(items, key=lambda s: s.get("Created", ""), reverse=True)


def default_name(project):
    return f"{project['name']}_{datetime.now():%Y%m%d-%H%M}"


def script_create(project, name):
    return ddev.script_simple(
        project["approot"],
        [(_("Creating snapshot {name}").format(name=name), f"ddev snapshot --name {ddev._q(name)}")],
        _("Snapshot {name} created").format(name=name),
    )


def script_restore(project, name):
    return ddev.script_simple(
        project["approot"],
        [(_("Restoring snapshot {name}").format(name=name), f"ddev snapshot restore {ddev._q(name)}")],
        _("Database restored from {name}").format(name=name),
    )


def script_delete(project, name):
    return ddev.script_simple(
        project["approot"],
        [(_("Deleting snapshot {name}").format(name=name), f"ddev snapshot --cleanup --name {ddev._q(name)} -y")],
        _("Snapshot {name} deleted").format(name=name),
    )


def _human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _when(iso):
    """'2026-11-07T20:06:29.17-05:00' -> '2026-11-07 20:06' (local time as reported)."""
    return (iso or "")[:16].replace("T", " ")


class SnapshotsDialog(Gtk.Dialog):
    """After run(): `action` is ('create'|'restore'|'delete', name) or None."""

    RESTORE, DELETE, CREATE = 1, 2, 3

    def __init__(self, parent, project):
        super().__init__(title=_("Database snapshots · {name}").format(name=project["name"]), transient_for=parent, modal=True)
        self.project = project
        self.action = None
        self.set_default_size(560, 440)
        self.add_button(_("Close"), Gtk.ResponseType.CLOSE)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(14)
        intro = Gtk.Label(
            label=_("A snapshot is a full copy of the database stored in .ddev/db_snapshots. "
                    "Restoring one replaces the current database."),
            xalign=0, wrap=True, max_width_chars=60,
        )
        intro.get_style_context().add_class("dim-label")
        box.pack_start(intro, False, False, 0)

        create = Gtk.Box(spacing=6)
        self.name = Gtk.Entry(text=default_name(project), activates_default=False)
        self.name.connect("changed", self._validate)
        self.name.connect("activate", lambda *_a: self._create())
        create.pack_start(self.name, True, True, 0)
        self.create_btn = Gtk.Button(label=_("Create snapshot"))
        self.create_btn.get_style_context().add_class("suggested-action")
        self.create_btn.connect("clicked", lambda *_a: self._create())
        create.pack_start(self.create_btn, False, False, 0)
        box.pack_start(create, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.status = Gtk.Label(label=_("Loading snapshots…"), margin=20)
        self.status.get_style_context().add_class("dim-label")
        self.status.show()
        self.listbox.set_placeholder(self.status)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroll.add(self.listbox)
        frame = Gtk.Frame()
        frame.add(scroll)
        box.pack_start(frame, True, True, 0)
        self.show_all()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            items, error = list_snapshots(self.project), None
        except Exception as exc:  # noqa: BLE001
            items, error = [], str(exc)
        GLib.idle_add(self._fill, items, error)

    def _fill(self, items, error):
        self.status.set_text(_("Could not list snapshots:\n{error}").format(error=error) if error else _("No snapshots yet."))
        for s in items:
            row = Gtk.ListBoxRow()
            line = Gtk.Box(spacing=8, margin=8)
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name = Gtk.Label(xalign=0)
            name.set_markup(f"<b>{GLib.markup_escape_text(s['Name'])}</b>")
            meta = Gtk.Label(xalign=0)
            meta.set_markup('<span size="small" foreground="#9a9996">{}</span>'.format(GLib.markup_escape_text(
                f"{_when(s.get('Created', ''))} · {_human_size(s.get('Size', 0))} · {s.get('DBVersion', '')}")))
            texts.pack_start(name, False, False, 0)
            texts.pack_start(meta, False, False, 0)
            line.pack_start(texts, True, True, 0)
            restore = Gtk.Button(label=_("Restore"))
            restore.connect("clicked", self._finish, "restore", s["Name"])
            delete = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
            delete.set_tooltip_text(_("Delete snapshot"))
            delete.connect("clicked", self._finish, "delete", s["Name"])
            line.pack_end(delete, False, False, 0)
            line.pack_end(restore, False, False, 0)
            row.add(line)
            self.listbox.add(row)
        self.listbox.show_all()
        return False

    def _validate(self, *_a):
        self.create_btn.set_sensitive(bool(NAME_RE.match(self.name.get_text().strip())))

    def _create(self):
        name = self.name.get_text().strip()
        if NAME_RE.match(name):
            self._finish(None, "create", name)

    def _finish(self, _btn, action, name):
        self.action = (action, name)
        self.response(Gtk.ResponseType.OK)
