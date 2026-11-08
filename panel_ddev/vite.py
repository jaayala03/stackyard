"""Sets up the Vite dev server (HMR) to work through DDEV.

1. Exposes container port 5173 over HTTPS in `.ddev/config.vite.yaml`
   (DDEV merges every `.ddev/config.*.yaml`, so the main config is untouched).
2. Adds a `server` block to vite.config so Vite listens on all interfaces and
   serves assets from the project's DDEV URL.
"""

import re
from pathlib import Path

from . import ddev

CONFIG_NAMES = ("vite.config.js", "vite.config.ts", "vite.config.mjs", "vite.config.mts", "vite.config.cjs")
DDEV_FILE = "config.vite.yaml"
PORT = 5173

DDEV_YAML = f"""# Added by Panel DDEV: exposes the Vite dev server (HMR) through DDEV.
web_extra_exposed_ports:
  - name: vite
    container_port: {PORT}
    http_port: {PORT - 1}
    https_port: {PORT}
"""


def server_block(tld):
    tld_re = re.escape(tld).replace("/", r"\/")
    return (
        "    server: {\n"
        "        // Added by Panel DDEV: serve HMR through the DDEV URL\n"
        "        host: '0.0.0.0',\n"
        f"        port: {PORT},\n"
        "        strictPort: true,\n"
        f"        origin: `${{process.env.DDEV_PRIMARY_URL_WITHOUT_PORT}}:{PORT}`,\n"
        f"        cors: {{ origin: /https?:\\/\\/([A-Za-z0-9\\-\\.]+)?(\\.{tld_re})(?::\\d+)?$/ }},\n"
        "    },\n"
    )


def _project_tld(root):
    """The project's own project_tld if it sets one, otherwise the global one."""
    try:
        import yaml
        cfg = yaml.safe_load((Path(root) / ".ddev" / "config.yaml").read_text()) or {}
        if cfg.get("project_tld"):
            return cfg["project_tld"]
    except (OSError, ValueError):
        pass
    return ddev.project_tld()


def find_config(approot):
    for name in CONFIG_NAMES:
        path = Path(approot) / name
        if path.exists():
            return path
    return None


def status(approot):
    """(config_path or None, ddev_ready, vite_ready)."""
    cfg = find_config(approot)
    ddev_ready = (Path(approot) / ".ddev" / DDEV_FILE).exists()
    vite_ready = bool(cfg and "DDEV_PRIMARY_URL" in cfg.read_text())
    return cfg, ddev_ready, vite_ready


def configure(approot):
    """Applies both changes. Returns (changed_vite_config, manual_snippet).
    manual_snippet is set when vite.config could not be patched safely."""
    root = Path(approot)
    (root / ".ddev").mkdir(exist_ok=True)
    (root / ".ddev" / DDEV_FILE).write_text(DDEV_YAML)

    cfg = find_config(root)
    block = server_block(_project_tld(root))
    if not cfg:
        return False, block
    text = cfg.read_text()
    if "DDEV_PRIMARY_URL" in text:
        return False, None
    if re.search(r"^\s*server\s*:", text, re.M):
        return False, block  # the project already has a server block: let the user merge it
    m = re.search(r"defineConfig\(\s*(?:\([^)]*\)\s*=>\s*\(?\s*)?\{\s*\n", text)
    if not m:
        return False, block
    cfg.with_name(cfg.name + ".bak").write_text(text)
    cfg.write_text(text[:m.end()] + block + text[m.end():])
    return True, None
