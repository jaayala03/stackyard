"""Diálogo para crear, clonar o editar un proyecto."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import ddev  # noqa: E402


def _combo(options, active):
    combo = Gtk.ComboBoxText()
    for value, label, *_ in options:
        combo.append(value, label)
    if not combo.set_active_id(active):
        combo.set_active(0)
    return combo


class ProjectDialog(Gtk.Dialog):
    """mode: 'new', 'clone' o 'edit'."""

    TITLES = {"new": "Nuevo proyecto", "clone": "Clonar proyecto con git", "edit": "Configuración del proyecto"}
    OK = {"new": "Crear", "clone": "Clonar y crear", "edit": "Aplicar y reiniciar"}

    def __init__(self, parent, mode, project=None):
        super().__init__(title=self.TITLES[mode], transient_for=parent, modal=True)
        self.mode = mode
        self.project = project or {}
        self.set_default_size(520, -1)
        self.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        self.ok_btn = self.add_button(self.OK[mode], Gtk.ResponseType.OK)
        self.ok_btn.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self._docroot_touched = False
        self._name_touched = False

        grid = Gtk.Grid(column_spacing=12, row_spacing=10, margin=18)
        self.get_content_area().add(grid)
        self._row = 0

        def add(label, widget, hint=None):
            lbl = Gtk.Label(label=label, xalign=1)
            lbl.get_style_context().add_class("dim-label")
            grid.attach(lbl, 0, self._row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, self._row, 1, 1)
            self._row += 1
            if hint:
                h = Gtk.Label(label=hint, xalign=0, wrap=True, max_width_chars=50)
                h.get_style_context().add_class("dim-label")
                grid.attach(h, 1, self._row, 1, 1)
                self._row += 1

        def section(text):
            lbl = Gtk.Label(xalign=0, margin_top=6 if self._row else 0)
            lbl.set_markup(f"<b>{text}</b>")
            grid.attach(lbl, 0, self._row, 2, 1)
            self._row += 1

        p = self.project
        # ---------- origen
        if mode == "clone":
            section("Repositorio")
            self.repo = Gtk.Entry(placeholder_text="https://github.com/usuario/proyecto.git")
            self.repo.connect("changed", self._on_repo_changed)
            add("URL", self.repo)
            self.branch = Gtk.Entry(placeholder_text="la rama por defecto")
            add("Rama", self.branch)

        if mode != "edit":
            section("Proyecto")
            self.name = Gtk.Entry(placeholder_text="mi-proyecto")
            self.name.connect("changed", self._on_name_changed)
            add("Nombre", self.name)
            self.parent_dir = Gtk.FileChooserButton(
                title="Carpeta donde guardar el proyecto",
                action=Gtk.FileChooserAction.SELECT_FOLDER,
            )
            ddev.DEFAULT_PARENT.mkdir(exist_ok=True)
            self.parent_dir.set_filename(str(ddev.DEFAULT_PARENT))
            self.parent_dir.connect("file-set", lambda *_: self._validate())
            add("Guardar en", self.parent_dir)
            self.summary = Gtk.Label(xalign=0, selectable=True)
            self.summary.get_style_context().add_class("dim-label")
            grid.attach(self.summary, 1, self._row, 1, 1)
            self._row += 1

        # ---------- entorno
        section("Entorno")
        types = ([ddev.AUTO_TYPE] if mode == "clone" else []) + ddev.PROJECT_TYPES
        current_type = p.get("cfg_type") or p.get("type") or ("" if mode == "clone" else "php")
        self.type = _combo(types, current_type)
        self.type.connect("changed", self._on_type_changed)
        add("Tipo", self.type)
        self.docroot = Gtk.Entry(placeholder_text="raíz del proyecto")
        self.docroot.set_text(p.get("cfg_docroot", "") if mode == "edit" else "")
        self.docroot.connect("changed", lambda *_: setattr(self, "_docroot_touched", True))
        add("Carpeta pública", self.docroot, "La carpeta que se sirve en la web (p. ej. public).")
        self.php = _combo([(v, f"PHP {v}") for v in ddev.PHP_VERSIONS], p.get("cfg_php") or ddev.DEFAULTS["php"])
        add("PHP", self.php)
        self.node = _combo([(v, f"Node {v}") for v in ddev.NODE_VERSIONS], p.get("cfg_node") or ddev.DEFAULTS["node"])
        add("Node", self.node)
        self.webserver = _combo(ddev.WEBSERVERS, p.get("cfg_webserver") or ddev.DEFAULTS["webserver"])
        add("Servidor web", self.webserver)
        self.old_db = p.get("cfg_db", "")
        db_opts = list(ddev.DATABASES)
        if self.old_db and self.old_db not in [d[0] for d in db_opts]:
            db_opts.insert(0, (self.old_db, self.old_db))
        self.db = _combo(db_opts, self.old_db or ddev.DEFAULTS["db"])
        add(
            "Base de datos",
            self.db,
            "Cambiarla migra tus datos (MariaDB ↔ MySQL). Con PostgreSQL no se puede migrar."
            if mode == "edit" else None,
        )

        # ---------- opciones
        if mode != "edit":
            section("Opciones")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            if mode == "new":
                self.scaffold = Gtk.CheckButton()
                box.pack_start(self.scaffold, False, False, 0)
            else:
                self.deps = Gtk.CheckButton(label="Instalar dependencias (composer install, npm install)", active=True)
                box.pack_start(self.deps, False, False, 0)
            self.pma = Gtk.CheckButton(label="Añadir phpMyAdmin")
            box.pack_start(self.pma, False, False, 0)
            self.launch = Gtk.CheckButton(label="Abrir en el navegador al terminar", active=True)
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

    # ------------------------------------------------------------ eventos
    def _on_repo_changed(self, entry):
        if not self._name_touched:
            self.name.handler_block_by_func(self._on_name_changed)
            self.name.set_text(ddev.name_from_repo(entry.get_text().strip()))
            self.name.handler_unblock_by_func(self._on_name_changed)
        self._validate()

    def _on_name_changed(self, _entry):
        self._name_touched = True
        self._validate()

    def _on_type_changed(self, combo, initial=False):
        t = combo.get_active_id() or ""
        if not (initial and self.mode == "edit") and not self._docroot_touched:
            default = next((d for v, _l, d in ddev.PROJECT_TYPES if v == t), "")
            self.docroot.set_text(default)  # dispara «changed»…
            self._docroot_touched = False  # …pero no cuenta como edición del usuario
        self.docroot.set_sensitive(t != "")
        if self.mode == "new":
            scaffold = ddev.SCAFFOLD.get(t)
            label = ddev.label_for(ddev.PROJECT_TYPES, t)
            self.scaffold.set_label(
                f"Descargar e instalar {label} nuevo" if scaffold else "Crear un index.php de prueba"
            )
            self.scaffold.set_active(True)
            self.scaffold.set_visible(t != "generic")
        self._validate()

    # ------------------------------------------------------------ validación
    def _target(self):
        parent = self.parent_dir.get_filename() or str(ddev.DEFAULT_PARENT)
        return Path(parent) / self.name.get_text().strip()

    def _validate(self):
        msg = ""
        if self.mode != "edit":
            name = self.name.get_text().strip()
            target = self._target()
            if self.mode == "clone" and not self.repo.get_text().strip():
                msg = "Escribe la URL del repositorio."
            elif not name:
                msg = "Escribe un nombre para el proyecto."
            elif not ddev.NAME_RE.match(name):
                msg = "El nombre solo puede tener minúsculas, números y guiones."
            elif target.exists() and any(target.iterdir()):
                msg = f"La carpeta {target} ya existe y no está vacía."
            if name and ddev.NAME_RE.match(name):
                self.summary.set_text(f"{target}\nhttps://{name}.{ddev.project_tld()}")
            else:
                self.summary.set_text("")
        self.error.set_markup(f'<span foreground="#e01b24">{msg}</span>' if msg else "")
        self.ok_btn.set_sensitive(not msg)

    # ------------------------------------------------------------ resultado
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
