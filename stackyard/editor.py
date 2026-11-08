"""Built-in code editor: a file explorer with the usual file operations and a
tabbed source editor (GtkSourceView) with search/replace and quick open."""

import os
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, GtkSource, Pango  # noqa: E402

from . import settings  # noqa: E402
from .i18n import _  # noqa: E402

MAX_FILE_SIZE = 5 * 1024 * 1024
HIDDEN_NAMES = {".git", ".DS_Store", "__pycache__", ".idea"}
QUICK_OPEN_SKIP = {".git", "node_modules", "vendor", ".ddev", "storage", "__pycache__", "dist", "build", ".next", ".nuxt"}
QUICK_OPEN_LIMIT = 20000

# file name or extension -> GtkSourceView language id (when guessing is not enough)
LANG_OVERRIDES = {
    ".env": "sh", ".blade.php": "php", ".vue": "html", ".svelte": "html", ".twig": "html",
    ".tsx": "jsx", ".ts": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".lock": "json", "Dockerfile": "dockerfile", ".conf": "ini", ".htaccess": "apache",
}
TWO_SPACE = {"javascript", "jsx", "json", "yaml", "html", "css", "scss", "markdown", "xml"}

COL_ICON, COL_NAME, COL_PATH, COL_IS_DIR = range(4)
DUMMY = "…"  # placeholder row of a folder not loaded yet (its path column is empty)


def language_for(path, manager):
    name = Path(path).name
    for key, lang_id in LANG_OVERRIDES.items():
        if name == key or name.endswith(key) or (key.startswith(".env") and name.startswith(".env")):
            lang = manager.get_language(lang_id)
            if lang:
                return lang
    content_type, _uncertain = Gio.content_type_guess(name, None)
    return manager.guess_language(name, content_type)


def is_binary(path):
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8000)
    except OSError:
        return False


def unique_name(folder, name):
    """'file.txt' -> 'file copy.txt', 'file copy 2.txt'… if it already exists."""
    target = Path(folder) / name
    if not target.exists():
        return target
    stem, suffix = (name, "") if target.is_dir() else (Path(name).stem, Path(name).suffix)
    i = 1
    while True:
        candidate = Path(folder) / (f"{stem} {_('copy')}{'' if i == 1 else f' {i}'}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


class EditorTab(Gtk.Box):
    """One open file."""

    __gsignals__ = {"file-state-changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, path, manager, scheme):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = Path(path)
        self.buffer = GtkSource.Buffer()
        self.buffer.set_language(language_for(path, manager))
        if scheme:
            self.buffer.set_style_scheme(scheme)
        self.view = GtkSource.View(buffer=self.buffer, monospace=True, show_line_numbers=True,
                                   highlight_current_line=True, auto_indent=True, smart_backspace=True,
                                   show_right_margin=True, right_margin_position=120,
                                   smart_home_end=GtkSource.SmartHomeEndType.BEFORE, tab_width=4,
                                   insert_spaces_instead_of_tabs=True, indent_on_tab=True)
        lang = self.buffer.get_language()
        if lang and lang.get_id() in TWO_SPACE:
            self.view.set_tab_width(2)
        self.buffer.set_highlight_matching_brackets(True)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.view)
        self.pack_start(scroll, True, True, 0)
        self.search_settings = GtkSource.SearchSettings(wrap_around=True)
        self.search = GtkSource.SearchContext(buffer=self.buffer, settings=self.search_settings)
        self.mtime = None
        self.load()
        self.buffer.connect("modified-changed", lambda *_a: self.emit("file-state-changed"))
        self.buffer.connect("mark-set", lambda *_a: self.emit("file-state-changed"))
        self.show_all()

    def load(self):
        text = self.path.read_text(errors="replace")
        self.buffer.begin_not_undoable_action()
        self.buffer.set_text(text)
        self.buffer.end_not_undoable_action()
        self.buffer.set_modified(False)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.mtime = self.path.stat().st_mtime

    def save(self):
        text = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)
        tmp = self.path.with_name(f".{self.path.name}.stackyard-tmp")
        tmp.write_text(text)
        if self.path.exists():
            shutil.copymode(self.path, tmp)
        os.replace(tmp, self.path)
        self.buffer.set_modified(False)
        self.mtime = self.path.stat().st_mtime

    def changed_on_disk(self):
        try:
            return self.path.stat().st_mtime != self.mtime
        except OSError:
            return False

    @property
    def modified(self):
        return self.buffer.get_modified()

    def cursor(self):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        return it.get_line() + 1, it.get_line_offset() + 1

    def set_scheme(self, scheme):
        if scheme:
            self.buffer.set_style_scheme(scheme)


class QuickOpen(Gtk.Dialog):
    """Ctrl+P: type part of a file name to open it."""

    def __init__(self, parent, root):
        super().__init__(title=_("Go to file"), transient_for=parent, modal=True)
        self.set_default_size(560, 420)
        self.root = Path(root)
        self.selected = None
        box = self.get_content_area()
        box.set_border_width(10)
        box.set_spacing(8)
        self.entry = Gtk.SearchEntry(placeholder_text=_("Type part of a file name…"))
        self.entry.connect("search-changed", lambda *_a: self._filter())
        self.entry.connect("activate", lambda *_a: self._accept_first())
        self.entry.connect("key-press-event", self._on_key)
        box.pack_start(self.entry, False, False, 0)
        self.store = Gtk.ListStore(str, str)
        self.view = Gtk.TreeView(model=self.store, headers_visible=False)
        cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.START)
        self.view.append_column(Gtk.TreeViewColumn("", cell, markup=0))
        self.view.connect("row-activated", lambda v, path, _c: self._accept(self.store[path][1]))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.add(self.view)
        box.pack_start(scroll, True, True, 0)
        self.files = self._list_files()
        self._filter()
        self.show_all()

    def _list_files(self):
        try:  # git knows which files matter (respects .gitignore)
            out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=self.root,
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.splitlines()[:QUICK_OPEN_LIMIT]
        except (OSError, subprocess.TimeoutExpired):
            pass
        files = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in QUICK_OPEN_SKIP]
            rel = os.path.relpath(dirpath, self.root)
            files += [f if rel == "." else f"{rel}/{f}" for f in filenames]
            if len(files) > QUICK_OPEN_LIMIT:
                break
        return files

    def _score(self, path, query):
        name = path.rsplit("/", 1)[-1].lower()
        p = path.lower()
        if query in name:
            return (0 if name.startswith(query) else 1, len(p))
        # subsequence match ("usrctl" -> "UserController")
        it = iter(p)
        if all(ch in it for ch in query):
            return (2, len(p))
        return None

    def _filter(self):
        query = self.entry.get_text().strip().lower()
        self.store.clear()
        scored = []
        for f in self.files:
            s = self._score(f, query) if query else (0, len(f))
            if s is not None:
                scored.append((s, f))
        for _s, f in sorted(scored)[:200]:
            folder, _sep, name = f.rpartition("/")
            markup = f"<b>{GLib.markup_escape_text(name)}</b>"
            if folder:
                markup += f'  <span foreground="#9a9996">{GLib.markup_escape_text(folder)}</span>'
            self.store.append([markup, f])
        if len(self.store):
            self.view.set_cursor(Gtk.TreePath(0), None, False)

    def _on_key(self, _w, event):
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            path, _col = self.view.get_cursor()
            i = path.get_indices()[0] if path else -1
            i = max(0, min(len(self.store) - 1, i + (1 if event.keyval == Gdk.KEY_Down else -1)))
            if len(self.store):
                self.view.set_cursor(Gtk.TreePath(i), None, False)
            return True
        return False

    def _accept_first(self):
        path, _col = self.view.get_cursor()
        if path is not None:
            self._accept(self.store[path][1])

    def _accept(self, rel):
        self.selected = self.root / rel
        self.response(Gtk.ResponseType.OK)


class EditorView(Gtk.Paned):
    """Explorer + editor for one project folder."""

    def __init__(self, root, window):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.root = Path(root)
        self.window = window
        self.clipboard = None  # ("copy"|"cut", [paths])
        self.manager = GtkSource.LanguageManager.get_default()
        self.schemes = GtkSource.StyleSchemeManager.get_default()
        self.show_hidden = True

        # ---------------- explorer
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=2, margin=4)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{GLib.markup_escape_text(self.root.name.upper())}</b>")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        bar.pack_start(title, True, True, 4)
        for icon, tip, cb in (
            ("document-new-symbolic", _("New file"), lambda: self.new_item(False)),
            ("folder-new-symbolic", _("New folder"), lambda: self.new_item(True)),
            ("view-refresh-symbolic", _("Refresh"), self.refresh_tree),
            ("view-restore-symbolic", _("Collapse all"), lambda: self.tree.collapse_all()),
        ):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, c=cb: c())
            bar.pack_start(b, False, False, 0)
        left.pack_start(bar, False, False, 0)

        self.store = Gtk.TreeStore(str, str, str, bool)
        self.tree = Gtk.TreeView(model=self.store, headers_visible=False, enable_search=True, search_column=COL_NAME)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        col = Gtk.TreeViewColumn()
        icon = Gtk.CellRendererPixbuf()
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(icon, False)
        col.pack_start(text, True)
        col.add_attribute(icon, "icon-name", COL_ICON)
        col.add_attribute(text, "text", COL_NAME)
        self.tree.append_column(col)
        self.tree.connect("row-expanded", self._on_expand)
        self.tree.connect("row-activated", self._on_activate)
        self.tree.connect("button-press-event", self._on_tree_click)
        self.tree.connect("key-press-event", self._on_tree_key)
        tscroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        tscroll.add(self.tree)
        left.pack_start(tscroll, True, True, 0)
        left.set_size_request(220, -1)

        # ---------------- editor
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.notebook = Gtk.Notebook(scrollable=True)
        self.notebook.connect("switch-page", lambda *_a: GLib.idle_add(self._after_switch))
        self.welcome = Gtk.Label(
            label=_("Open a file from the explorer, or press Ctrl+P to find one by name.\n\n"
                    "Ctrl+S save · Ctrl+F find · Ctrl+H replace · Ctrl+W close tab"),
            justify=Gtk.Justification.CENTER,
        )
        self.welcome.get_style_context().add_class("dim-label")
        self.notebook.append_page(self.welcome, Gtk.Label(label=_("Welcome")))

        self.search_bar = self._build_search_bar()
        right.pack_start(self.search_bar, False, False, 0)
        right.pack_start(self.notebook, True, True, 0)
        self.status = Gtk.Label(xalign=1, margin_end=8, margin_top=2, margin_bottom=2)
        self.status.get_style_context().add_class("dim-label")
        right.pack_start(self.status, False, False, 0)

        self.pack1(left, False, False)
        self.pack2(right, True, False)
        self.set_position(240)
        self.connect("key-press-event", self._on_key)
        self.refresh_tree()
        self.show_all()
        self.search_bar.set_search_mode(False)

    # ================================================================ tree
    def _icon(self, path, is_dir):
        if is_dir:
            return "folder-symbolic"
        content_type, _u = Gio.content_type_guess(path.name, None)
        icon = Gio.content_type_get_symbolic_icon(content_type)
        names = icon.get_names() if isinstance(icon, Gio.ThemedIcon) else []
        theme = Gtk.IconTheme.get_default()
        return next((n for n in names if theme.has_icon(n)), "text-x-generic-symbolic")

    def _children(self, folder):
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return []
        items = [e for e in entries if e.name not in HIDDEN_NAMES and (self.show_hidden or not e.name.startswith("."))]
        items.sort(key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        return items

    def _fill(self, parent_iter, folder):
        for e in self._children(folder):
            is_dir = e.is_dir(follow_symlinks=False)
            p = Path(e.path)
            it = self.store.append(parent_iter, [self._icon(p, is_dir), e.name, e.path, is_dir])
            if is_dir:
                self.store.append(it, ["", DUMMY, "", False])

    def refresh_tree(self):
        expanded = set()
        self.tree.map_expanded_rows(lambda _t, path, _d: expanded.add(self.store[path][COL_PATH]), None)
        self.store.clear()
        self._fill(None, self.root)
        self._reexpand(None, expanded)

    def _reexpand(self, parent, expanded):
        it = self.store.iter_children(parent)
        while it:
            if self.store[it][COL_IS_DIR] and self.store[it][COL_PATH] in expanded:
                self.tree.expand_row(self.store.get_path(it), False)
                self._reexpand(it, expanded)
            it = self.store.iter_next(it)

    def _on_expand(self, _tree, it, _path):
        first = self.store.iter_children(it)
        if first and not self.store[first][COL_PATH]:
            self.store.remove(first)
            self._fill(it, self.store[it][COL_PATH])

    def _on_activate(self, tree, path, _col):
        row = self.store[path]
        if row[COL_IS_DIR]:
            if tree.row_expanded(path):
                tree.collapse_row(path)
            else:
                tree.expand_row(path, False)
        elif row[COL_PATH]:
            self.open_file(row[COL_PATH])

    def _selected_paths(self):
        model, rows = self.tree.get_selection().get_selected_rows()
        return [Path(model[r][COL_PATH]) for r in rows if model[r][COL_PATH]]

    def _target_folder(self):
        sel = self._selected_paths()
        if not sel:
            return self.root
        return sel[0] if sel[0].is_dir() else sel[0].parent

    def _on_tree_click(self, tree, event):
        if event.button != 3:
            return False
        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        selection = tree.get_selection()
        if hit:
            if not selection.path_is_selected(hit[0]):
                selection.unselect_all()
                selection.select_path(hit[0])
        else:
            selection.unselect_all()
        self._context_menu(event)
        return True

    def _context_menu(self, event):
        sel = self._selected_paths()
        one = len(sel) == 1
        menu = Gtk.Menu()
        entries = [
            (_("New file…"), lambda: self.new_item(False), True),
            (_("New folder…"), lambda: self.new_item(True), True),
            None,
            (_("Copy"), lambda: self.copy(False), bool(sel)),
            (_("Cut"), lambda: self.copy(True), bool(sel)),
            (_("Paste"), self.paste, bool(self.clipboard)),
            (_("Duplicate"), self.duplicate, bool(sel)),
            None,
            (_("Rename…"), self.rename, one),
            (_("Move to trash"), self.trash, bool(sel)),
            None,
            (_("Copy path"), self.copy_path, one),
            (_("Open in file manager"), self.open_in_file_manager, True),
        ]
        for e in entries:
            if e is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            label, cb, sensitive = e
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(sensitive)
            item.connect("activate", lambda _i, c=cb: c())
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_tree_key(self, _tree, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        key = Gdk.keyval_to_lower(event.keyval)
        if event.keyval == Gdk.KEY_F2:
            self.rename()
        elif event.keyval == Gdk.KEY_Delete:
            self.trash()
        elif ctrl and key == Gdk.KEY_c:
            self.copy(False)
        elif ctrl and key == Gdk.KEY_x:
            self.copy(True)
        elif ctrl and key == Gdk.KEY_v:
            self.paste()
        elif ctrl and key == Gdk.KEY_d:
            self.duplicate()
        else:
            return False
        return True

    # ================================================================ file operations
    def _ask_name(self, title, initial="", select_stem=False):
        dlg = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        ok = dlg.add_button(_("OK"), Gtk.ResponseType.OK)
        ok.get_style_context().add_class("suggested-action")
        dlg.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(text=initial, activates_default=True, margin=14, width_chars=40)
        dlg.get_content_area().add(entry)
        dlg.show_all()
        if select_stem and "." in initial[1:]:
            entry.select_region(0, initial.rfind("."))
        name = entry.get_text().strip() if dlg.run() == Gtk.ResponseType.OK else ""
        dlg.destroy()
        if name and ("/" in name or name in (".", "..")):
            self._error(_("Invalid name"), name)
            return ""
        return name

    def _error(self, title, text):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.OK, text=title)
        dlg.format_secondary_text(str(text))
        dlg.run()
        dlg.destroy()

    def _confirm(self, title, text, ok):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION, text=title)
        dlg.format_secondary_text(text)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(ok, Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        answer = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        return answer

    def new_item(self, folder):
        parent = self._target_folder()
        name = self._ask_name(_("New folder") if folder else _("New file"))
        if not name:
            return
        target = parent / name
        if target.exists():
            self._error(_("It already exists"), str(target))
            return
        try:
            if folder:
                target.mkdir(parents=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
        except OSError as exc:
            self._error(_("Could not create it"), exc)
            return
        self.refresh_tree()
        if not folder:
            self.open_file(target)

    def rename(self):
        sel = self._selected_paths()
        if len(sel) != 1:
            return
        src = sel[0]
        name = self._ask_name(_("Rename"), src.name, select_stem=True)
        if not name or name == src.name:
            return
        dst = src.with_name(name)
        if dst.exists():
            self._error(_("It already exists"), str(dst))
            return
        try:
            src.rename(dst)
        except OSError as exc:
            self._error(_("Could not rename it"), exc)
            return
        self._retarget_tabs(src, dst)
        self.refresh_tree()

    def trash(self):
        sel = self._selected_paths()
        if not sel:
            return
        names = "\n".join(p.name for p in sel[:8]) + ("\n…" if len(sel) > 8 else "")
        if not self._confirm(_("Move to trash?"), names + "\n\n" + _("You can restore them from the trash."), _("Move to trash")):
            return
        for p in sel:
            try:
                Gio.File.new_for_path(str(p)).trash(None)
            except GLib.Error as exc:
                self._error(_("Could not move it to the trash"), f"{p}\n{exc.message}")
                continue
            self._close_tabs_under(p)
        self.refresh_tree()

    def copy(self, cut):
        sel = self._selected_paths()
        if sel:
            self.clipboard = ("cut" if cut else "copy", sel)

    def paste(self):
        if not self.clipboard:
            return
        mode, sources = self.clipboard
        folder = self._target_folder()
        for src in sources:
            if not src.exists():
                continue
            if src.is_dir() and (folder == src or src in folder.parents):
                self._error(_("Cannot paste a folder inside itself"), str(src))
                continue
            dst = unique_name(folder, src.name)
            try:
                if mode == "cut":
                    shutil.move(str(src), str(dst))
                    self._retarget_tabs(src, dst)
                elif src.is_dir():
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)
            except OSError as exc:
                self._error(_("Could not paste"), f"{src}\n{exc}")
        if mode == "cut":
            self.clipboard = None
        self.refresh_tree()

    def duplicate(self):
        for src in self._selected_paths():
            dst = unique_name(src.parent, src.name)  # next to the original
            try:
                shutil.copytree(src, dst, symlinks=True) if src.is_dir() else shutil.copy2(src, dst)
            except OSError as exc:
                self._error(_("Could not duplicate"), exc)
        self.refresh_tree()

    def copy_path(self):
        sel = self._selected_paths()
        if sel:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(str(sel[0]), -1)

    def open_in_file_manager(self):
        folder = self._target_folder()
        Gtk.show_uri_on_window(self.window, folder.as_uri(), Gdk.CURRENT_TIME)

    # ================================================================ tabs
    def tabs(self):
        return [self.notebook.get_nth_page(i) for i in range(self.notebook.get_n_pages())
                if isinstance(self.notebook.get_nth_page(i), EditorTab)]

    def current(self):
        page = self.notebook.get_nth_page(self.notebook.get_current_page())
        return page if isinstance(page, EditorTab) else None

    def _scheme(self):
        dark = settings.is_dark_now()
        for sid in (("oblivion", "solarized-dark", "cobalt") if dark else ("tango", "classic", "solarized-light")):
            scheme = self.schemes.get_scheme(sid)
            if scheme:
                return scheme
        return None

    def update_scheme(self):
        scheme = self._scheme()
        for tab in self.tabs():
            tab.set_scheme(scheme)

    def open_file(self, path):
        path = Path(path)
        for i in range(self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(i)
            if isinstance(page, EditorTab) and page.path == path:
                self.notebook.set_current_page(i)
                page.view.grab_focus()
                return page
        try:
            too_big = path.stat().st_size > MAX_FILE_SIZE
        except OSError as exc:
            self._error(_("Could not open the file"), exc)
            return None
        if too_big or is_binary(path):
            if self._confirm(_("This file cannot be edited here"),
                             _("It is binary or larger than 5 MB. Open it with the default application?"), _("Open")):
                Gtk.show_uri_on_window(self.window, path.as_uri(), Gdk.CURRENT_TIME)
            return None
        try:
            tab = EditorTab(path, self.manager, self._scheme())
        except OSError as exc:
            self._error(_("Could not open the file"), exc)
            return None
        if self.welcome.get_parent():
            self.notebook.remove_page(self.notebook.page_num(self.welcome))
        label = self._tab_label(tab)
        idx = self.notebook.append_page(tab, label)
        self.notebook.set_tab_reorderable(tab, True)
        tab.connect("file-state-changed", self._on_tab_state)
        self.notebook.set_current_page(idx)
        tab.view.grab_focus()
        self._on_tab_state(tab)
        return tab

    def _tab_label(self, tab):
        box = Gtk.Box(spacing=6)
        tab.title = Gtk.Label(label=tab.path.name)
        tab.title.set_tooltip_text(str(tab.path))
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.connect("clicked", lambda *_a: self.close_tab(tab))
        box.pack_start(tab.title, False, False, 0)
        box.pack_start(close, False, False, 0)
        box.show_all()
        return box

    def _on_tab_state(self, tab):
        tab.title.set_text(("● " if tab.modified else "") + tab.path.name)
        if tab is self.current():
            self._update_status()

    def _update_status(self):
        tab = self.current()
        if not tab:
            self.status.set_text("")
            return
        line, col = tab.cursor()
        lang = tab.buffer.get_language()
        rel = os.path.relpath(tab.path, self.root)
        self.status.set_text(f"{rel}   ·   {_('Ln {line}, Col {col}').format(line=line, col=col)}   ·   "
                             f"{lang.get_name() if lang else _('Plain text')}   ·   UTF-8")

    def _after_switch(self):
        tab = self.current()
        self._update_status()
        if tab and tab.changed_on_disk():
            if not tab.modified:
                tab.load()
            elif self._confirm(_("{name} changed on disk").format(name=tab.path.name),
                               _("Reload it and lose your unsaved changes?"), _("Reload")):
                tab.load()
        return False

    def save_current(self):
        tab = self.current()
        if not tab:
            return
        try:
            tab.save()
        except OSError as exc:
            self._error(_("Could not save the file"), exc)

    def close_tab(self, tab):
        if tab.modified:
            choice = self._ask_save(tab)
            if choice == "cancel":
                return False
            if choice == "save":
                try:
                    tab.save()
                except OSError as exc:
                    self._error(_("Could not save the file"), exc)
                    return False
        self.notebook.remove_page(self.notebook.page_num(tab))
        if not self.tabs():
            self.notebook.append_page(self.welcome, Gtk.Label(label=_("Welcome")))
            self.welcome.show()
        self._update_status()
        return True

    def _ask_save(self, tab):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.WARNING,
                                text=_("Save changes to {name}?").format(name=tab.path.name))
        dlg.format_secondary_text(_("Your changes will be lost if you don't save them."))
        dlg.add_button(_("Don't save"), 1)
        dlg.add_button(_("Cancel"), 2)
        dlg.add_button(_("Save"), 3).get_style_context().add_class("suggested-action")
        r = dlg.run()
        dlg.destroy()
        return {1: "discard", 3: "save"}.get(r, "cancel")

    def close_all(self):
        """Closes every tab, asking about unsaved ones. False if the user cancelled."""
        return all(self.close_tab(tab) for tab in list(self.tabs()))

    def has_unsaved(self):
        return any(t.modified for t in self.tabs())

    def _retarget_tabs(self, src, dst):
        for tab in self.tabs():
            if tab.path == src or src in tab.path.parents:
                tab.path = dst / tab.path.relative_to(src) if tab.path != src else dst
                self._on_tab_state(tab)

    def _close_tabs_under(self, path):
        for tab in list(self.tabs()):
            if tab.path == path or path in tab.path.parents:
                tab.buffer.set_modified(False)
                self.close_tab(tab)

    # ================================================================ search
    def _build_search_bar(self):
        bar = Gtk.SearchBar(show_close_button=True)
        grid = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.find_entry = Gtk.SearchEntry(placeholder_text=_("Find"), width_chars=28)
        self.find_entry.connect("search-changed", lambda *_a: self._search_changed())
        self.find_entry.connect("activate", lambda *_a: self.find(True))
        self.replace_entry = Gtk.Entry(placeholder_text=_("Replace with"), width_chars=28)
        self.replace_entry.connect("activate", lambda *_a: self.replace_one())
        self.match_label = Gtk.Label()
        self.match_label.get_style_context().add_class("dim-label")
        self.case_check = Gtk.CheckButton(label="Aa", tooltip_text=_("Match case"))
        self.case_check.connect("toggled", lambda *_a: self._search_changed())
        self.regex_check = Gtk.CheckButton(label=".*", tooltip_text=_("Regular expression"))
        self.regex_check.connect("toggled", lambda *_a: self._search_changed())
        prev_b = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.BUTTON)
        prev_b.connect("clicked", lambda *_a: self.find(False))
        next_b = Gtk.Button.new_from_icon_name("go-down-symbolic", Gtk.IconSize.BUTTON)
        next_b.connect("clicked", lambda *_a: self.find(True))
        rep = Gtk.Button(label=_("Replace"))
        rep.connect("clicked", lambda *_a: self.replace_one())
        rep_all = Gtk.Button(label=_("Replace all"))
        rep_all.connect("clicked", lambda *_a: self.replace_all())
        grid.attach(self.find_entry, 0, 0, 1, 1)
        grid.attach(prev_b, 1, 0, 1, 1)
        grid.attach(next_b, 2, 0, 1, 1)
        grid.attach(self.case_check, 3, 0, 1, 1)
        grid.attach(self.regex_check, 4, 0, 1, 1)
        grid.attach(self.match_label, 5, 0, 1, 1)
        self.replace_row = [self.replace_entry, rep, rep_all]
        grid.attach(self.replace_entry, 0, 1, 1, 1)
        grid.attach(rep, 1, 1, 2, 1)
        grid.attach(rep_all, 3, 1, 3, 1)
        bar.add(grid)
        bar.connect_entry(self.find_entry)
        return bar

    def show_search(self, replace=False):
        tab = self.current()
        if not tab:
            return
        if tab.buffer.get_has_selection():
            start, end = tab.buffer.get_selection_bounds()
            text = tab.buffer.get_text(start, end, False)
            if "\n" not in text:
                self.find_entry.set_text(text)
        self.search_bar.set_search_mode(True)
        for w in self.replace_row:
            w.set_visible(replace)
        self.find_entry.grab_focus()
        self._search_changed()

    def _search_changed(self):
        tab = self.current()
        if not tab:
            return
        s = tab.search_settings
        s.set_case_sensitive(self.case_check.get_active())
        s.set_regex_enabled(self.regex_check.get_active())
        s.set_search_text(self.find_entry.get_text() or None)
        GLib.timeout_add(150, self._update_count)
        self.find(True, from_start_of_selection=True)

    def _update_count(self):
        tab = self.current()
        if tab:
            n = tab.search.get_occurrences_count()
            self.match_label.set_text("" if not self.find_entry.get_text() else
                                      (_("{n} matches").format(n=n) if n >= 0 else "…"))
        return False

    def find(self, forward=True, from_start_of_selection=False):
        tab = self.current()
        if not tab or not self.find_entry.get_text():
            return
        buf = tab.buffer
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
        else:
            start = end = buf.get_iter_at_mark(buf.get_insert())
        anchor = start if (from_start_of_selection or not forward) else end
        found, m_start, m_end, _wrapped = (tab.search.forward(anchor) if forward else tab.search.backward(anchor))
        if found:
            buf.select_range(m_start, m_end)
            tab.view.scroll_to_iter(m_start, 0.2, False, 0, 0)

    def replace_one(self):
        tab = self.current()
        if not tab or not tab.buffer.get_has_selection():
            self.find(True)
            return
        start, end = tab.buffer.get_selection_bounds()
        try:
            tab.search.replace(start, end, self.replace_entry.get_text(), -1)
        except GLib.Error:
            pass
        self.find(True)

    def replace_all(self):
        tab = self.current()
        if tab and self.find_entry.get_text():
            try:
                n = tab.search.replace_all(self.replace_entry.get_text(), -1)
            except GLib.Error as exc:
                self._error(_("Invalid search"), exc.message)
                return
            self.match_label.set_text(_("{n} replaced").format(n=n))

    # ================================================================ keys
    def _on_key(self, _w, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        key = Gdk.keyval_to_lower(event.keyval)
        if not ctrl:
            if event.keyval == Gdk.KEY_Escape and self.search_bar.get_search_mode():
                self.search_bar.set_search_mode(False)
                tab = self.current()
                if tab:
                    tab.view.grab_focus()
                return True
            return False
        if key == Gdk.KEY_s:
            self.save_current()
        elif key == Gdk.KEY_w:
            tab = self.current()
            if tab:
                self.close_tab(tab)
        elif key == Gdk.KEY_f:
            self.show_search(False)
        elif key == Gdk.KEY_h:
            self.show_search(True)
        elif key == Gdk.KEY_p:
            self.quick_open()
        else:
            return False
        return True

    def quick_open(self):
        dlg = QuickOpen(self.window, self.root)
        selected = dlg.selected if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if selected:
            self.open_file(selected)
