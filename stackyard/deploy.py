"""Deploy tab: deploys with pm2 (`pm2 deploy`) using the project's ecosystem
file, and manages the app on the server over SSH (status, logs, reload).

Everything runs inside the project's web container, so neither Node nor pm2
is needed on this computer. SSH keys reach the container with `ddev auth ssh`."""

import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from . import ddev, pm2  # noqa: E402
from .i18n import _  # noqa: E402


def ssh_keys_loaded(approot):
    """Number of keys in DDEV's SSH agent, or None if it cannot be read."""
    try:
        proc = subprocess.run(ddev.shell_argv("ddev exec ssh-add -l"), cwd=approot, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout + proc.stderr
    if "no identities" in out:
        return 0
    if proc.returncode != 0:
        return None
    return len([line for line in proc.stdout.splitlines() if line.strip()])


class DeployView(Gtk.Box):
    """`window` provides confirm(), run_script() and terms (MainWindow)."""

    def __init__(self, project, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.project = project
        self.approot = project["approot"]
        self.window = window
        self.info = None
        self._loading = False
        self.status = Gtk.Label(label=_("Reading the pm2 ecosystem file…"), margin=24)
        self.status.get_style_context().add_class("dim-label")
        self.pack_start(self.status, True, True, 0)
        self.show_all()

    # ------------------------------------------------------------ data
    def refresh(self, project=None):
        if project:
            self.project = project
        if self._loading:
            return
        self._loading = True

        def work():
            info = pm2.summary(self.approot)
            keys = ssh_keys_loaded(self.approot) if self._running() else None
            GLib.idle_add(self._build, info, keys)

        threading.Thread(target=work, daemon=True).start()

    def _running(self):
        return self.project.get("status") == "running"

    # ------------------------------------------------------------ UI
    def _clear(self):
        for child in self.get_children():
            self.remove(child)

    def _message(self, text):
        self._clear()
        lbl = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER, margin=24, max_width_chars=70)
        lbl.get_style_context().add_class("dim-label")
        self.pack_start(lbl, True, True, 0)
        self.show_all()

    def _build(self, info, keys):
        self._loading = False
        self.info = info
        if info is None:
            self._message(_("No pm2 ecosystem file found (ecosystem.config.js, .cjs, .mjs, .json, .yml…)."))
            return False
        if info.get("error"):
            self._message(_("Could not read {file}:\n{error}").format(file=info["file"].name, error=info["error"]))
            return False
        if not info["deploy"]:
            self._message(_("{file} has no “deploy” section. Add one to deploy with pm2 from here.").format(file=info["file"].name))
            return False
        self._clear()

        top = Gtk.Box(spacing=8)
        top.pack_start(Gtk.Label(label=_("Environment")), False, False, 0)
        self.env_combo = Gtk.ComboBoxText()
        for env in info["deploy"]:
            self.env_combo.append(env, env)
        self.env_combo.set_active(0)
        self.env_combo.connect("changed", lambda *_a: self._fill_details())
        top.pack_start(self.env_combo, False, False, 0)
        file_lbl = Gtk.Label()
        file_lbl.set_markup(f'<span foreground="#9a9996">{GLib.markup_escape_text(info["file"].name)}</span>')
        top.pack_end(file_lbl, False, False, 0)
        self.pack_start(top, False, False, 0)

        self.details = Gtk.Grid(column_spacing=24, row_spacing=6, margin=4)
        frame = Gtk.Frame(label=" " + _("Server") + " ")
        frame.add(self.details)
        self.pack_start(frame, False, False, 0)

        # SSH keys
        ssh = Gtk.Box(spacing=8)
        if not self._running():
            text = _("Start the project to deploy: commands run inside its container.")
        elif keys is None:
            text = _("Could not check the SSH keys in DDEV.")
        elif keys == 0:
            text = _("No SSH keys loaded in DDEV yet. Load them to connect to the server.")
        else:
            text = _("{n} SSH key(s) loaded in DDEV.").format(n=keys)
        ssh_lbl = Gtk.Label(label=text, xalign=0, wrap=True)
        ssh.pack_start(ssh_lbl, True, True, 0)
        load = Gtk.Button(label=_("Load my SSH keys"))
        load.set_tooltip_text(_("Runs “ddev auth ssh”: adds the keys from ~/.ssh to DDEV (it may ask for their passphrase)"))
        load.connect("clicked", lambda *_a: self.on_auth())
        ssh.pack_end(load, False, False, 0)
        self.pack_start(ssh, False, False, 0)

        # actions
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, min_children_per_line=2,
                           column_spacing=6, row_spacing=6, homogeneous=True)
        actions = [
            ("send-to-symbolic", _("Deploy now"), _("pm2 deploy: pull the branch on the server and run post-deploy"), self.on_deploy, True),
            ("edit-undo-symbolic", _("Roll back"), _("pm2 deploy … revert 1: go back to the previous release"), self.on_revert, True),
            ("view-list-symbolic", _("Status"), _("pm2 ls on the server"), self.on_status, False),
            ("text-x-generic-symbolic", _("Live logs"), _("pm2 logs on the server"), self.on_logs, False),
            ("view-refresh-symbolic", _("Reload app"), _("pm2 reload of the apps in the ecosystem file"), self.on_reload, True),
            ("network-transmit-receive-symbolic", _("Test connection"), _("Connects to the server over SSH"), self.on_test, False),
            ("emblem-system-symbolic", _("First-time setup"), _("pm2 deploy … setup: clones the repository on the server"), self.on_setup, True),
        ]
        for icon, label, tip, cb, _danger in actions:
            b = Gtk.Button()
            box = Gtk.Box(spacing=6)
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
            box.pack_start(Gtk.Label(label=label), False, False, 0)
            b.add(box)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, c=cb: c())
            b.set_sensitive(self._running())
            if label == _("Deploy now"):
                b.get_style_context().add_class("suggested-action")
            flow.add(b)
        self.pack_start(flow, False, False, 0)

        apps = ", ".join(a["name"] for a in info["apps"]) or "—"
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup('<span size="small" foreground="#9a9996">{}</span>'.format(GLib.markup_escape_text(
            _("Apps: {apps}. Commands run in the project's container with pm2 from npm; the output appears below.").format(apps=apps))))
        self.pack_start(hint, False, False, 0)
        self._fill_details()
        self.show_all()
        return False

    def _env(self):
        return self.env_combo.get_active_id()

    def _deploy(self):
        return self.info["deploy"][self._env()]

    def _fill_details(self):
        for c in self.details.get_children():
            self.details.remove(c)
        d = self._deploy()
        rows = [
            (_("Server"), pm2.ssh_target(d) + (f":{d['port']}" if d.get("port") else "")),
            (_("Folder"), d["path"]),
            (_("Branch"), d["ref"]),
            (_("Repository"), d["repo"]),
            (_("After deploy"), d["post_deploy"] or "—"),
        ]
        for i, (k, v) in enumerate(rows):
            kl = Gtk.Label(label=k, xalign=0)
            kl.get_style_context().add_class("dim-label")
            vl = Gtk.Label(label=str(v), xalign=0, selectable=True, wrap=True, max_width_chars=70)
            vl.set_ellipsize(Pango.EllipsizeMode.NONE)
            self.details.attach(kl, 0, i, 1, 1)
            self.details.attach(vl, 1, i, 1, 1)
        self.details.show_all()

    # ------------------------------------------------------------ actions
    def _run(self, title, command, done_msg):
        name = self.project["name"]
        script = ddev.script_simple(self.approot, [(title, command)], done_msg)
        self.window.terms.run(f"{name}: {title}", script, cwd=self.approot,
                              on_done=lambda *_a: self.refresh())

    def _confirm_prod(self, title, text, ok):
        return self.window.confirm(title, text, ok, destructive=True)

    def on_auth(self):
        self.window.terms.interactive(f"{self.project['name']}: ddev auth ssh", "ddev auth ssh", cwd=self.approot,
                                      on_done=lambda *_a: self.refresh())

    def on_deploy(self):
        env, d = self._env(), self._deploy()
        if self._confirm_prod(_("Deploy to {env}?").format(env=env),
                              _("Branch {ref} is deployed to {target}:{path} and “{post}” runs there.").format(
                                  ref=d["ref"], target=pm2.ssh_target(d), path=d["path"], post=d["post_deploy"] or "—"),
                              _("Deploy now")):
            self._run(_("Deploying to {env}").format(env=env), pm2.in_container(pm2.deploy_cmd(self.info["file"], env)),
                      _("Deployed to {env}").format(env=env))

    def on_revert(self):
        env = self._env()
        if self._confirm_prod(_("Roll back {env}?").format(env=env),
                              _("The server goes back to the previous release."), _("Roll back")):
            self._run(_("Rolling back {env}").format(env=env),
                      pm2.in_container(pm2.deploy_cmd(self.info["file"], env, "revert 1")), _("Rolled back"))

    def on_setup(self):
        env = self._env()
        if self._confirm_prod(_("Set up {env} for the first time?").format(env=env),
                              _("pm2 creates the folders and clones the repository on the server. Do it only once."),
                              _("Set up")):
            self._run(_("Setting up {env}").format(env=env),
                      pm2.in_container(pm2.deploy_cmd(self.info["file"], env, "setup")), _("Server ready"))

    def on_status(self):
        self._run(_("Status on the server"), pm2.in_container(pm2.remote_cmd(self._deploy(), "pm2 ls")), _("Done"))

    def on_test(self):
        self._run(_("Testing the SSH connection"),
                  pm2.in_container(pm2.remote_cmd(self._deploy(), "echo connected to $(hostname) && command -v pm2")),
                  _("Connection works"))

    def on_logs(self):
        cmd = pm2.remote_cmd(self._deploy(), "pm2 logs --lines 100", tty=True)
        self.window.terms.interactive(f"{self.project['name']}: {_('server logs')}", pm2.in_container_tty(cmd), cwd=self.approot)

    def on_reload(self):
        names = " ".join(a["name"] for a in self.info["apps"]) or "all"
        if self._confirm_prod(_("Reload the app on the server?"),
                              _("pm2 reload {apps} (zero-downtime restart when the app supports it).").format(apps=names),
                              _("Reload")):
            self._run(_("Reloading on the server"), pm2.in_container(pm2.remote_cmd(self._deploy(), f"pm2 reload {names}")),
                      _("Reloaded"))
