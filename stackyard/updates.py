"""Checks GitHub for a newer release (at most once a day) and builds the
script that installs it."""

import json
import re
import time
import urllib.request

from . import REPO_URL, __version__, ddev, settings
from .i18n import _

API_URL = REPO_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
CHECK_EVERY = 24 * 3600


def _parse(version):
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3]) or (0,)


def is_newer(remote, local=__version__):
    return _parse(remote) > _parse(local)


def fetch_latest(timeout=10):
    """{'version', 'url', 'deb'} of the latest release, or None (offline, private repo…)."""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"Stackyard/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except (OSError, ValueError):
        return None
    deb = next((a["browser_download_url"] for a in data.get("assets", []) if a.get("name", "").endswith("_all.deb")), None)
    return {"version": data.get("tag_name", "").lstrip("v"), "url": data.get("html_url", REPO_URL), "deb": deb}


def due(prefs, now=None):
    if not prefs.get("check_updates", True):
        return False
    now = time.time() if now is None else now
    return now - float(prefs.get("_last_update_check", 0)) >= CHECK_EVERY


def check(now=None):
    """Runs a check if one is due. Returns the release dict when it is newer
    than this version and the user did not skip it, else None."""
    prefs = settings.load()
    if not due(prefs, now):
        return None
    latest = fetch_latest()
    prefs = settings.load()  # reload: the network call can take a while
    prefs["_last_update_check"] = time.time() if now is None else now
    settings.save(prefs)
    if latest and latest["version"] and is_newer(latest["version"]) and latest["version"] != prefs.get("skip_version"):
        return latest
    return None


def skip(version):
    prefs = settings.load()
    prefs["skip_version"] = version
    settings.save(prefs)


def install_script(release):
    """Downloads the new .deb and installs it with apt (asks for the sudo password)."""
    deb_url = ddev._q(release["deb"])
    return ddev.script_simple(None, [
        (_("Downloading Stackyard {version}").format(version=release["version"]),
         f"TMP=$(mktemp -d) && curl -fsSL -o \"$TMP/stackyard.deb\" {deb_url}"),
        (_("Installing (it may ask for your password)"), "sudo apt-get install -y \"$TMP/stackyard.deb\" && rm -rf \"$TMP\""),
    ], _("Stackyard {version} installed. Quit and reopen the app to use it.").format(version=release["version"]))
