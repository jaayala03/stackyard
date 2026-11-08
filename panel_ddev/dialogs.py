"""Dialogs: create / clone / edit a project, and preferences."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import ddev, github, settings  # noqa: E402
from .i18n import _  # noqa: E402


def combo(options, active, translate=True):
    box = Gtk.ComboBoxText()
    for value, label, *_rest in options:
        box.append(value, _(label) if translate else label)
    if not box.set_active_id(active):
        box.set_active(0)
    return box


class ProjectDialog(Gtk.Dialog):
    """mode: 'new', 'clone' or 'edit'."""

    TITLES = {"new": "New project", "clone": "Clone a project with git", "edit": "Project settings"}
    OK = {"new": "Create", "clone": "Clone and create", "edit": "Apply and restart"}

    def __init__(self, parent, mode, project=None):
        super().__init__(title=_(self.TITLES[mode]), transient_for=parent, modal=True)
        self.mode = mode
        self.project = project or {}
        self.set_default_size(520, -1)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.ok_btn = self.add_button(_(self.OK[mode]), Gtk.ResponseType.OK)
        self.ok_btn.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self._docroot_touched = False
        self._name_touched = False

        grid = Gtk.Grid(column_spacing=12, row_spacing=10, margin=18)
        self.get_content_area().add(grid)
        self.grid = grid
        self._row = 0

        p = self.project
        # ---------- source
        if mode == "clone":
            self._section(_("Repository"))
            self.repo = Gtk.Entry(placeholder_text="https://github.com/user/project.git")
            self.repo.connect("changed", self._on_repo_changed)
            url_box = Gtk.Box(spacing=6)
            url_box.pack_start(self.repo, True, True, 0)
            browse = Gtk.Button(label=_("My repositories…"))
            if github.gh_logged_in():
                browse.set_tooltip_text(_("Pick one of your GitHub repositories"))
                browse.connect("clicked", self._on_browse)
            else:
                browse.set_sensitive(False)
                browse.set_tooltip_text(_("Install the GitHub CLI (gh) and run “gh auth login” to list your repositories"))
            url_box.pack_start(browse, False, False, 0)
            self._add(_("URL"), url_box)
            self.branch = Gtk.Entry(placeholder_text=_("the default branch"))
            self._add(_("Branch"), self.branch)

        if mode != "edit":
            self._section(_("Project"))
            self.name = Gtk.Entry(placeholder_text="my-project")
            self.name.connect("changed", self._on_name_changed)
            self._add(_("Name"), self.name)
            self.parent_dir = Gtk.FileChooserButton(
                title=_("Folder where the project is saved"),
                action=Gtk.FileChooserAction.SELECT_FOLDER,
            )
            ddev.DEFAULT_PARENT.mkdir(exist_ok=True)
            self.parent_dir.set_filename(str(ddev.DEFAULT_PARENT))
            self.parent_dir.connect("file-set", lambda *_a: self._validate())
            self._add(_("Save in"), self.parent_dir)
            self.summary = Gtk.Label(xalign=0, selectable=True)
            self.summary.get_style_context().add_class("dim-label")
            grid.attach(self.summary, 1, self._row, 1, 1)
            self._row += 1

        # ---------- environment
        self._section(_("Environment"))
        types = ([ddev.AUTO_TYPE] if mode == "clone" else []) + ddev.PROJECT_TYPES
        current_type = p.get("cfg_type") or p.get("type") or ("" if mode == "clone" else "php")
        self.type = combo(types, current_type)
        self.type.connect("changed", self._on_type_changed)
        self._add(_("Type"), self.type)
        self.docroot = Gtk.Entry(placeholder_text=_("project root"))
        self.docroot.set_text(p.get("cfg_docroot", "") if mode == "edit" else "")
        self.docroot.connect("changed", lambda *_a: setattr(self, "_docroot_touched", True))
        self._add(_("Public folder"), self.docroot, _("The folder served on the web (e.g. public)."))
        self.php = combo([(v, f"PHP {v}") for v in ddev.PHP_VERSIONS], p.get("cfg_php") or ddev.DEFAULTS["php"], False)
        self._add("PHP", self.php)
        self.node = combo([(v, f"Node {v}") for v in ddev.NODE_VERSIONS], p.get("cfg_node") or ddev.DEFAULTS["node"], False)
        self._add("Node", self.node)
        self.webserver = combo(ddev.WEBSERVERS, p.get("cfg_webserver") or ddev.DEFAULTS["webserver"], False)
        self._add(_("Web server"), self.webserver)
        self.old_db = p.get("cfg_db", "")
        db_opts = list(ddev.DATABASES)
        if self.old_db and self.old_db not in [d[0] for d in db_opts]:
            db_opts.insert(0, (self.old_db, self.old_db))
        self.db = combo(db_opts, self.old_db or ddev.DEFAULTS["db"], False)
        self._add(
            _("Database"),
            self.db,
            _("Changing it migrates your data (MariaDB ↔ MySQL). PostgreSQL cannot be migrated.")
            if mode == "edit" else None,
        )

        # ---------- options
        if mode != "edit":
            self._section(_("Options"))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            if mode == "new":
                self.scaffold = Gtk.CheckButton()
                box.pack_start(self.scaffold, False, False, 0)
            else:
                self.deps = Gtk.CheckButton(label=_("Install dependencies (composer install, npm install)"), active=True)
                box.pack_start(self.deps, False, False, 0)
            self.pma = Gtk.CheckButton(label=_("Add phpMyAdmin"))
            box.pack_start(self.pma, False, False, 0)
            self.launch = Gtk.CheckButton(label=_("Open in the browser when done"), active=True)
            box.pack_start(self.launch, False, False, 0)
            grid.attach(box, 0, self._row, 2, 1)
            self._row += 1

        self.error = Gtk.Label(xalign=0, wrap=True)
        grid.attach(self.error, 0, self._row, 2, 1)

        self._on_type_changed(self.type, initial=True)
        self.show_all()
        if mode == "new":
            self.name.grab_focus()
        elif mode == "clone":
            self.repo.grab_focus()
        self._validate()

    # ------------------------------------------------------------ layout helpers
    def _add(self, label, widget, hint=None):
        lbl = Gtk.Label(label=label, xalign=1)
        lbl.get_style_context().add_class("dim-label")
        self.grid.attach(lbl, 0, self._row, 1, 1)
        widget.set_hexpand(True)
        self.grid.attach(widget, 1, self._row, 1, 1)
        self._row += 1
        if hint:
            h = Gtk.Label(label=hint, xalign=0, wrap=True, max_width_chars=50)
            h.get_style_context().add_class("dim-label")
            self.grid.attach(h, 1, self._row, 1, 1)
            self._row += 1

    def _section(self, text):
        lbl = Gtk.Label(xalign=0, margin_top=6 if self._row else 0)
        lbl.set_markup(f"<b>{text}</b>")
        self.grid.attach(lbl, 0, self._row, 2, 1)
        self._row += 1

    # ------------------------------------------------------------ events
    def _on_repo_changed(self, entry):
        if not self._name_touched:
            self.name.handler_block_by_func(self._on_name_changed)
            self.name.set_text(ddev.name_from_repo(entry.get_text().strip()))
            self.name.handler_unblock_by_func(self._on_name_changed)
        self._validate()

    def _on_browse(self, _btn):
        picker = github.RepoPicker(self)
        if picker.run() == Gtk.ResponseType.OK and picker.selected:
            self.repo.set_text(github.clone_url(picker.selected, picker.protocol))
            self.name.grab_focus()
        picker.destroy()

    def _on_name_changed(self, _entry):
        self._name_touched = True
        self._validate()

    def _on_type_changed(self, box, initial=False):
        t = box.get_active_id() or ""
        if not (initial and self.mode == "edit") and not self._docroot_touched:
            default = next((d for v, _l, d in ddev.PROJECT_TYPES if v == t), "")
            self.docroot.set_text(default)  # fires "changed"…
            self._docroot_touched = False  # …but it is not a user edit
        self.docroot.set_sensitive(t != "")
        if self.mode == "new":
            framework = ddev.label_for(ddev.PROJECT_TYPES, t)
            self.scaffold.set_label(
                _("Download and install a fresh {framework}").format(framework=framework)
                if ddev.SCAFFOLD.get(t) else _("Create a test index.php")
            )
            self.scaffold.set_active(True)
            self.scaffold.set_visible(t != "generic")
        self._validate()

    # ------------------------------------------------------------ validation
    def _target(self):
        parent = self.parent_dir.get_filename() or str(ddev.DEFAULT_PARENT)
        return Path(parent) / self.name.get_text().strip()

    def _validate(self):
        msg = ""
        if self.mode != "edit":
            name = self.name.get_text().strip()
            target = self._target()
            if self.mode == "clone" and not self.repo.get_text().strip():
                msg = _("Enter the repository URL.")
            elif not name:
                msg = _("Enter a name for the project.")
            elif not ddev.NAME_RE.match(name):
                msg = _("The name can only contain lowercase letters, numbers and hyphens.")
            elif target.exists() and any(target.iterdir()):
                msg = _("The folder {path} already exists and is not empty.").format(path=target)
            if name and ddev.NAME_RE.match(name):
                self.summary.set_text(f"{target}\nhttps://{name}.{ddev.project_tld()}")
            else:
                self.summary.set_text("")
        self.error.set_markup(f'<span foreground="#e01b24">{msg}</span>' if msg else "")
        self.ok_btn.set_sensitive(not msg)

    # ------------------------------------------------------------ result
    def options(self):
        o = {
            "mode": self.mode,
            "type": self.type.get_active_id() or "",
            "docroot": self.docroot.get_text().strip(),
            "php": self.php.get_active_id(),
            "node": self.node.get_active_id(),
            "webserver": self.webserver.get_active_id(),
            "db": self.db.get_active_id(),
        }
        if self.mode != "edit":
            o.update(
                name=self.name.get_text().strip(),
                path=str(self._target()),
                phpmyadmin=self.pma.get_active(),
                launch=self.launch.get_active(),
            )
        if self.mode == "new":
            o["scaffold"] = self.scaffold.get_active()
        if self.mode == "clone":
            o.update(
                repo=self.repo.get_text().strip(),
                branch=self.branch.get_text().strip(),
                deps=self.deps.get_active(),
            )
        return o


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, parent, values):
        super().__init__(title=_("Preferences"), transient_for=parent, modal=True)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        ok = self.add_button(_("Save"), Gtk.ResponseType.OK)
        ok.get_style_context().add_class("suggested-action")
        grid = Gtk.Grid(column_spacing=12, row_spacing=10, margin=18)
        self.get_content_area().add(grid)

        self.language = combo(settings.LANGUAGES, values.get("language", "auto"))
        self.theme = combo(settings.THEMES, values.get("theme", "system"))
        for row, (label, widget) in enumerate(((_("Language"), self.language), (_("Appearance"), self.theme))):
            lbl = Gtk.Label(label=label, xalign=1)
            lbl.get_style_context().add_class("dim-label")
            grid.attach(lbl, 0, row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, row, 1, 1)
        self.show_all()

    def values(self):
        return {"language": self.language.get_active_id(), "theme": self.theme.get_active_id()}
