"""Panel DDEV main window and application."""

import shutil
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import REPO_URL, __version__, ddev, i18n, settings  # noqa: E402
from . import tray as traymod  # noqa: E402
from . import commands, snapshots  # noqa: E402
from .dialogs import CommandDialog, PreferencesDialog, ProjectDialog  # noqa: E402
from .git import GitView  # noqa: E402
from .i18n import _  # noqa: E402
from .terminal import TerminalTabs  # noqa: E402

APP_ID = "local.panel.ddev"
REFRESH_SECONDS = 10
ICON = str(Path(__file__).resolve().parent.parent / "icon.svg")
AUTHOR = "Jonathan Alberto Ayala Mendoza"

CSS = b"""
.status-dot { font-size: 14px; }
.running { color: #2ec27e; }
.stopped, .paused { color: #9a9996; }
.unhealthy, .starting { color: #e5a50a; }
.project-title { font-size: 20px; font-weight: bold; }
"""

STATUS_LABELS = {
    "running": "Running",
    "stopped": "Stopped",
    "paused": "Paused",
    "starting": "Starting",
    "unhealthy": "Unhealthy",
}


def icon_button(icon, label, tooltip=None, cb=None):
    btn = Gtk.Button()
    box = Gtk.Box(spacing=6)
    box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
    box.pack_start(Gtk.Label(label=label), False, False, 0)
    btn.add(box)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    if cb:
        btn.connect("clicked", lambda *_a: cb())
    return btn


class ProjectRow(Gtk.ListBoxRow):
    def __init__(self, project):
        super().__init__()
        self.project = project
        box = Gtk.Box(spacing=10, margin=8)
        status = project.get("status", "stopped")
        dot = Gtk.Label(label="●")
        dot.get_style_context().add_class("status-dot")
        dot.get_style_context().add_class(status.split()[0])
        box.pack_start(dot, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(xalign=0)
        name.set_markup(f"<b>{GLib.markup_escape_text(project['name'])}</b>")
        url = Gtk.Label(label=project.get("primary_url", ""), xalign=0, ellipsize=3)
        url.get_style_context().add_class("dim-label")
        texts.pack_start(name, False, False, 0)
        texts.pack_start(url, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.add(box)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Panel DDEV")
        self.set_default_size(1060, 720)
        if Path(ICON).exists():
            self.set_icon_from_file(ICON)
        self.projects = []
        self.selected = None
        self.busy = set()  # projects with an action in progress
        self.editor = ddev.find_editor()
        self.git_views = {}
        self.current_page = "project"
        self._rebuilding = False
        self._pending_select = None
        self._tray_sig = None

        # ---------------- header bar
        header = Gtk.HeaderBar(show_close_button=True, title="Panel DDEV")
        self.set_titlebar(header)
        self.header = header
        header.pack_start(icon_button("document-new-symbolic", _("New"), _("Create a new project"), self.on_new))
        header.pack_start(icon_button("folder-download-symbolic", _("Clone"), _("Clone a repository with git"), self.on_clone))
        header.pack_start(icon_button("folder-new-symbolic", _("Add folder"), _("Use a folder you already have with DDEV"), self.on_add_existing))
        header.pack_end(self._build_menu_button())
        header.pack_end(icon_button("system-shutdown-symbolic", _("Stop all"), _("Stop every project (ddev poweroff)"), self.on_poweroff))
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text(_("Refresh"))
        refresh.connect("clicked", lambda *_a: self.refresh())
        header.pack_end(refresh)

        # ---------------- project list
        self.listbox = Gtk.ListBox()
        self.listbox.set_placeholder(self._placeholder_label(_("No projects yet.\nCreate one with “New”, “Clone” or “Add folder”.")))
        self.listbox.connect("row-selected", self.on_row_selected)
        list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        list_scroll.set_size_request(280, -1)
        list_scroll.add(self.listbox)

        # ---------------- detail
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        top = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        top.pack1(list_scroll, False, False)
        top.pack2(self.detail, True, False)

        # ---------------- terminal
        self.terms = TerminalTabs()
        self.terms.set_dark(settings.is_dark_now())
        bottom = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        bottom.pack1(top, True, False)
        bottom.pack2(self.terms, False, True)
        bottom.set_position(440)
        self.add(bottom)

        self.show_all()
        if self.get_screen().get_height() < 900:
            self.maximize()
        self.render_detail()
        if not ddev.ddev_installed():
            self.error(_("DDEV is not installed"), _("Install it first: https://ddev.com/get-started/"))
            return
        self.refresh()
        self._timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self._auto_refresh)
        self.connect("destroy", lambda *_a: GLib.source_remove(self._timer))

    def _build_menu_button(self):
        menu = Gtk.Menu()
        for label, cb in (
            (_("Preferences"), self.on_preferences),
            (_("About Panel DDEV"), self.on_about),
            (None, None),
            (_("Quit"), lambda: self.get_application().quit()),
        ):
            if label is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, c=cb: c())
            menu.append(item)
        menu.show_all()
        button = Gtk.MenuButton(popup=menu)
        button.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        button.set_tooltip_text(_("Menu"))
        return button

    # ================================================================ data
    def _auto_refresh(self):
        self.refresh()
        if self.get_visible() and self.current_page == "git" and self.selected:
            view = self.git_views.get(self.selected["name"])
            if view and view.get_mapped():
                view.refresh()
        return True

    def refresh(self):
        def work():
            try:
                projects = ddev.list_projects()
                GLib.idle_add(self.set_projects, projects)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.header.set_subtitle, _("Error reading projects: {error}").format(error=exc)[:120])

        threading.Thread(target=work, daemon=True).start()

    def set_projects(self, projects):
        prev = self.selected["name"] if self.selected else None
        if self._pending_select and any(p["name"] == self._pending_select for p in projects):
            prev, self._pending_select = self._pending_select, None
            self.projects = []  # force a redraw that selects the new project

        def sig(items):
            return [(p["name"], p.get("status"), p.get("cfg_php"), p.get("cfg_node"), p.get("cfg_webserver"), p.get("cfg_db")) for p in items]

        changed = sig(projects) != sig(self.projects)
        self.projects = projects
        self._update_tray()
        running = sum(1 for p in projects if p.get("status") == "running")
        self.header.set_subtitle(
            (_("{count} project") if len(projects) == 1 else _("{count} projects")).format(count=len(projects))
            + " · " + _("{count} running").format(count=running)
        )
        if not changed:
            return False
        for row in self.listbox.get_children():
            self.listbox.remove(row)
        select = None
        for p in projects:
            row = ProjectRow(p)
            self.listbox.add(row)
            if p["name"] == prev:
                select = row
        self.listbox.show_all()
        if select is None and projects and prev is None:
            select = self.listbox.get_row_at_index(0)
        if select:
            self.listbox.select_row(select)
        else:
            self.selected = None
            self.render_detail()
        return False

    def _update_tray(self):
        tray = getattr(self.get_application(), "tray", None)
        if not tray:
            return
        sig = [(p["name"], p.get("status"), p.get("primary_url")) for p in self.projects] + sorted(self.busy)
        if sig != self._tray_sig:
            self._tray_sig = sig
            tray.update(self.projects)

    def select_project(self, name):
        for row in self.listbox.get_children():
            if row.project["name"] == name:
                self.listbox.select_row(row)
                return

    def on_row_selected(self, _lb, row):
        self.selected = row.project if row else None
        self.render_detail()

    # ================================================================ detail
    def _placeholder_label(self, text):
        lbl = Gtk.Label(label=text, justify=Gtk.Justification.CENTER, margin=30)
        lbl.get_style_context().add_class("dim-label")
        lbl.show()
        return lbl

    def render_detail(self):
        # Git views are reused (they keep the commit message and selection), so
        # detach them before the old stack is destroyed. Detaching makes the old
        # stack switch page: _rebuilding tells _on_page_changed to ignore it.
        self._rebuilding = True
        for view in self.git_views.values():
            if view.get_parent():
                view.get_parent().remove(view)
        self._rebuilding = False
        for child in self.detail.get_children():
            self.detail.remove(child)
        p = self.selected
        if not p:
            self.detail.pack_start(self._placeholder_label(_("Select a project from the list\nor create a new one.")), True, True, 0)
            self.detail.show_all()
            return

        status = p.get("status", "stopped")
        running = status == "running"
        busy = p["name"] in self.busy

        # header
        title = Gtk.Label(label=p["name"], xalign=0)
        title.get_style_context().add_class("project-title")
        state = Gtk.Label(xalign=0)
        state_txt = _("Working…") if busy else _(STATUS_LABELS.get(status.split()[0], status))
        state.set_markup(f'<span size="large">●</span> {GLib.markup_escape_text(state_txt)}')
        state.get_style_context().add_class(status.split()[0])
        head = Gtk.Box(spacing=14)
        head.pack_start(title, False, False, 0)
        head.pack_start(state, False, False, 0)
        delete = icon_button("user-trash-symbolic", _("Delete…"), _("Removes containers and database; your files stay"), self.on_delete)
        delete.get_style_context().add_class("destructive-action")
        delete.set_sensitive(not busy)
        head.pack_end(delete, False, False, 0)
        self.detail.pack_start(head, False, False, 0)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher()
        head.pack_start(switcher, False, False, 12)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        body_scroll.add(body)
        stack.add_titled(body_scroll, "project", _("Project"))
        gitview = self._git_view(p)
        if gitview.get_parent():
            gitview.get_parent().remove(gitview)
        stack.add_titled(gitview, "git", "Git")
        self.detail.pack_start(stack, True, True, 0)

        url = p.get("primary_url") or p.get("httpsurl", "")
        link = Gtk.LinkButton.new_with_label(url, url)
        link.set_halign(Gtk.Align.START)
        link.set_sensitive(running)
        body.pack_start(link, False, False, 0)

        # main actions
        actions = Gtk.Box(spacing=8)
        start = icon_button("media-playback-start-symbolic", _("Start"), cb=lambda: self.action("start"))
        start.get_style_context().add_class("suggested-action")
        stop = icon_button("media-playback-stop-symbolic", _("Stop"), cb=lambda: self.action("stop"))
        restart = icon_button("view-refresh-symbolic", _("Restart"), cb=lambda: self.action("restart"))
        start.set_sensitive(not running and not busy)
        stop.set_sensitive(running and not busy)
        restart.set_sensitive(running and not busy)
        for b in (start, stop, restart):
            actions.pack_start(b, False, False, 0)
        actions.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)
        web = icon_button("web-browser-symbolic", _("Open site"), cb=lambda: self.open_uri(url))
        web.set_sensitive(running)
        actions.pack_start(web, False, False, 0)
        actions.pack_start(icon_button("folder-open-symbolic", _("Folder"), cb=lambda: self.open_uri(Path(p["approot"]).as_uri())), False, False, 0)
        if self.editor:
            actions.pack_start(icon_button("accessories-text-editor-symbolic", _("Editor"), _("Open with {editor}").format(editor=self.editor), lambda: self.open_editor(p["approot"])), False, False, 0)
        body.pack_start(actions, False, False, 0)

        # configuration
        frame = Gtk.Frame(label=" " + _("Configuration") + " ")
        grid = Gtk.Grid(column_spacing=24, row_spacing=6, margin=12)
        rows = [
            (_("Folder"), p.get("shortroot") or p.get("approot")),
            (_("Type"), ddev.label_for(ddev.PROJECT_TYPES, p.get("cfg_type") or p.get("type"))),
            (_("Public folder"), p.get("cfg_docroot") or _("(root)")),
            ("PHP", p.get("cfg_php") or "—"),
            ("Node", p.get("cfg_node") or p.get("nodejs_version") or "—"),
            (_("Web server"), ddev.label_for(ddev.WEBSERVERS, p.get("cfg_webserver"))),
            (_("Database"), ddev.label_for(ddev.DATABASES, p.get("cfg_db"))),
        ]
        for i, (k, v) in enumerate(rows):
            kl = Gtk.Label(label=k, xalign=0)
            kl.get_style_context().add_class("dim-label")
            grid.attach(kl, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=str(v), xalign=0, selectable=True), 1, i, 1, 1)
        xl = Gtk.Label(label="Xdebug", xalign=0)
        xl.get_style_context().add_class("dim-label")
        grid.attach(xl, 0, len(rows), 1, 1)
        xdebug = Gtk.Switch(halign=Gtk.Align.START, sensitive=False)
        xdebug.set_tooltip_text(_("Step debugging for PHP. It stays on until the project restarts."))
        grid.attach(xdebug, 1, len(rows), 1, 1)
        if running and not busy:
            self._load_xdebug(p, xdebug)
        edit = icon_button("emblem-system-symbolic", _("Change settings…"), cb=self.on_edit)
        edit.set_sensitive(not busy)
        edit.set_halign(Gtk.Align.START)
        edit.set_margin_top(6)
        grid.attach(edit, 0, len(rows) + 1, 2, 1)
        frame.add(grid)
        columns = Gtk.Box(spacing=12, homogeneous=True)
        columns.pack_start(frame, True, True, 0)
        body.pack_start(columns, False, False, 0)

        # tools
        tools_frame = Gtk.Frame(label=" " + _("Tools") + " ")
        tools = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2, min_children_per_line=2, margin=10, column_spacing=6, row_spacing=6, homogeneous=True)
        items = [
            ("utilities-terminal-symbolic", _("Terminal"), _("Shell inside the container (ddev ssh)"), self.on_ssh, running),
            ("text-x-generic-symbolic", _("Logs"), _("Follow the logs live"), self.on_logs, running),
            ("network-server-symbolic", "phpMyAdmin", _("Manage the database"), self.on_phpmyadmin, running and not busy),
            ("mail-unread-symbolic", "Mailpit", _("See the emails your app sends"), lambda: self.open_uri(p.get("mailpit_https_url", "")), running),
            ("document-open-symbolic", _("Import DB…"), _("Import a .sql or .sql.gz file"), self.on_import_db, running and not busy),
            ("document-save-symbolic", _("Export DB…"), _("Save the database to a file"), self.on_export_db, running and not busy),
            ("document-revert-symbolic", _("Snapshots…"), _("Save and restore copies of the database"), self.on_snapshots, running and not busy),
            ("package-x-generic-symbolic", "composer install", None, lambda: self.quick("composer install", "ddev composer install"), running and not busy),
            ("package-x-generic-symbolic", "npm install", None, lambda: self.quick("npm install", "ddev npm install"), running and not busy),
        ]
        for icon, label, tip, cb, sensitive in items:
            b = icon_button(icon, label, tip, cb)
            b.set_sensitive(sensitive)
            tools.add(b)
        tools_frame.add(tools)
        columns.pack_start(tools_frame, True, True, 0)

        # quick commands
        body.pack_start(self._commands_frame(p, running), False, False, 0)

        self.detail.show_all()
        stack.set_visible_child_name(self.current_page)
        switcher.set_stack(stack)  # after choosing the page so the right button is active
        stack.connect("notify::visible-child-name", self._on_page_changed, gitview)

    def _load_xdebug(self, p, switch):
        def work():
            state = ddev.xdebug_enabled(p["approot"])
            GLib.idle_add(apply, state)

        def apply(state):
            if state is None or switch.get_parent() is None:  # unknown, or the detail was redrawn
                return False
            switch.set_active(state)
            switch.set_sensitive(True)
            switch.connect("notify::active", lambda sw, _ps: self._toggle_xdebug(p, sw.get_active()))
            return False

        threading.Thread(target=work, daemon=True).start()

    def _toggle_xdebug(self, p, on):
        title = _("Enabling Xdebug") if on else _("Disabling Xdebug")
        done = _("Xdebug enabled") if on else _("Xdebug disabled")
        script = ddev.script_simple(p["approot"], [(title, f"ddev xdebug {'on' if on else 'off'}")], done)
        self.terms.run(f"{p['name']}: Xdebug", script, cwd=p["approot"])

    def _commands_frame(self, p, running):
        frame = Gtk.Frame(label=" " + _("Quick commands") + " ")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, min_children_per_line=2,
                           margin=10, column_spacing=6, row_spacing=6, homogeneous=True)
        approot = p["approot"]
        groups = [
            (commands.builtin_commands(p.get("cfg_type") or p.get("type") or ""), False),
            (commands.package_scripts(approot), False),
            (commands.composer_commands(approot), False),
            (commands.saved_commands(p["name"]), True),
        ]
        for items, saved in groups:
            for label, cmd, kind in items:
                icon = "starred-symbolic" if saved else (
                    "utilities-terminal-symbolic" if kind == "interactive" else
                    "dialog-warning-symbolic" if kind == "danger" else "system-run-symbolic")
                tip = cmd + ("\n" + _("Right-click to remove") if saved else "")
                b = icon_button(icon, label, tip, lambda c=cmd, k=kind, l=label: self.run_command(p, l, c, k))
                b.set_sensitive(running)
                if saved:
                    b.connect("button-press-event", self._on_saved_command_click, p["name"], label)
                flow.add(b)
        add = icon_button("list-add-symbolic", _("Add command…"), _("Save your own command for this project"), lambda: self.on_add_command(p))
        flow.add(add)
        frame.add(flow)
        return frame

    def run_command(self, p, label, cmd, kind):
        title = f"{p['name']}: {label}"
        if kind == "danger" and not self.confirm(
            _("Run “{label}”?").format(label=label),
            _("This command can delete data in the database of {name}.").format(name=p["name"]),
            _("Run"), destructive=True,
        ):
            return
        if kind == "interactive":
            self.terms.interactive(title, cmd, cwd=p["approot"])
        else:
            self.terms.run(title, ddev.script_simple(p["approot"], [(label, cmd)], _("Done")), cwd=p["approot"])

    def on_add_command(self, p):
        dlg = CommandDialog(self)
        values = dlg.values() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if values:
            commands.add_command(p["name"], *values)
            self.render_detail()

    def _on_saved_command_click(self, _btn, event, project_name, label):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label=_("Remove “{label}”").format(label=label))
        item.connect("activate", lambda *_a: (commands.remove_command(project_name, label), self.render_detail()))
        menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _on_page_changed(self, stack, _pspec, gitview):
        if self._rebuilding:
            return
        self.current_page = stack.get_visible_child_name()
        if self.current_page == "git":
            gitview.refresh()

    def _git_view(self, p):
        view = self.git_views.get(p["name"])
        if view is None or view.approot != p["approot"]:
            def run(title, script, on_done):
                def done(code):
                    self.refresh()
                    on_done(code)
                self.terms.run(title, script, on_done=done)
            view = GitView(p["approot"], run, self)
            self.git_views[p["name"]] = view
        return view

    # ================================================================ helpers
    def open_uri(self, uri):
        if uri:
            Gtk.show_uri_on_window(self, uri, Gdk.CURRENT_TIME)

    def open_editor(self, path):
        Gio.Subprocess.new([self.editor, path], Gio.SubprocessFlags.NONE)

    def error(self, title, text=""):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=title)
        dlg.format_secondary_text(text)
        dlg.run()
        dlg.destroy()

    def confirm(self, title, text, ok_label, destructive=False):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION, text=title)
        dlg.format_secondary_text(text)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        btn = dlg.add_button(ok_label, Gtk.ResponseType.OK)
        btn.get_style_context().add_class("destructive-action" if destructive else "suggested-action")
        answer = dlg.run()
        dlg.destroy()
        return answer == Gtk.ResponseType.OK

    def run_script(self, title, script, project=None, cwd=None):
        name = project["name"] if project else None
        if name:
            self.busy.add(name)
            self.render_detail()
            self._update_tray()

        def done(_code):
            if name:
                self.busy.discard(name)
                self._update_tray()
            self.refresh()
            if self.selected and self.selected.get("name") == name:
                self.render_detail()

        self.terms.run(title, script, cwd=cwd, on_done=done)

    # ================================================================ menu
    def on_preferences(self):
        app = self.get_application()
        dlg = PreferencesDialog(self, app.prefs)
        values = dlg.values() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if values:
            app.apply_preferences(values)

    def on_about(self):
        dlg = Gtk.AboutDialog(transient_for=self, modal=True)
        dlg.set_program_name("Panel DDEV")
        dlg.set_version(__version__)
        dlg.set_comments(
            _("Create, clone and manage your DDEV projects from one window.") + "\n"
            + _("Independent project, not affiliated with the DDEV project.")
        )
        dlg.set_website(REPO_URL)
        dlg.set_website_label(_("Repository on GitHub"))
        dlg.set_authors([AUTHOR])
        dlg.set_copyright(f"© 2026 {AUTHOR}")
        dlg.set_license_type(Gtk.License.MIT_X11)
        dlg.add_credit_section(_("Terms of use"), [f"{_('Terms and privacy')} {REPO_URL}/blob/main/TERMS.md"])
        if Path(ICON).exists():
            dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(ICON, 96, 96))
        dlg.run()
        dlg.destroy()

    # ================================================================ actions
    def action(self, verb):
        self.project_action(self.selected, verb)

    def project_action(self, p, verb):
        labels = {
            "start": (_("Starting {name}"), _("Project running")),
            "stop": (_("Stopping {name}"), _("Project stopped")),
            "restart": (_("Restarting {name}"), _("Project restarted")),
        }
        doing, done = labels[verb]
        script = ddev.script_simple(p["approot"], [(doing.format(name=p["name"]), f"ddev {verb}")], done)
        self.run_script(f"{p['name']}: {verb}", script, p)

    def quick(self, title, command):
        p = self.selected
        self.run_script(f"{p['name']}: {title}", ddev.script_simple(p["approot"], [(title, command)], _("Done")), p)

    def on_poweroff(self):
        if self.confirm(_("Stop all projects?"), _("Every DDEV container is stopped. Your files and databases are kept."), _("Stop all")):
            self.poweroff_now()

    def poweroff_now(self):
        self.run_script(_("Stop all"), ddev.script_simple(None, [(_("Stopping every project"), "ddev poweroff")], _("Everything stopped")))

    def _project_dialog(self, mode, project=None):
        dlg = ProjectDialog(self, mode, project)
        options = dlg.options() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return options

    def on_new(self):
        o = self._project_dialog("new")
        if o:
            self._pending_select = o["name"]
            self.run_script(f"{o['name']}: {_('create')}", ddev.script_create(o), {"name": o["name"]})

    def on_clone(self):
        o = self._project_dialog("clone")
        if o:
            self._pending_select = o["name"]
            self.run_script(f"{o['name']}: {_('clone')}", ddev.script_create(o), {"name": o["name"]})

    def on_add_existing(self):
        o = self._project_dialog("existing")
        if o:
            self._pending_select = o["name"]
            self.run_script(f"{o['name']}: {_('add')}", ddev.script_create(o), {"name": o["name"]})

    def on_edit(self):
        p = self.selected
        o = self._project_dialog("edit", p)
        if o:
            self.run_script(f"{p['name']}: {_('configure')}", ddev.script_edit(p["approot"], o, p.get("cfg_db", "")), p)

    def on_ssh(self):
        p = self.selected
        self.terms.interactive(f"{p['name']}: {_('terminal')}", "ddev ssh", cwd=p["approot"])

    def on_logs(self):
        p = self.selected
        self.terms.interactive(f"{p['name']}: logs", "ddev logs -f", cwd=p["approot"])

    def on_phpmyadmin(self):
        p = self.selected
        if ddev.has_phpmyadmin(p["approot"]):
            Gio.Subprocess.new(ddev.shell_argv(f"cd {ddev._q(p['approot'])} && ddev phpmyadmin"), Gio.SubprocessFlags.NONE)
            return
        if self.confirm(_("phpMyAdmin is not installed in this project"), _("The official add-on will be added and the project restarted."), _("Install")):
            script = ddev.script_simple(
                p["approot"],
                [
                    (_("Adding phpMyAdmin"), "ddev add-on get ddev/ddev-phpmyadmin"),
                    (_("Restarting"), "ddev restart"),
                    (_("Opening phpMyAdmin"), "ddev phpmyadmin"),
                ],
                _("phpMyAdmin ready"),
            )
            self.run_script(f"{p['name']}: phpMyAdmin", script, p)

    def _choose_file(self, title, action, ok, name=None):
        dlg = Gtk.FileChooserNative(title=title, transient_for=self, action=action, accept_label=ok)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        dlg.set_current_folder(downloads or str(ddev.HOME))
        if name:
            dlg.set_current_name(name)
            dlg.set_do_overwrite_confirmation(True)
        else:
            f = Gtk.FileFilter()
            f.set_name(_("SQL dumps (.sql, .sql.gz, .zip…)"))
            for pat in ("*.sql", "*.sql.gz", "*.sql.bz2", "*.sql.xz", "*.zip", "*.tar.gz", "*.gz"):
                f.add_pattern(pat)
            dlg.add_filter(f)
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.ACCEPT else None
        dlg.destroy()
        return path

    def on_import_db(self):
        p = self.selected
        path = self._choose_file(_("Import database"), Gtk.FileChooserAction.OPEN, _("Import"))
        if path and self.confirm(
            _("Import this file?"),
            _("The current database of {name} is replaced with:\n{path}").format(name=p["name"], path=path),
            _("Import"),
            destructive=True,
        ):
            script = ddev.script_simple(p["approot"], [(_("Importing database"), f"ddev import-db --file={ddev._q(path)}")], _("Database imported"))
            self.run_script(f"{p['name']}: {_('import DB')}", script, p)

    def on_export_db(self):
        p = self.selected
        stamp = GLib.DateTime.new_now_local().format("%Y%m%d-%H%M")
        path = self._choose_file(_("Export database"), Gtk.FileChooserAction.SAVE, _("Export"), f"{p['name']}-{stamp}.sql.gz")
        if path:
            script = ddev.script_simple(p["approot"], [(_("Exporting database"), f"ddev export-db --file={ddev._q(path)}")], _("Saved to {path}").format(path=path))
            self.run_script(f"{p['name']}: {_('export DB')}", script, p)

    def on_snapshots(self):
        p = self.selected
        dlg = snapshots.SnapshotsDialog(self, p)
        dlg.run()
        action = dlg.action
        dlg.destroy()
        if not action:
            return
        kind, name = action
        if kind == "restore" and not self.confirm(
            _("Restore snapshot {name}?").format(name=name),
            _("The current database of {project} is replaced with this snapshot.").format(project=p["name"]),
            _("Restore"), destructive=True,
        ):
            return
        if kind == "delete" and not self.confirm(
            _("Delete snapshot {name}?").format(name=name), _("This cannot be undone."), _("Delete"), destructive=True,
        ):
            return
        script = {"create": snapshots.script_create, "restore": snapshots.script_restore, "delete": snapshots.script_delete}[kind](p, name)
        self.run_script(f"{p['name']}: snapshot", script, p)

    def on_delete(self):
        p = self.selected
        if self.confirm(
            _("Delete {name} from DDEV?").format(name=p["name"]),
            _("Its containers and database are removed (no backup). Your files in {path} are NOT touched.").format(path=p.get("shortroot")),
            _("Delete"),
            destructive=True,
        ):
            script = ddev.script_simple(None, [(_("Deleting {name}").format(name=p["name"]), f"ddev delete --omit-snapshot --yes {ddev._q(p['name'])}")], _("Project removed from DDEV"))
            self.selected = None
            self.run_script(f"{p['name']}: {_('delete')}", script, p)


class PanelApp(Gtk.Application):
    def __init__(self, hidden=False, app_id=APP_ID):
        super().__init__(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.start_hidden = hidden
        self.tray = None
        self.prefs = settings.load()
        i18n.set_language(self.prefs["language"])

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings.apply_theme(self.prefs["theme"])

    def _launcher(self):
        return shutil.which("panel-ddev") or str(Path(__file__).resolve().parent.parent / "panel-ddev")

    def _new_window(self):
        win = MainWindow(self)
        if self.tray:
            win.connect("delete-event", lambda w, _e: w.hide() or True)
        return win

    def do_activate(self):
        win = self.get_windows()[0] if self.get_windows() else None
        if win is None:
            if traymod.available():
                win = MainWindow(self)
                self.tray = traymod.Tray(self, win, ICON, self._launcher())
                self.hold()  # stay alive in the tray when the window is closed
                win.connect("delete-event", lambda w, _e: w.hide() or True)
                if self.start_hidden:
                    win.hide()
                    return
            else:
                win = MainWindow(self)
        win.show()
        win.present()

    def apply_preferences(self, values):
        old = dict(self.prefs)
        # reload first: other parts of the app (saved commands) write to the same file
        self.prefs = {**settings.load(), **values}
        settings.save(self.prefs)
        dark = settings.apply_theme(self.prefs["theme"])
        for w in self.get_windows():
            if isinstance(w, MainWindow):
                w.terms.set_dark(dark)
        if self.prefs["language"] != old["language"]:
            self.rebuild_ui()

    def rebuild_ui(self):
        """Recreates the window so every label uses the new language."""
        i18n.set_language(self.prefs["language"])
        old = next((w for w in self.get_windows() if isinstance(w, MainWindow)), None)
        if old and old.terms.running_count():
            old.error(
                _("Language saved"),
                _("It will apply when the running actions finish and you reopen the app."),
            )
            return
        selected = old.selected["name"] if old and old.selected else None
        page = old.current_page if old else "project"
        win = self._new_window()
        win.current_page = page
        win._pending_select = selected
        if self.tray:
            self.tray.set_window(win)
            win._tray_sig = None
        if old:
            old.destroy()
        win.present()


def main():
    import sys

    hidden = "--hidden" in sys.argv
    argv = [a for a in sys.argv if a != "--hidden"]
    return PanelApp(hidden).run(argv)
