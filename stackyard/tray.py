"""System tray icon: quick access to projects without opening the window."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .i18n import _  # noqa: E402

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
except (ValueError, ImportError):
    AppIndicator = None

AUTOSTART = Path(GLib.get_user_config_dir()) / "autostart" / "stackyard.desktop"
AUTOSTART_TEXT = """[Desktop Entry]
Type=Application
Name=Stackyard
Comment=Stackyard tray icon
Exec={launcher} --hidden
Icon=stackyard
Terminal=false
X-GNOME-Autostart-enabled=true
"""


OLD_AUTOSTART = AUTOSTART.with_name("panel-ddev.desktop")  # name before 1.1.0


def migrate_autostart(launcher):
    """Replaces the autostart entry of the old app name with the new one."""
    if OLD_AUTOSTART.exists():
        OLD_AUTOSTART.unlink()
        set_autostart(True, launcher)


def available():
    return AppIndicator is not None


def autostart_enabled():
    return AUTOSTART.exists()


def set_autostart(enabled, launcher):
    if enabled:
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART.write_text(AUTOSTART_TEXT.format(launcher=launcher))
    elif AUTOSTART.exists():
        AUTOSTART.unlink()


class Tray:
    """The menu reuses the actions of `window` (the MainWindow)."""

    def __init__(self, app, window, icon_path, launcher):
        self.app = app
        self.window = window
        self.launcher = launcher
        self.menu = None
        self.indicator = AppIndicator.Indicator.new(
            "stackyard", "applications-development", AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        if Path(icon_path).exists():
            self.indicator.set_icon_full(icon_path, "Stackyard")
        self.indicator.set_title("Stackyard")
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.update([])

    def set_window(self, window):
        self.window = window

    def _item(self, menu, label, cb=None, sensitive=True):
        item = Gtk.MenuItem(label=label)
        item.set_sensitive(sensitive)
        if cb:
            item.connect("activate", lambda *_a: cb())
        menu.append(item)
        return item

    def update(self, projects):
        w = self.window
        menu = Gtk.Menu()
        self._item(menu, _("Open Stackyard"), self.show_window)
        menu.append(Gtk.SeparatorMenuItem())

        if not projects:
            self._item(menu, _("No projects"), sensitive=False)
        for p in projects:
            running = p.get("status") == "running"
            busy = p["name"] in w.busy
            mark = "⏳" if busy else ("●" if running else "○")
            sub = Gtk.Menu()
            top = Gtk.MenuItem(label=f"{mark}  {p['name']}")
            top.set_submenu(sub)
            url = w.project_url(p)
            self._item(sub, _("Open in browser"), lambda u=url: w.open_uri(u), running)
            if running:
                self._item(sub, _("Stop"), lambda pp=p: w.project_action(pp, "stop"), not busy)
                self._item(sub, _("Restart"), lambda pp=p: w.project_action(pp, "restart"), not busy)
            else:
                self._item(sub, _("Start"), lambda pp=p: w.project_action(pp, "start"), not busy)
            self._item(sub, _("Open folder"), lambda pp=p: w.open_uri(Path(pp["approot"]).as_uri()))
            self._item(sub, _("Show in panel"), lambda pp=p: self.show_window(pp["name"]))
            menu.append(top)

        menu.append(Gtk.SeparatorMenuItem())
        any_running = any(p.get("status") == "running" for p in projects)
        self._item(menu, _("Stop all"), w.poweroff_now, any_running)
        auto = Gtk.CheckMenuItem(label=_("Open at login"))
        auto.set_active(autostart_enabled())
        auto.connect("toggled", lambda item: set_autostart(item.get_active(), self.launcher))
        menu.append(auto)
        menu.append(Gtk.SeparatorMenuItem())
        self._item(menu, _("Quit"), self.app.request_quit)
        menu.show_all()
        self.indicator.set_menu(menu)
        self.menu = menu

    def show_window(self, select=None):
        if select:
            self.window.select_project(select)
        self.window.show()
        self.window.present()
