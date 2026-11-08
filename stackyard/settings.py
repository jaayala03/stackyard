"""User preferences (language and theme), stored as JSON in the XDG config dir."""

import json
import os
import re
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

CONFIG_DIR = Path(GLib.get_user_config_dir()) / "stackyard"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULTS = {"language": "auto", "theme": "system", "notifications": "background", "auto_stop": "0", "check_updates": True}

LANGUAGES = [("auto", "System default"), ("en", "English"), ("es", "Español")]
THEMES = [("system", "System default"), ("light", "Light"), ("dark", "Dark")]


OLD_CONFIG_FILE = Path(GLib.get_user_config_dir()) / "panel-ddev" / "settings.json"  # name before 1.1.0


def load():
    if not CONFIG_FILE.exists() and OLD_CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(OLD_CONFIG_FILE.read_text())
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **data}


def save(values):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, indent=2))
    os.replace(tmp, CONFIG_FILE)


def project_pref(project, key, default=None):
    return load().get("projects", {}).get(project, {}).get(key, default)


def set_project_pref(project, key, value):
    values = load()
    values.setdefault("projects", {}).setdefault(project, {})[key] = value
    save(values)


# --------------------------------------------------------------------- theme
_THEME_DIRS = [
    Path.home() / ".themes",
    Path(GLib.get_user_data_dir()) / "themes",
    *(Path(d) / "themes" for d in GLib.get_system_data_dirs()),
]
_original = {}


def _theme_exists(name):
    return any((d / name / "gtk-3.0").is_dir() for d in _THEME_DIRS)


def _is_dark(name):
    return "dark" in name.lower()


def _light_variant(name):
    for candidate in (re.sub(r"-?[Dd]ark", "", name), name.replace("-dark", ""), "Adwaita"):
        if candidate and _theme_exists(candidate):
            return candidate
    return "Adwaita"


def _dark_variant(name):
    if _is_dark(name):
        return name
    parts = name.split("-")
    candidates = ["-".join(parts[:i] + ["Dark"] + parts[i:]) for i in range(1, len(parts) + 1)]
    candidates += [f"{name}-dark", f"{name}-Dark"]
    for candidate in candidates:
        if _theme_exists(candidate):
            return candidate
    return None


def apply_theme(mode):
    """mode: 'system', 'light' or 'dark'. Returns True if the result is dark."""
    gtk = Gtk.Settings.get_default()
    if not _original:
        _original["name"] = gtk.get_property("gtk-theme-name")
        _original["prefer_dark"] = gtk.get_property("gtk-application-prefer-dark-theme")
    base = _original["name"]

    if mode == "light":
        name, prefer_dark = (_light_variant(base) if _is_dark(base) else base), False
    elif mode == "dark":
        name, prefer_dark = (_dark_variant(base) or base), True
    else:
        name, prefer_dark = base, _original["prefer_dark"]

    gtk.set_property("gtk-theme-name", name)
    gtk.set_property("gtk-application-prefer-dark-theme", prefer_dark)
    return is_dark_now()


def is_dark_now():
    gtk = Gtk.Settings.get_default()
    return _is_dark(gtk.get_property("gtk-theme-name")) or gtk.get_property("gtk-application-prefer-dark-theme")
