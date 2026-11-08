"""Ventana principal de Panel DDEV."""

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import ddev  # noqa: E402
from .dialogs import ProjectDialog  # noqa: E402
from .git import GitView  # noqa: E402
from .terminal import TerminalTabs  # noqa: E402

APP_ID = "local.panel.ddev"
REFRESH_SECONDS = 10
ICON = str(Path(__file__).resolve().parent.parent / "icono.svg")

CSS = b"""
.status-dot { font-size: 14px; }
.running { color: #2ec27e; }
.stopped, .paused { color: #9a9996; }
.unhealthy, .starting { color: #e5a50a; }
.project-title { font-size: 20px; font-weight: bold; }
.danger { color: #e01b24; }
"""

STATUS_ES = {
    "running": "En marcha",
    "stopped": "Detenido",
    "paused": "Pausado",
    "starting": "Arrancando",
    "unhealthy": "Con problemas",
}


def _icon_button(icon, label, tooltip=None, cb=None):
    btn = Gtk.Button()
    box = Gtk.Box(spacing=6)
    box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
    box.pack_start(Gtk.Label(label=label), False, False, 0)
    btn.add(box)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    if cb:
        btn.connect("clicked", lambda *_: cb())
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
        self.busy = set()  # proyectos con una acción en marcha
        self.editor = ddev.find_editor()

        # ---------------- barra superior
        header = Gtk.HeaderBar(show_close_button=True, title="Panel DDEV")
        self.set_titlebar(header)
        self.header = header
        header.pack_start(_icon_button("document-new-symbolic", "Nuevo", "Crear un proyecto nuevo", self.on_new))
        header.pack_start(_icon_button("folder-download-symbolic", "Clonar", "Clonar un repositorio con git", self.on_clone))
        header.pack_end(_icon_button("system-shutdown-symbolic", "Apagar todo", "Detener todos los proyectos (ddev poweroff)", self.on_poweroff))
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Actualizar")
        refresh.connect("clicked", lambda *_: self.refresh())
        header.pack_end(refresh)

        # ---------------- lista de proyectos
        self.listbox = Gtk.ListBox()
        self.listbox.set_placeholder(self._placeholder_label("Todavía no hay proyectos.\nCrea uno con «Nuevo» o «Clonar»."))
        self.listbox.connect("row-selected", self.on_row_selected)
        list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        list_scroll.set_size_request(280, -1)
        list_scroll.add(self.listbox)

        # ---------------- detalle
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.git_views = {}
        self.current_page = "proyecto"

        top = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        top.pack1(list_scroll, False, False)
        top.pack2(self.detail, True, False)

        # ---------------- terminal
        self.terms = TerminalTabs()
        bottom = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        bottom.pack1(top, True, False)
        bottom.pack2(self.terms, False, True)
        bottom.set_position(440)
        self.add(bottom)

        self.show_all()
        screen = self.get_screen()
        if screen.get_height() < 900:
            self.maximize()
        self.render_detail()
        if not ddev.ddev_installed():
            self.error("DDEV no está instalado", "Instálalo primero: https://ddev.com/get-started/")
            return
        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._auto_refresh)

    # ================================================================ datos
    def _auto_refresh(self):
        if self.get_visible():
            self.refresh()
            if self.current_page == "git" and self.selected:
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
                GLib.idle_add(self.header.set_subtitle, f"Error al leer los proyectos: {exc}"[:120])

        threading.Thread(target=work, daemon=True).start()

    def set_projects(self, projects):
        prev = self.selected["name"] if self.selected else None
        pending = getattr(self, "_pending_select", None)
        if pending and any(p["name"] == pending for p in projects):
            prev, self._pending_select = pending, None
            self.projects = []  # fuerza a redibujar y seleccionar el nuevo
        changed = [(p["name"], p.get("status"), p.get("cfg_php"), p.get("cfg_node"), p.get("cfg_webserver"), p.get("cfg_db")) for p in projects] != [
            (p["name"], p.get("status"), p.get("cfg_php"), p.get("cfg_node"), p.get("cfg_webserver"), p.get("cfg_db")) for p in self.projects
        ]
        self.projects = projects
        running = sum(1 for p in projects if p.get("status") == "running")
        self.header.set_subtitle(f"{len(projects)} proyecto{'' if len(projects) == 1 else 's'} · {running} en marcha")
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

    def on_row_selected(self, _lb, row):
        self.selected = row.project if row else None
        self.render_detail()

    # ================================================================ detalle
    def _placeholder_label(self, text):
        lbl = Gtk.Label(label=text, justify=Gtk.Justification.CENTER, margin=30)
        lbl.get_style_context().add_class("dim-label")
        lbl.show()
        return lbl

    def render_detail(self):
        # Las vistas Git se reutilizan (guardan el mensaje del commit y la selección):
        # se separan antes de destruir la cabecera vieja para que no se destruyan con ella.
        self._rebuilding = True  # al separar la vista Git, el Stack viejo cambia de página: ignorarlo
        for view in self.git_views.values():
            if view.get_parent():
                view.get_parent().remove(view)
        self._rebuilding = False
        for child in self.detail.get_children():
            self.detail.remove(child)
        p = self.selected
        if not p:
            self.detail.pack_start(self._placeholder_label("Selecciona un proyecto de la lista\no crea uno nuevo."), True, True, 0)
            self.detail.show_all()
            return

        status = p.get("status", "stopped")
        running = status == "running"
        busy = p["name"] in self.busy

        # cabecera
        title = Gtk.Label(label=p["name"], xalign=0)
        title.get_style_context().add_class("project-title")
        state = Gtk.Label(xalign=0)
        state_txt = "Trabajando…" if busy else STATUS_ES.get(status.split()[0], status)
        state.set_markup(f'<span size="large">●</span> {state_txt}')
        state.get_style_context().add_class(status.split()[0])
        head = Gtk.Box(spacing=14)
        head.pack_start(title, False, False, 0)
        head.pack_start(state, False, False, 0)
        delete = _icon_button("user-trash-symbolic", "Eliminar…", "Borra los contenedores y la base de datos; tus archivos se quedan", self.on_delete)
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
        stack.add_titled(body_scroll, "proyecto", "Proyecto")
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

        # acciones principales
        actions = Gtk.Box(spacing=8)
        start = _icon_button("media-playback-start-symbolic", "Iniciar", cb=lambda: self.action("start"))
        start.get_style_context().add_class("suggested-action")
        stop = _icon_button("media-playback-stop-symbolic", "Detener", cb=lambda: self.action("stop"))
        restart = _icon_button("view-refresh-symbolic", "Reiniciar", cb=lambda: self.action("restart"))
        start.set_sensitive(not running and not busy)
        stop.set_sensitive(running and not busy)
        restart.set_sensitive(running and not busy)
        for b in (start, stop, restart):
            actions.pack_start(b, False, False, 0)
        actions.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)
        web = _icon_button("web-browser-symbolic", "Abrir web", cb=lambda: self.open_uri(url))
        web.set_sensitive(running)
        actions.pack_start(web, False, False, 0)
        actions.pack_start(_icon_button("folder-open-symbolic", "Carpeta", cb=lambda: self.open_uri(Path(p["approot"]).as_uri())), False, False, 0)
        if self.editor:
            actions.pack_start(_icon_button("accessories-text-editor-symbolic", "Editor", f"Abrir con {self.editor}", lambda: self.open_editor(p["approot"])), False, False, 0)
        body.pack_start(actions, False, False, 0)

        # configuración
        frame = Gtk.Frame(label=" Configuración ")
        grid = Gtk.Grid(column_spacing=24, row_spacing=6, margin=12)
        rows = [
            ("Carpeta", p.get("shortroot") or p.get("approot")),
            ("Tipo", ddev.label_for(ddev.PROJECT_TYPES, p.get("cfg_type") or p.get("type"))),
            ("Carpeta pública", p.get("cfg_docroot") or "(raíz)"),
            ("PHP", p.get("cfg_php") or "—"),
            ("Node", p.get("cfg_node") or p.get("nodejs_version") or "—"),
            ("Servidor web", ddev.label_for(ddev.WEBSERVERS, p.get("cfg_webserver"))),
            ("Base de datos", ddev.label_for(ddev.DATABASES, p.get("cfg_db"))),
        ]
        for i, (k, v) in enumerate(rows):
            kl = Gtk.Label(label=k, xalign=0)
            kl.get_style_context().add_class("dim-label")
            grid.attach(kl, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=str(v), xalign=0, selectable=True), 1, i, 1, 1)
        edit = _icon_button("emblem-system-symbolic", "Cambiar configuración…", cb=self.on_edit)
        edit.set_sensitive(not busy)
        edit.set_halign(Gtk.Align.START)
        edit.set_margin_top(6)
        grid.attach(edit, 0, len(rows), 2, 1)
        frame.add(grid)
        columns = Gtk.Box(spacing=12, homogeneous=True)
        columns.pack_start(frame, True, True, 0)
        body.pack_start(columns, False, False, 0)

        # herramientas
        tools_frame = Gtk.Frame(label=" Herramientas ")
        tools = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2, min_children_per_line=2, margin=10, column_spacing=6, row_spacing=6, homogeneous=True)
        items = [
            ("utilities-terminal-symbolic", "Terminal", "Consola dentro del contenedor (ddev ssh)", self.on_ssh, running),
            ("text-x-generic-symbolic", "Logs", "Ver los logs en vivo", self.on_logs, running),
            ("network-server-symbolic", "phpMyAdmin", "Administrar la base de datos", self.on_phpmyadmin, running and not busy),
            ("mail-unread-symbolic", "Mailpit", "Ver los correos que envía tu app", lambda: self.open_uri(p.get("mailpit_https_url", "")), running),
            ("document-open-symbolic", "Importar BD…", "Importar un .sql o .sql.gz", self.on_import_db, running and not busy),
            ("document-save-symbolic", "Exportar BD…", "Guardar la base de datos en un archivo", self.on_export_db, running and not busy),
            ("package-x-generic-symbolic", "composer install", None, lambda: self.quick("composer install", "ddev composer install"), running and not busy),
            ("package-x-generic-symbolic", "npm install", None, lambda: self.quick("npm install", "ddev npm install"), running and not busy),
        ]
        for icon, label, tip, cb, sensitive in items:
            b = _icon_button(icon, label, tip, cb)
            b.set_sensitive(sensitive)
            tools.add(b)
        tools_frame.add(tools)
        columns.pack_start(tools_frame, True, True, 0)

        self.detail.show_all()
        stack.set_visible_child_name(self.current_page)
        switcher.set_stack(stack)  # después de elegir página, para que el botón activo sea el correcto
        stack.connect("notify::visible-child-name", self._on_page_changed, gitview)

    def _on_page_changed(self, stack, _pspec, gitview):
        if getattr(self, "_rebuilding", False):
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

    # ================================================================ utilidades
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
        dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
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

        def done(_code):
            if name:
                self.busy.discard(name)
            self.refresh()
            if self.selected and self.selected.get("name") == name:
                self.render_detail()

        self.terms.run(title, script, cwd=cwd, on_done=done)

    # ================================================================ acciones
    def action(self, verb):
        p = self.selected
        labels = {"start": ("Iniciando", "Proyecto en marcha"), "stop": ("Deteniendo", "Proyecto detenido"), "restart": ("Reiniciando", "Proyecto reiniciado")}
        doing, done = labels[verb]
        script = ddev.script_simple(p["approot"], [(f"{doing} {p['name']}", f"ddev {verb}")], done)
        self.run_script(f"{p['name']}: {verb}", script, p)

    def quick(self, title, command):
        p = self.selected
        self.run_script(f"{p['name']}: {title}", ddev.script_simple(p["approot"], [(title, command)], "Hecho"), p)

    def on_poweroff(self):
        if self.confirm("¿Apagar todos los proyectos?", "Se detienen todos los contenedores de DDEV. Tus archivos y bases de datos se conservan.", "Apagar todo"):
            self.run_script("Apagar todo", ddev.script_simple(None, [("Deteniendo todos los proyectos", "ddev poweroff")], "Todo apagado"))

    def _project_dialog(self, mode, project=None):
        dlg = ProjectDialog(self, mode, project)
        options = dlg.options() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return options

    def on_new(self):
        o = self._project_dialog("new")
        if o:
            self._pending_select = o["name"]
            self.run_script(f"{o['name']}: crear", ddev.script_create(o), {"name": o["name"]})

    def on_clone(self):
        o = self._project_dialog("clone")
        if o:
            self._pending_select = o["name"]
            self.run_script(f"{o['name']}: clonar", ddev.script_create(o), {"name": o["name"]})

    def on_edit(self):
        p = self.selected
        o = self._project_dialog("edit", p)
        if o:
            self.run_script(f"{p['name']}: configurar", ddev.script_edit(p["approot"], o, p.get("cfg_db", "")), p)

    def on_ssh(self):
        p = self.selected
        self.terms.interactive(f"{p['name']}: terminal", "ddev ssh", cwd=p["approot"])

    def on_logs(self):
        p = self.selected
        self.terms.interactive(f"{p['name']}: logs", "ddev logs -f", cwd=p["approot"])

    def on_phpmyadmin(self):
        p = self.selected
        if ddev.has_phpmyadmin(p["approot"]):
            Gio.Subprocess.new(ddev.shell_argv(f"cd {ddev._q(p['approot'])} && ddev phpmyadmin"), Gio.SubprocessFlags.NONE)
            return
        if self.confirm("phpMyAdmin no está instalado en este proyecto", "Se añadirá el complemento oficial y se reiniciará el proyecto.", "Instalar"):
            script = ddev.script_simple(
                p["approot"],
                [("Añadiendo phpMyAdmin", "ddev add-on get ddev/ddev-phpmyadmin"), ("Reiniciando", "ddev restart"), ("Abriendo phpMyAdmin", "ddev phpmyadmin")],
                "phpMyAdmin listo",
            )
            self.run_script(f"{p['name']}: phpMyAdmin", script, p)

    def _choose_file(self, title, action, ok, name=None):
        dlg = Gtk.FileChooserNative(title=title, transient_for=self, action=action, accept_label=ok)
        dlg.set_current_folder(str(ddev.HOME / "Descargas") if (ddev.HOME / "Descargas").exists() else str(ddev.HOME))
        if name:
            dlg.set_current_name(name)
            dlg.set_do_overwrite_confirmation(True)
        else:
            f = Gtk.FileFilter()
            f.set_name("Volcados SQL (.sql, .sql.gz, .zip…)")
            for pat in ("*.sql", "*.sql.gz", "*.sql.bz2", "*.sql.xz", "*.zip", "*.tar.gz", "*.gz"):
                f.add_pattern(pat)
            dlg.add_filter(f)
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.ACCEPT else None
        dlg.destroy()
        return path

    def on_import_db(self):
        p = self.selected
        path = self._choose_file("Importar base de datos", Gtk.FileChooserAction.OPEN, "Importar")
        if path and self.confirm("¿Importar este archivo?", f"Se reemplaza la base de datos actual de {p['name']} con:\n{path}", "Importar", destructive=True):
            script = ddev.script_simple(p["approot"], [("Importando base de datos", f"ddev import-db --file={ddev._q(path)}")], "Base de datos importada")
            self.run_script(f"{p['name']}: importar BD", script, p)

    def on_export_db(self):
        p = self.selected
        stamp = GLib.DateTime.new_now_local().format("%Y%m%d-%H%M")
        path = self._choose_file("Exportar base de datos", Gtk.FileChooserAction.SAVE, "Exportar", f"{p['name']}-{stamp}.sql.gz")
        if path:
            script = ddev.script_simple(p["approot"], [("Exportando base de datos", f"ddev export-db --file={ddev._q(path)}")], f"Guardada en {path}")
            self.run_script(f"{p['name']}: exportar BD", script, p)

    def on_delete(self):
        p = self.selected
        if self.confirm(
            f"¿Eliminar {p['name']} de DDEV?",
            "Se borran sus contenedores y su base de datos (sin copia). "
            f"Tus archivos en {p.get('shortroot')} NO se tocan.",
            "Eliminar",
            destructive=True,
        ):
            script = ddev.script_simple(None, [(f"Eliminando {p['name']}", f"ddev delete --omit-snapshot --yes {ddev._q(p['name'])}")], "Proyecto eliminado de DDEV")
            self.selected = None
            self.run_script(f"{p['name']}: eliminar", script, p)


class PanelApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.get_active_window() or MainWindow(self)
        win.present()


def main():
    import sys

    return PanelApp().run(sys.argv)
