"""Talks to DDEV: lists projects, reads their config and builds the bash
scripts that run in the embedded terminal."""

import grp
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import yaml

from .i18n import _

HOME = Path.home()
DEFAULT_PARENT = HOME / "proyectos" if (HOME / "proyectos").exists() else HOME / "projects"

# (ddev value, label, default docroot)
PROJECT_TYPES = [
    ("php", "PHP", ""),
    ("laravel", "Laravel", "public"),
    ("wordpress", "WordPress", ""),
    ("symfony", "Symfony", "public"),
    ("drupal11", "Drupal 11", "web"),
    ("codeigniter", "CodeIgniter 4", "public"),
    ("cakephp", "CakePHP", "webroot"),
    ("craftcms", "Craft CMS", "web"),
    ("magento2", "Magento 2", "pub"),
    ("generic", "Generic (no PHP)", ""),
]
AUTO_TYPE = ("", "Detect automatically", "")

# Command that creates a brand-new project of each type
SCAFFOLD = {
    "laravel": "ddev composer create-project laravel/laravel",
    "wordpress": "ddev start && ddev wp core download",
    "symfony": "ddev composer create-project symfony/skeleton",
    "drupal11": "ddev composer create-project drupal/recommended-project:^11",
    "codeigniter": "ddev composer create-project codeigniter4/appstarter",
    "cakephp": "ddev composer create-project cakephp/app",
    "craftcms": "ddev composer create-project craftcms/craft",
}

PHP_VERSIONS = ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0", "7.4", "7.3", "7.2", "7.1", "7.0", "5.6"]
NODE_VERSIONS = ["24", "22", "20", "18", "25"]
WEBSERVERS = [("apache-fpm", "Apache"), ("nginx-fpm", "nginx")]
DATABASES = [
    ("mariadb:11.8", "MariaDB 11.8"),
    ("mariadb:10.11", "MariaDB 10.11"),
    ("mysql:8.4", "MySQL 8.4"),
    ("mysql:8.0", "MySQL 8.0"),
    ("postgres:18", "PostgreSQL 18"),
    ("postgres:17", "PostgreSQL 17"),
]

DEFAULTS = {
    "php": "8.4",
    "node": "24",
    "webserver": "apache-fpm",
    "db": "mariadb:11.8",
}

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
EDITORS = ["code", "codium", "phpstorm", "subl", "zed", "gnome-text-editor", "mousepad"]


class DdevError(Exception):
    pass


def ddev_installed():
    return shutil.which("ddev") is not None


def _docker_group_active():
    """After adding the user to the docker group a new login is needed.
    Until then we go through `sg docker` so sudo is not required."""
    try:
        gid = grp.getgrnam("docker").gr_gid
    except KeyError:
        return True
    return gid in os.getgroups()


def shell_argv(command):
    """argv that runs a bash command line with Docker access."""
    if _docker_group_active():
        return ["bash", "-c", command]
    return ["sg", "docker", "-c", "bash -c " + shlex.quote(command)]


def _run_json(command, cwd=None, timeout=60):
    proc = subprocess.run(
        shell_argv(command), cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "raw" in data:
            return data["raw"]
    raise DdevError((proc.stderr or proc.stdout).strip() or "ddev returned no data")


def list_projects():
    raw = _run_json("ddev list -j")
    projects = raw if isinstance(raw, list) else []
    for p in projects:
        p.update(read_config(p.get("approot", "")))
    return sorted(projects, key=lambda p: p.get("name", ""))


def read_config(approot):
    """Reads .ddev/config.yaml (works even when the project is stopped)."""
    cfg = {}
    path = Path(approot) / ".ddev" / "config.yaml"
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        pass
    db = cfg.get("database") or {}
    return {
        "cfg_type": cfg.get("type", ""),
        "cfg_docroot": cfg.get("docroot", ""),
        "cfg_php": str(cfg.get("php_version", "")),
        "cfg_node": str(cfg.get("nodejs_version", "")),
        "cfg_webserver": cfg.get("webserver_type", "nginx-fpm"),
        "cfg_db": f"{db.get('type', 'mariadb')}:{db.get('version', '')}".rstrip(":"),
    }


def project_tld():
    try:
        cfg = yaml.safe_load((HOME / ".ddev" / "global_config.yaml").read_text()) or {}
        return cfg.get("project_tld") or "ddev.site"
    except (OSError, yaml.YAMLError):
        return "ddev.site"


def has_phpmyadmin(approot):
    return (Path(approot) / ".ddev" / "docker-compose.phpmyadmin.yaml").exists()


def find_editor():
    for e in EDITORS:
        if shutil.which(e):
            return e
    return None


def name_from_repo(url):
    base = url.rstrip("/").split("/")[-1].split(":")[-1]
    base = re.sub(r"\.git$", "", base).lower()
    base = re.sub(r"[^a-z0-9-]+", "-", base).strip("-")
    return base


# (marker files, project type, docroot) checked in order
_DETECT = [
    (("artisan",), "laravel", "public"),
    (("wp-config.php",), "wordpress", ""),
    (("wp-content",), "wordpress", ""),
    (("web/core",), "drupal11", "web"),
    (("symfony.lock",), "symfony", "public"),
    (("bin/console", "public/index.php"), "symfony", "public"),
    (("spark",), "codeigniter", "public"),
    (("craft",), "craftcms", "web"),
    (("bin/cake",), "cakephp", "webroot"),
    (("bin/magento",), "magento2", "pub"),
]


def detect_type(path):
    """Best guess of (project type, docroot) from the files in `path`."""
    root = Path(path)
    for markers, kind, docroot in _DETECT:
        if all((root / m).exists() for m in markers):
            return kind, docroot
    if (root / "public" / "index.php").exists():
        return "php", "public"
    if any(root.glob("*.php")):
        return "php", ""
    return "", ""


def label_for(options, value):
    """Translated label of `value` in a list of (value, label, ...) tuples."""
    for v, label, *_rest in options:
        if v == value:
            return _(label)
    return value or "—"


# ---------------------------------------------------------------- scripts

def _q(v):
    return shlex.quote(str(v))


def _header():
    failed = _("Something went wrong. Check the messages above.")
    return (
        "set -eo pipefail\n"
        "step() { printf '\\n\\033[1;36m==> %s\\033[0m\\n' \"$*\"; }\n"
        "ok()   { printf '\\n\\033[1;32m✔ %s\\033[0m\\n' \"$*\"; }\n"
        f"FAILED_MSG={_q(failed)}\n"
        "trap 'printf \"\\n\\033[1;31m✘ %s\\033[0m\\n\" \"$FAILED_MSG\"' ERR\n"
    )


def _step(text):
    return f"step {_q(text)}"


def _ok(text):
    return f"ok {_q(text)}"


def _config_flags(o, include_name=True):
    flags = []
    if include_name and o.get("name"):
        flags.append(f"--project-name={_q(o['name'])}")
    if o.get("type"):
        flags.append(f"--project-type={_q(o['type'])}")
        flags.append(f"--docroot={_q(o.get('docroot') or '.')}")
    flags += [
        f"--php-version={_q(o['php'])}",
        f"--nodejs-version={_q(o['node'])}",
        f"--webserver-type={_q(o['webserver'])}",
    ]
    if o.get("db"):
        flags.append(f"--database={_q(o['db'])}")
    return " ".join(flags)


def script_create(o):
    """o: mode('new'|'clone'|'existing'), name, path, repo, branch, type, docroot, php,
    node, webserver, db, scaffold, deps, phpmyadmin, launch."""
    path = o["path"]
    s = [_header()]
    if o["mode"] == "clone":
        branch = f"--branch {_q(o['branch'])} " if o.get("branch") else ""
        s.append(_step(_("Cloning {repo}").format(repo=o["repo"])))
        s.append(f"git clone {branch}{_q(o['repo'])} {_q(path)}")
        s.append(f"cd {_q(path)}")
    elif o["mode"] == "existing":
        s.append(f"cd {_q(path)}")
    else:
        s.append(_step(_("Creating folder {path}").format(path=path)))
        s.append(f"mkdir -p {_q(path)} && cd {_q(path)}")

    s.append(_step(_("Configuring DDEV")))
    s.append(f"ddev config {_config_flags(o)}")

    if o["mode"] == "new":
        scaffold = SCAFFOLD.get(o.get("type")) if o.get("scaffold") else None
        if scaffold:
            s.append(_step(_("Installing {framework}").format(framework=label_for(PROJECT_TYPES, o["type"]))))
            s.append(scaffold)
        elif o.get("type") != "generic":
            docroot = o.get("docroot") or "."
            s.append(f"mkdir -p {_q(docroot)}")
            s.append(
                f"[ -e {_q(docroot)}/index.php ] || printf '%s\\n' "
                f"{_q('<?php phpinfo();')} > {_q(docroot)}/index.php"
            )
    elif o.get("deps"):
        s.append(
            "if [ -f artisan ] && [ ! -f .env ] && [ -f .env.example ]; then "
            f"{_step(_('Creating .env from .env.example'))}; cp .env.example .env; fi"
        )

    if o.get("phpmyadmin"):
        s.append(_step(_("Adding phpMyAdmin")))
        s.append("ddev add-on get ddev/ddev-phpmyadmin")

    s.append(_step(_("Starting the project (it may ask for your password to add the domain)")))
    s.append("ddev start")

    if o["mode"] in ("clone", "existing") and o.get("deps"):
        s.append(f"if [ -f composer.json ]; then {_step('composer install')}; ddev composer install; fi")
        s.append(
            "if [ -f artisan ] && ! grep -q '^APP_KEY=.\\+' .env 2>/dev/null; then "
            f"{_step(_('Generating APP_KEY'))}; ddev artisan key:generate; fi"
        )
        s.append(f"if [ -f package.json ]; then {_step('npm install')}; ddev npm install; fi")

    if o.get("launch"):
        s.append("ddev launch")
    s.append(_ok(_("Project ready: {url}").format(url=f"https://{o['name']}.{project_tld()}")))
    return "\n".join(s) + "\n"


def script_edit(approot, o, old_db):
    s = [_header(), f"cd {_q(approot)}"]
    db_changed = o.get("db") and o["db"] != old_db
    opts = dict(o)
    if db_changed:
        opts["db"] = None  # the database is changed with migrate-database
    s.append(_step(_("Saving the new configuration")))
    s.append(f"ddev config {_config_flags(opts, include_name=False)}")
    if db_changed:
        s.append(_step(_("Migrating the database to {db}").format(db=o["db"])))
        s.append(f"ddev debug migrate-database {_q(o['db'])}")
    s.append(_step(_("Restarting")))
    s.append("ddev restart")
    s.append(_ok(_("Configuration applied")))
    return "\n".join(s) + "\n"


def script_simple(approot, commands, done_msg):
    s = [_header()]
    if approot:
        s.append(f"cd {_q(approot)}")
    for title, cmd in commands:
        s.append(_step(title))
        s.append(cmd)
    s.append(_ok(done_msg))
    return "\n".join(s) + "\n"
