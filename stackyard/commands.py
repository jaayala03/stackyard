"""Quick commands: framework-specific shortcuts, package.json scripts and the
user's own saved commands (stored per project in the settings file)."""

import json
import shlex
from pathlib import Path

from . import settings

# kinds: "run" (runs to completion), "interactive" (keeps running / needs input),
#        "danger" (asks for confirmation first)
BUILTIN = {
    "laravel": [
        ("artisan migrate", "ddev artisan migrate", "run"),
        ("migrate:fresh --seed", "ddev artisan migrate:fresh --seed", "danger"),
        ("optimize:clear", "ddev artisan optimize:clear", "run"),
        ("artisan test", "ddev artisan test", "run"),
        ("tinker", "ddev artisan tinker", "interactive"),
        ("queue:work", "ddev artisan queue:work", "interactive"),
    ],
    "wordpress": [
        ("wp plugin update --all", "ddev wp plugin update --all", "run"),
        ("wp core update", "ddev wp core update", "run"),
        ("wp cache flush", "ddev wp cache flush", "run"),
        ("wp user list", "ddev wp user list", "run"),
    ],
    "symfony": [
        ("cache:clear", "ddev exec bin/console cache:clear", "run"),
        ("doctrine:migrations:migrate", "ddev exec bin/console doctrine:migrations:migrate -n", "run"),
    ],
    "drupal11": [
        ("drush cr", "ddev drush cr", "run"),
        ("drush updb", "ddev drush updb -y", "run"),
        ("drush uli", "ddev drush uli", "run"),
    ],
    "craftcms": [
        ("craft migrate/all", "ddev craft migrate/all --interactive=0", "run"),
        ("craft clear-caches/all", "ddev craft clear-caches/all", "run"),
    ],
    "codeigniter": [
        ("spark migrate", "ddev exec php spark migrate", "run"),
    ],
    "cakephp": [
        ("cake migrations migrate", "ddev exec bin/cake migrations migrate", "run"),
    ],
    "magento2": [
        ("setup:upgrade", "ddev magento setup:upgrade", "run"),
        ("cache:flush", "ddev magento cache:flush", "run"),
    ],
}

COMPOSER = [("composer update", "ddev composer update", "run")]

# npm scripts that keep running until stopped
_LONG_SCRIPTS = ("dev", "watch", "serve", "start", "hot")


def builtin_commands(project_type):
    kind = "drupal11" if project_type.startswith("drupal") else project_type
    return BUILTIN.get(kind, [])


def package_scripts(approot):
    """npm scripts of the project's package.json as quick commands."""
    try:
        scripts = json.loads((Path(approot) / "package.json").read_text()).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for name in scripts:
        kind = "interactive" if name.split(":")[0] in _LONG_SCRIPTS else "run"
        out.append((f"npm run {name}", f"ddev npm run {shlex.quote(name)}", kind))
    return out


def composer_commands(approot):
    return COMPOSER if (Path(approot) / "composer.json").exists() else []


# ------------------------------------------------------------ saved commands
def saved_commands(project_name):
    prefs = settings.load()
    return [(c["label"], c["command"], "interactive" if c.get("interactive") else "run")
            for c in prefs.get("commands", {}).get(project_name, [])]


def add_command(project_name, label, command, interactive=False):
    prefs = settings.load()
    prefs.setdefault("commands", {}).setdefault(project_name, []).append(
        {"label": label, "command": command, "interactive": bool(interactive)}
    )
    settings.save(prefs)


def remove_command(project_name, label):
    prefs = settings.load()
    items = prefs.get("commands", {}).get(project_name, [])
    prefs["commands"][project_name] = [c for c in items if c["label"] != label]
    settings.save(prefs)
