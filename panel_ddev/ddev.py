"""Capa que habla con DDEV: listar proyectos, leer su configuración y
construir los scripts de bash que se ejecutan en la terminal integrada."""

import grp
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import yaml

HOME = Path.home()
DEFAULT_PARENT = HOME / "proyectos"

# (valor para ddev, etiqueta, docroot por defecto)
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
    ("generic", "Genérico (sin PHP)", ""),
]
AUTO_TYPE = ("", "Detectar automáticamente", "")

# Comando que crea el proyecto desde cero para cada tipo
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
    """Tras añadir al usuario al grupo docker hay que reiniciar sesión.
    Mientras tanto, usamos `sg docker` para no necesitar sudo."""
    try:
        gid = grp.getgrnam("docker").gr_gid
    except KeyError:
        return True
    return gid in os.getgroups()


def shell_argv(command):
    """argv para ejecutar una línea de bash con acceso a Docker."""
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
    raise DdevError((proc.stderr or proc.stdout).strip() or "ddev no devolvió datos")


def list_projects():
    raw = _run_json("ddev list -j")
    projects = raw if isinstance(raw, list) else []
    for p in projects:
        p.update(read_config(p.get("approot", "")))
    return sorted(projects, key=lambda p: p.get("name", ""))


def read_config(approot):
    """Lee .ddev/config.yaml (funciona aunque el proyecto esté parado)."""
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


def label_for(options, value):
    for v, label, *_ in options:
        if v == value:
            return label
    return value or "—"


# ---------------------------------------------------------------- scripts

_HEADER = r"""set -eo pipefail
paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\n\033[1;32m✔ %s\033[0m\n' "$*"; }
trap 'printf "\n\033[1;31m✘ Algo falló. Revisa los mensajes de arriba.\033[0m\n"' ERR
"""


def _q(v):
    return shlex.quote(str(v))


def _paso(text):
    return f"paso {_q(text)}"


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
    """o: mode('new'|'clone'), name, path, repo, branch, type, docroot, php,
    node, webserver, db, scaffold, deps, phpmyadmin, launch."""
    path = o["path"]
    s = [_HEADER]
    if o["mode"] == "clone":
        branch = f"--branch {_q(o['branch'])} " if o.get("branch") else ""
        s.append(_paso(f"Clonando {o['repo']}"))
        s.append(f"git clone {branch}{_q(o['repo'])} {_q(path)}")
        s.append(f"cd {_q(path)}")
    else:
        s.append(_paso(f"Creando la carpeta {path}"))
        s.append(f"mkdir -p {_q(path)} && cd {_q(path)}")

    s.append(_paso("Configurando DDEV"))
    s.append(f"ddev config {_config_flags(o)}")

    if o["mode"] == "new":
        scaffold = SCAFFOLD.get(o.get("type")) if o.get("scaffold") else None
        if scaffold:
            s.append(_paso(f"Instalando {label_for(PROJECT_TYPES, o['type'])}"))
            s.append(scaffold)
        elif o.get("type") not in ("generic",):
            docroot = o.get("docroot") or "."
            s.append(f"mkdir -p {_q(docroot)}")
            s.append(
                f"[ -e {_q(docroot)}/index.php ] || printf '%s\\n' "
                f"{_q('<?php phpinfo();')} > {_q(docroot)}/index.php"
            )
    else:
        if o.get("deps"):
            s.append(
                "if [ -f artisan ] && [ ! -f .env ] && [ -f .env.example ]; then "
                "paso 'Creando .env a partir de .env.example'; cp .env.example .env; fi"
            )

    if o.get("phpmyadmin"):
        s.append(_paso("Añadiendo phpMyAdmin"))
        s.append("ddev add-on get ddev/ddev-phpmyadmin")

    s.append(_paso("Arrancando el proyecto (puede pedir tu contraseña para el dominio)"))
    s.append("ddev start")

    if o["mode"] == "clone" and o.get("deps"):
        s.append("if [ -f composer.json ]; then paso 'composer install'; ddev composer install; fi")
        s.append(
            "if [ -f artisan ] && ! grep -q '^APP_KEY=.\\+' .env 2>/dev/null; then "
            "paso 'Generando APP_KEY'; ddev artisan key:generate; fi"
        )
        s.append("if [ -f package.json ]; then paso 'npm install'; ddev npm install; fi")

    if o.get("launch"):
        s.append("ddev launch")
    s.append(f"ok {_q('Proyecto listo: https://' + o['name'] + '.' + project_tld())}")
    return "\n".join(s) + "\n"


def script_edit(approot, o, old_db):
    s = [_HEADER, f"cd {_q(approot)}"]
    db_changed = o.get("db") and o["db"] != old_db
    opts = dict(o)
    if db_changed:
        opts["db"] = None  # la base de datos se cambia con migrate-database
    s.append(_paso("Guardando la nueva configuración"))
    s.append(f"ddev config {_config_flags(opts, include_name=False)}")
    if db_changed:
        s.append(_paso(f"Migrando la base de datos a {o['db']}"))
        s.append(f"ddev debug migrate-database {_q(o['db'])}")
    s.append(_paso("Reiniciando"))
    s.append("ddev restart")
    s.append("ok 'Configuración aplicada'")
    return "\n".join(s) + "\n"


def script_simple(approot, commands, done_msg):
    s = [_HEADER]
    if approot:
        s.append(f"cd {_q(approot)}")
    for title, cmd in commands:
        s.append(f"paso {_q(title)}")
        s.append(cmd)
    s.append(f"ok {_q(done_msg)}")
    return "\n".join(s) + "\n"
