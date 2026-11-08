"""Lists the user's GitHub repositories through the GitHub CLI (gh) and lets
them pick one to clone."""

import json
import shutil
import subprocess
import threading
from datetime import datetime, timezone

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .i18n import _  # noqa: E402

FIELDS = "nameWithOwner,description,isPrivate,isFork,isArchived,url,sshUrl,updatedAt,primaryLanguage"
LIMIT = 400


class GitHubError(Exception):
    pass


def gh_installed():
    return shutil.which("gh") is not None


def gh_logged_in():
    if not gh_installed():
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def _gh_json(*args):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise GitHubError(proc.stderr.strip() or "gh failed")
    return json.loads(proc.stdout or "null")


def git_protocol():
    proc = subprocess.run(["gh", "config", "get", "git_protocol"], capture_output=True, text=True)
    return proc.stdout.strip() or "https"


def list_repos():
    """The user's own repositories plus those of their organizations,
    most recently updated first."""
    owners = [None] + (_gh_json("api", "user/orgs", "--jq", "[.[].login]") or [])
    repos, seen = [], set()
    for owner in owners:
        args = ["repo", "list"] + ([owner] if owner else []) + ["--limit", str(LIMIT), "--json", FIELDS]
        try:
            items = _gh_json(*args)
        except GitHubError:
            if owner is None:
                raise
            continue  # an organization we cannot list is not fatal
        for r in items:
            if r["nameWithOwner"] not in seen:
                seen.add(r["nameWithOwner"])
                repos.append(r)
    repos.sort(key=lambda r: r.get("updatedAt") or "", reverse=True)
    return repos


def clone_url(repo, protocol):
    return repo["sshUrl"] if protocol == "ssh" else repo["url"] + ".git"


def _ago(iso):
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return ""
    days = (datetime.now(timezone.utc) - then).days
    if days < 1:
        return _("today")
    if days < 30:
        return _("{n} days ago").format(n=days)
    if days < 365:
        return _("{n} months ago").format(n=days // 30)
    return _("{n} years ago").format(n=days // 365)


class RepoPicker(Gtk.Dialog):
    """Searchable list of repositories. After run() == OK, `selected` holds the repo."""

    def __init__(self, parent):
        super().__init__(title=_("Your GitHub repositories"), transient_for=parent, modal=True)
        self.set_default_size(620, 520)
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.ok = self.add_button(_("Select"), Gtk.ResponseType.OK)
        self.ok.get_style_context().add_class("suggested-action")
        self.ok.set_sensitive(False)
        self.selected = None
        self.protocol = "https"

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        self.search = Gtk.SearchEntry(placeholder_text=_("Search by name, owner, description or language"))
        self.search.connect("search-changed", lambda *_a: self.listbox.invalidate_filter())
        self.search.connect("activate", lambda *_a: self._activate_first())
        box.pack_start(self.search, False, False, 0)

        self.show_forks = Gtk.CheckButton(label=_("Show forks and archived"))
        self.show_forks.connect("toggled", lambda *_a: self.listbox.invalidate_filter())
        box.pack_start(self.show_forks, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        self.listbox.connect("row-selected", self._on_selected)
        self.listbox.connect("row-activated", lambda *_a: self.response(Gtk.ResponseType.OK))
        self.status = Gtk.Label(label=_("Loading repositories…"), margin=24)
        self.status.get_style_context().add_class("dim-label")
        self.status.show()
        self.listbox.set_placeholder(self.status)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroll.add(self.listbox)
        box.pack_start(scroll, True, True, 0)
        self.show_all()
        self.search.grab_focus()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            repos, protocol, error = list_repos(), git_protocol(), None
        except (GitHubError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
            repos, protocol, error = [], "https", str(exc)
        GLib.idle_add(self._fill, repos, protocol, error)

    def _fill(self, repos, protocol, error):
        self.protocol = protocol
        if error:
            self.status.set_text(_("Could not list your repositories:\n{error}").format(error=error))
            return False
        self.status.set_text(_("No repository matches."))
        for r in repos:
            self.listbox.add(self._row(r))
        self.listbox.show_all()
        return False

    def _row(self, r):
        row = Gtk.ListBoxRow()
        row.repo = r
        lang = (r.get("primaryLanguage") or {}).get("name") or ""
        row.haystack = " ".join([r["nameWithOwner"], r.get("description") or "", lang]).lower()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=6, spacing=2)
        top = Gtk.Box(spacing=8)
        name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        name.set_markup(f"<b>{GLib.markup_escape_text(r['nameWithOwner'])}</b>")
        top.pack_start(name, True, True, 0)
        tags = []
        if r.get("isPrivate"):
            tags.append(_("private"))
        if r.get("isFork"):
            tags.append(_("fork"))
        if r.get("isArchived"):
            tags.append(_("archived"))
        if tags:
            t = Gtk.Label()
            t.set_markup(f'<span size="small" foreground="#9a9996">{GLib.markup_escape_text(" · ".join(tags))}</span>')
            top.pack_end(t, False, False, 0)
        box.pack_start(top, False, False, 0)
        if r.get("description"):
            d = Gtk.Label(label=r["description"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            box.pack_start(d, False, False, 0)
        meta = " · ".join(x for x in (lang, _("updated {when}").format(when=_ago(r.get("updatedAt")))) if x)
        m = Gtk.Label(xalign=0)
        m.set_markup(f'<span size="small" foreground="#9a9996">{GLib.markup_escape_text(meta)}</span>')
        box.pack_start(m, False, False, 0)
        row.add(box)
        return row

    def _filter(self, row):
        r = row.repo
        if not self.show_forks.get_active() and (r.get("isFork") or r.get("isArchived")):
            return False
        words = self.search.get_text().lower().split()
        return all(w in row.haystack for w in words)

    def _on_selected(self, _lb, row):
        self.selected = row.repo if row else None
        self.ok.set_sensitive(row is not None)

    def _activate_first(self):
        for row in self.listbox.get_children():
            if row.get_child_visible() and self._filter(row):
                self.listbox.select_row(row)
                self.response(Gtk.ResponseType.OK)
                return
