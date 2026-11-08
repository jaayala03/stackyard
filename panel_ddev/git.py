"""Git tab: changes, diffs, history, branches, commit, pull and push."""

import shlex
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .i18n import _  # noqa: E402

MAX_DIFF = 400_000  # characters: avoids freezing the window with huge diffs

# status code -> (letter shown, description, colour)
STATUS_INFO = {
    "M": ("M", "Modified", "#e5a50a"),
    "A": ("A", "Added", "#2ec27e"),
    "D": ("D", "Deleted", "#e01b24"),
    "R": ("R", "Renamed", "#62a0ea"),
    "C": ("C", "Copied", "#62a0ea"),
    "T": ("T", "Type changed", "#e5a50a"),
    "?": ("U", "Untracked (new)", "#2ec27e"),
    "!": ("!", "Conflict", "#e01b24"),
}


# ===================================================================== backend
class GitError(Exception):
    pass


def git_installed():
    return shutil.which("git") is not None


def run(cwd, *args, stdin=None, ok_codes=(0,)):
    proc = subprocess.run(
        ["git", "-c", "color.ui=never", "-c", "core.quotepath=off", *args],
        cwd=cwd, input=stdin, capture_output=True, text=True, errors="replace",
    )
    if proc.returncode not in ok_codes:
        raise GitError((proc.stderr or proc.stdout).strip() or f"git {args[0]} failed")
    return proc.stdout


def toplevel(path):
    try:
        return run(path, "rev-parse", "--show-toplevel").strip()
    except (GitError, FileNotFoundError, NotADirectoryError):
        return None


def has_head(repo):
    try:
        run(repo, "rev-parse", "--verify", "-q", "HEAD")
        return True
    except GitError:
        return False


def status(repo):
    out = run(repo, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all")
    info = {"branch": None, "upstream": None, "ahead": 0, "behind": 0, "files": []}
    recs = out.split("\0")
    i = 0
    while i < len(recs):
        rec = recs[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("# branch.head "):
            head = rec[len("# branch.head "):]
            info["branch"] = None if head == "(detached)" else head
        elif rec.startswith("# branch.upstream "):
            info["upstream"] = rec[len("# branch.upstream "):]
        elif rec.startswith("# branch.ab "):
            a, b = rec[len("# branch.ab "):].split()
            info["ahead"], info["behind"] = int(a[1:]), int(b[1:])
        elif rec[0] == "1":
            parts = rec.split(" ", 8)
            info["files"].append(_entry(parts[1], parts[8]))
        elif rec[0] == "2":
            parts = rec.split(" ", 9)
            orig = recs[i]
            i += 1
            info["files"].append(_entry(parts[1], parts[9], orig))
        elif rec[0] == "u":
            parts = rec.split(" ", 10)
            e = _entry("!!", parts[10])
            e["conflict"] = True
            info["files"].append(e)
        elif rec[0] == "?":
            info["files"].append(_entry("??", rec[2:]))
    return info


def _entry(xy, path, orig=None):
    x, y = xy[0], xy[1]
    untracked = xy == "??"
    staged = not untracked and x not in ".!"
    unstaged = untracked or y not in "."
    code = "?" if untracked else ("!" if xy == "!!" else (y if y != "." else x))
    return {"path": path, "orig": orig, "code": code, "staged": staged, "unstaged": unstaged, "conflict": False}


def branches(repo):
    out = run(repo, "branch", "--format=%(refname:short)")
    return [b for b in out.splitlines() if b]


def remotes(repo):
    return [r for r in run(repo, "remote").splitlines() if r]


def log(repo, limit=300):
    if not has_head(repo):
        return []
    fmt = "%H%x1f%h%x1f%s%x1f%an%x1f%ar%x1f%D%x1e"
    out = run(repo, "log", f"-n{limit}", "--date=relative", f"--pretty=format:{fmt}")
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        full, short, subject, author, when, refs = (rec.split("\x1f") + [""] * 6)[:6]
        commits.append({"hash": full, "short": short, "subject": subject, "author": author, "when": when, "refs": refs})
    return commits


def file_diff(repo, f):
    if f["code"] == "?":
        return run(repo, "diff", "--no-index", "--", "/dev/null", f["path"], ok_codes=(0, 1))
    parts = []
    if f["staged"]:
        parts.append(run(repo, "diff", "--cached", "-M", "--", f["path"], *([f["orig"]] if f["orig"] else [])))
    if f["unstaged"]:
        parts.append(run(repo, "diff", "--", f["path"]))
    return "\n".join(p for p in parts if p)


def show_commit(repo, sha):
    return run(repo, "show", "--stat", "--patch", "-M", "--format=fuller", sha)


def stage(repo, f):
    run(repo, "add", "-A", "--", f["path"])


def unstage(repo, f):
    paths = [f["path"]] + ([f["orig"]] if f["orig"] else [])
    if has_head(repo):
        run(repo, "restore", "--staged", "--", *paths)
    else:
        run(repo, "rm", "--cached", "-q", "--", *paths)


def stage_all(repo):
    run(repo, "add", "-A")


def unstage_all(repo):
    if has_head(repo):
        run(repo, "reset", "-q")
    else:
        run(repo, "rm", "--cached", "-r", "-q", ".")


def commit(repo, message):
    return run(repo, "commit", "-F", "-", stdin=message)


# ===================================================================== UI
def _diff_view():
    tv = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
    tv.set_left_margin(8)
    tv.set_top_margin(6)
    buf = tv.get_buffer()
    buf.create_tag("add", foreground="#26a269")
    buf.create_tag("del", foreground="#e01b24")
    buf.create_tag("hunk", foreground="#3584e4")
    buf.create_tag("meta", weight=Pango.Weight.BOLD)
    buf.create_tag("dim", foreground="#9a9996")
    scroll = Gtk.ScrolledWindow()
    scroll.add(tv)
    return scroll, tv


def _set_diff(tv, text, empty=None):
    buf = tv.get_buffer()
    buf.set_text("")
    if not text.strip():
        buf.insert_with_tags_by_name(buf.get_end_iter(), empty or _("No differences."), "dim")
        return
    if len(text) > MAX_DIFF:
        text = text[:MAX_DIFF] + "\n\n… " + _("(diff truncated: it is too large)") + "\n"
    for line in text.splitlines(True):
        if line.startswith(("+++", "---", "diff --git", "index ", "new file", "deleted file", "similarity", "rename ", "commit ")):
            tag = "meta"
        elif line.startswith("+"):
            tag = "add"
        elif line.startswith("-"):
            tag = "del"
        elif line.startswith("@@"):
            tag = "hunk"
        elif line.startswith(("Author:", "AuthorDate:", "Commit:", "CommitDate:", "Merge:")):
            tag = "dim"
        else:
            tag = None
        if tag:
            buf.insert_with_tags_by_name(buf.get_end_iter(), line, tag)
        else:
            buf.insert(buf.get_end_iter(), line)
    buf.place_cursor(buf.get_start_iter())
    tv.scroll_to_iter(buf.get_start_iter(), 0, False, 0, 0)


def _button(icon, label=None, tip=None):
    if label:
        b = Gtk.Button()
        box = Gtk.Box(spacing=6)
        box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
        box.pack_start(Gtk.Label(label=label), False, False, 0)
        b.add(box)
    else:
        b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    if tip:
        b.set_tooltip_text(tip)
    return b


class GitView(Gtk.Box):
    """Git view of a project. `run_script(title, script, on_done)` runs long
    commands (pull, push…) in the embedded terminal."""

    def __init__(self, approot, run_script, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.approot = approot
        self.run_script = run_script
        self.window = window
        self.repo = None
        self.files = []
        self.state = {}
        self.remotes = []
        self._selected_path = None
        self._building = False
        self._last_log_head = None
        self.build()
        self.refresh()

    # ------------------------------------------------------------ construction
    def build(self):
        for c in self.get_children():
            self.remove(c)
        self.repo = toplevel(self.approot) if git_installed() else None
        if not self.repo:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, vexpand=True)
            lbl = Gtk.Label(label=_("This project does not use git yet.") if git_installed() else _("git is not installed."))
            lbl.get_style_context().add_class("dim-label")
            box.pack_start(lbl, False, False, 0)
            if git_installed():
                init = _button("list-add-symbolic", _("Initialize git repository"))
                init.connect("clicked", self.on_init)
                box.pack_start(init, False, False, 0)
            self.pack_start(box, True, True, 0)
            self.show_all()
            return

        # ---- toolbar: branch + sync
        bar = Gtk.Box(spacing=6)
        bar.pack_start(Gtk.Image.new_from_icon_name("media-playlist-shuffle-symbolic", Gtk.IconSize.BUTTON), False, False, 0)
        self.branch_combo = Gtk.ComboBoxText()
        self.branch_combo.set_tooltip_text(_("Switch branch"))
        self.branch_combo.connect("changed", self.on_branch_changed)
        bar.pack_start(self.branch_combo, False, False, 0)
        new_branch = _button("list-add-symbolic", tip=_("New branch…"))
        new_branch.connect("clicked", self.on_new_branch)
        bar.pack_start(new_branch, False, False, 0)
        self.sync_label = Gtk.Label()
        self.sync_label.get_style_context().add_class("dim-label")
        bar.pack_start(self.sync_label, False, False, 8)
        refresh = _button("view-refresh-symbolic", tip=_("Refresh"))
        refresh.connect("clicked", lambda *_a: self.refresh())
        self.push_btn = _button("go-up-symbolic", "Push", _("Upload your commits (git push)"))
        self.push_btn.connect("clicked", self.on_push)
        self.pull_btn = _button("go-down-symbolic", "Pull", _("Bring changes from the remote (git pull)"))
        self.pull_btn.connect("clicked", self.on_pull)
        self.fetch_btn = _button("emblem-synchronizing-symbolic", "Fetch", _("Check for new changes (git fetch)"))
        self.fetch_btn.connect("clicked", self.on_fetch)
        for w in (refresh, self.push_btn, self.pull_btn, self.fetch_btn):
            bar.pack_end(w, False, False, 0)
        self.pack_start(bar, False, False, 0)

        # ---- left: changes + commit
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lhead = Gtk.Box(spacing=6)
        self.changes_title = Gtk.Label(xalign=0)
        lhead.pack_start(self.changes_title, True, True, 0)
        add_all = _button("list-add-symbolic", tip=_("Stage all changes (git add -A)"))
        add_all.connect("clicked", lambda *_a: self._safe(stage_all, self.repo))
        rem_all = _button("list-remove-symbolic", tip=_("Unstage all"))
        rem_all.connect("clicked", lambda *_a: self._safe(unstage_all, self.repo))
        lhead.pack_end(rem_all, False, False, 0)
        lhead.pack_end(add_all, False, False, 0)
        left.pack_start(lhead, False, False, 0)

        self.changes = Gtk.ListBox()
        self.changes.set_placeholder(self._dim(_("No changes.")))
        self.changes.connect("row-selected", self.on_file_selected)
        cs = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        cs.add(self.changes)
        left.pack_start(cs, True, True, 0)

        self.message = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.message.set_left_margin(6)
        self.message.set_top_margin(4)
        self.message.set_tooltip_text(_("Commit message (Ctrl+Enter to commit)"))
        self.message.connect("key-press-event", self.on_message_key)
        ms = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        ms.set_size_request(-1, 64)
        ms.add(self.message)
        frame = Gtk.Frame()
        frame.add(ms)
        hint = self._dim(_("Commit message"))
        hint.set_xalign(0)
        left.pack_start(hint, False, False, 0)
        left.pack_start(frame, False, False, 0)
        self.commit_btn = _button("object-select-symbolic", "Commit")
        self.commit_btn.get_style_context().add_class("suggested-action")
        self.commit_btn.connect("clicked", self.on_commit)
        left.pack_start(self.commit_btn, False, False, 0)

        # ---- right: diff + history
        self.tabs = Gtk.Notebook()
        dscroll, self.diff_tv = _diff_view()
        self.tabs.append_page(dscroll, Gtk.Label(label=_("Changes")))
        hist = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.commits = Gtk.ListBox()
        self.commits.set_placeholder(self._dim(_("No commits yet.")))
        self.commits.connect("row-selected", self.on_commit_selected)
        hs = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        hs.set_size_request(-1, 110)
        hs.add(self.commits)
        cscroll, self.commit_tv = _diff_view()
        hist.pack1(hs, True, False)
        hist.pack2(cscroll, True, False)
        hist.set_position(140)
        self.tabs.append_page(hist, Gtk.Label(label=_("History")))
        _set_diff(self.diff_tv, "", _("Select a file from the list to see its changes."))
        _set_diff(self.commit_tv, "", _("Select a commit to see what changed."))

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        left.set_size_request(260, -1)
        paned.pack1(left, False, False)
        paned.pack2(self.tabs, True, False)
        paned.set_position(300)
        self.pack_start(paned, True, True, 0)
        self.show_all()

    def _dim(self, text):
        lbl = Gtk.Label(label=text, margin=6)
        lbl.get_style_context().add_class("dim-label")
        lbl.show()
        return lbl

    # ------------------------------------------------------------ data
    def refresh(self):
        if not self.repo:
            if git_installed() and toplevel(self.approot):
                self.build()
                self.refresh()
            return
        try:
            st = status(self.repo)
            brs = branches(self.repo)
            self.remotes = remotes(self.repo)
        except GitError as exc:
            self.changes_title.set_text(_("Error: {error}").format(error=exc)[:80])
            return
        self.state = st

        # branches
        self._building = True
        self.branch_combo.remove_all()
        current = st["branch"]
        for b in brs or ([current] if current else []):
            self.branch_combo.append(b, b)
        if current:
            if not self.branch_combo.set_active_id(current):
                self.branch_combo.append(current, current)
                self.branch_combo.set_active_id(current)
        else:
            self.branch_combo.append("__detached__", _("(no branch)"))
            self.branch_combo.set_active_id("__detached__")
        self._building = False

        # sync status
        if not self.remotes:
            self.sync_label.set_text(_("no remote"))
        elif not st["upstream"]:
            self.sync_label.set_text(_("branch not published"))
        else:
            self.sync_label.set_text(f"↑{st['ahead']}  ↓{st['behind']}  · {st['upstream']}")
        for b in (self.push_btn, self.pull_btn, self.fetch_btn):
            b.set_sensitive(bool(self.remotes))
        self.pull_btn.set_sensitive(bool(self.remotes and st["upstream"]))

        # changes
        self.files = st["files"]
        staged = sum(1 for f in self.files if f["staged"])
        self.changes_title.set_markup(
            _("<b>Changes</b> ({total}) · {staged} staged").format(total=len(self.files), staged=staged)
        )
        for row in self.changes.get_children():
            self.changes.remove(row)
        select = None
        for f in self.files:
            row = self._file_row(f)
            self.changes.add(row)
            if f["path"] == self._selected_path:
                select = row
        self.changes.show_all()
        if select:
            self.changes.select_row(select)
        elif self._selected_path:
            self._selected_path = None
            _set_diff(self.diff_tv, "", _("Select a file from the list to see its changes."))
        self.commit_btn.set_sensitive(bool(self.files))

        # history (only reloaded when HEAD moved)
        head = None
        try:
            head = run(self.repo, "rev-parse", "-q", "--verify", "HEAD", ok_codes=(0, 1)).strip()
        except GitError:
            pass
        if head != self._last_log_head:
            self._last_log_head = head
            self._load_log()

    def _file_row(self, f):
        row = Gtk.ListBoxRow()
        row.file = f
        box = Gtk.Box(spacing=6, margin_start=4, margin_end=6, margin_top=2, margin_bottom=2)
        check = Gtk.CheckButton()
        check.set_active(f["staged"])
        check.set_inconsistent(f["staged"] and f["unstaged"] and f["code"] != "?")
        check.set_tooltip_text(_("Staged for the commit") if f["staged"] else _("Check to include it in the commit"))
        check.connect("toggled", self.on_toggle, f)
        box.pack_start(check, False, False, 0)
        letter, desc, color = STATUS_INFO.get(f["code"], (f["code"], f["code"], "#9a9996"))
        code = Gtk.Label()
        code.set_markup(f'<span foreground="{color}" weight="bold">{letter}</span>')
        code.set_tooltip_text(_(desc))
        code.set_width_chars(2)
        box.pack_start(code, False, False, 0)
        p = Path(f["path"])
        name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.START)
        parent = "" if str(p.parent) == "." else f'  <span size="small" foreground="#9a9996">{GLib.markup_escape_text(str(p.parent))}</span>'
        strike = ' strikethrough="true"' if f["code"] == "D" else ""
        name.set_markup(f"<span{strike}>{GLib.markup_escape_text(p.name)}</span>{parent}")
        name.set_tooltip_text(f["path"] + (_("  (was: {path})").format(path=f["orig"]) if f["orig"] else ""))
        box.pack_start(name, True, True, 0)
        row.add(box)
        return row

    def _load_log(self):
        for row in self.commits.get_children():
            self.commits.remove(row)
        try:
            commits = log(self.repo)
        except GitError:
            commits = []
        for c in commits:
            row = Gtk.ListBoxRow()
            row.commit = c
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=4)
            top = Gtk.Box(spacing=8)
            subj = Gtk.Label(label=c["subject"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            top.pack_start(subj, True, True, 0)
            if c["refs"]:
                refs = Gtk.Label()
                refs.set_markup(f'<span size="small" foreground="#3584e4">{GLib.markup_escape_text(c["refs"])}</span>')
                top.pack_end(refs, False, False, 0)
            meta = Gtk.Label(xalign=0)
            meta.set_markup(
                f'<span size="small" foreground="#9a9996"><tt>{c["short"]}</tt> · '
                f'{GLib.markup_escape_text(c["author"])} · {GLib.markup_escape_text(c["when"])}</span>'
            )
            box.pack_start(top, False, False, 0)
            box.pack_start(meta, False, False, 0)
            row.add(box)
            self.commits.add(row)
        self.commits.show_all()

    # ------------------------------------------------------------ events
    def _safe(self, fn, *args):
        try:
            fn(*args)
        except GitError as exc:
            self._error(_("git returned an error"), str(exc))
        self.refresh()

    def _error(self, title, text):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=title)
        dlg.format_secondary_text(text[:2000])
        dlg.run()
        dlg.destroy()

    def _ask(self, title, text, ok):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION, text=title)
        dlg.format_secondary_text(text)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(ok, Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        r = dlg.run()
        dlg.destroy()
        return r == Gtk.ResponseType.OK

    def on_toggle(self, _check, f):
        fully_staged = f["staged"] and not (f["unstaged"] and f["code"] != "?")
        # deferred: refresh() rebuilds the row that is emitting the signal
        GLib.idle_add(lambda: self._safe(unstage if fully_staged else stage, self.repo, f) and False)

    def on_file_selected(self, _lb, row):
        if not row:
            return
        f = row.file
        self._selected_path = f["path"]
        try:
            _set_diff(self.diff_tv, file_diff(self.repo, f))
        except GitError as exc:
            _set_diff(self.diff_tv, "", str(exc))
        self.tabs.set_current_page(0)

    def on_commit_selected(self, _lb, row):
        if row:
            try:
                _set_diff(self.commit_tv, show_commit(self.repo, row.commit["hash"]))
            except GitError as exc:
                _set_diff(self.commit_tv, "", str(exc))

    def on_message_key(self, _w, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.on_commit()
            return True
        return False

    def on_commit(self, *_a):
        buf = self.message.get_buffer()
        msg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if not msg:
            self._error(_("Missing message"), _("Describe what you changed before committing."))
            self.message.grab_focus()
            return
        if not any(f["staged"] for f in self.files):
            if not self._ask(_("Nothing is staged"), _("Include all changes in this commit?"), _("Include all and commit")):
                return
            try:
                stage_all(self.repo)
            except GitError as exc:
                self._error(_("Could not stage the changes"), str(exc))
                return
        try:
            commit(self.repo, msg + "\n")
        except GitError as exc:
            self._error(_("Could not commit"), str(exc))
            self.refresh()
            return
        buf.set_text("")
        self._selected_path = None
        self.refresh()
        self.tabs.set_current_page(1)

    def _git_script(self, title, cmd):
        q = shlex.quote
        return (
            "set -eo pipefail\n"
            f"cd {q(self.repo)}\n"
            f"printf '\\n\\033[1;36m==> %s\\033[0m\\n' {q(title)}\n"
            f"{cmd}\n"
            f"printf '\\n\\033[1;32m✔ %s\\033[0m\\n' {q(_('Done'))}\n"
        )

    def _run(self, title, cmd):
        name = Path(self.approot).name
        self.run_script(f"{name}: {title}", self._git_script(title, cmd), lambda *_a: self.refresh())

    def on_push(self, *_a):
        if self.state["upstream"]:
            self._run("git push", "git push")
        else:
            remote = "origin" if "origin" in self.remotes else self.remotes[0]
            self._run(
                _("git push (publish branch to {remote})").format(remote=remote),
                f"git push -u {shlex.quote(remote)} HEAD",
            )

    def on_pull(self, *_a):
        failed = _("Could not pull automatically (diverged or uncommitted changes).")
        self._run("git pull", f"git pull --ff-only || {{ echo; echo {shlex.quote(failed)}; exit 1; }}")

    def on_fetch(self, *_a):
        self._run("git fetch", "git fetch --all --prune")

    def on_branch_changed(self, box):
        if self._building:
            return
        target = box.get_active_id()
        if not target or target == "__detached__" or target == self.state.get("branch"):
            return
        self._run(_("switch to branch {branch}").format(branch=target), f"git switch {shlex.quote(target)}")

    def on_new_branch(self, *_a):
        dlg = Gtk.Dialog(title=_("New branch"), transient_for=self.window, modal=True)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        ok = dlg.add_button(_("Create and switch"), Gtk.ResponseType.OK)
        ok.get_style_context().add_class("suggested-action")
        dlg.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(placeholder_text="feature/my-change", activates_default=True, margin=14)
        dlg.get_content_area().add(entry)
        dlg.show_all()
        name = entry.get_text().strip() if dlg.run() == Gtk.ResponseType.OK else ""
        dlg.destroy()
        if name:
            try:
                run(self.repo, "check-ref-format", "--branch", name)
            except GitError:
                self._error(_("Invalid branch name"), name)
                return
            self._safe(run, self.repo, "switch", "-c", name)

    def on_init(self, *_a):
        try:
            run(self.approot, "init", "-q")
        except GitError as exc:
            self._error(_("Could not initialize git"), str(exc))
            return
        self.build()
        self.refresh()
