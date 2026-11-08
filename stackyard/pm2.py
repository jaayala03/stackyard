"""pm2 ecosystem files: finds and reads them (JS/CJS/MJS/TS by running them
with the Node that ships in the DDEV web image, JSON/YAML directly), and
builds the commands of the Deploy tab (`pm2 deploy`, remote `pm2` over SSH).

Secrets from `env*` blocks are never shown; only names, scripts, ports and the
`deploy` section (host, user, path, ref, repo, hooks) are used."""

import json
import re
import shlex
import subprocess
from pathlib import Path

import yaml

# pm2 accepts any of these (https://pm2.keymetrics.io/docs/usage/application-declaration/)
CANDIDATES = [
    "ecosystem.config.js", "ecosystem.config.cjs", "ecosystem.config.mjs", "ecosystem.config.ts",
    "ecosystem.config.json", "ecosystem.config.json5", "ecosystem.config.yaml", "ecosystem.config.yml",
    "ecosystem.json", "ecosystem.yaml", "ecosystem.yml", "ecosystem.js", "ecosystem.cjs", "ecosystem.mjs",
    "pm2.config.js", "pm2.config.cjs", "pm2.config.mjs", "pm2.json", "process.json", "process.yml", "process.yaml",
]
SCRIPT_EXTS = {".js", ".cjs", ".mjs", ".ts"}
_cache = {}

# Node one-liner that prints the evaluated config as JSON (ESM or CommonJS, sync or async)
_EVAL = (
    "const {pathToFileURL}=require('url');"
    "(async()=>{const f=process.argv[1];"
    "let m;try{m=require(f)}catch(e){m=await import(pathToFileURL(f).href)}"
    "let c=(m&&m.default!==undefined)?m.default:m;if(typeof c==='function')c=await c();"
    "process.stdout.write(JSON.stringify(c))})().catch(e=>{console.error(e.message);process.exit(1)})"
)


class Pm2Error(Exception):
    pass


def find(root):
    """Path of the project's ecosystem file, or None. Exact pm2 names first,
    then any ecosystem*.<ext> in the project root."""
    root = Path(root)
    for name in CANDIDATES:
        if (root / name).is_file():
            return root / name
    for p in sorted(root.glob("ecosystem*")):
        if p.is_file() and p.suffix in SCRIPT_EXTS | {".json", ".yaml", ".yml", ".json5"}:
            return p
    return None


def _ddev_image():
    try:
        out = subprocess.run(["ddev", "--version"], capture_output=True, text=True, timeout=10).stdout
        version = re.search(r"v\d+\.\d+\.\d+", out).group(0)
    except (OSError, AttributeError, subprocess.TimeoutExpired):
        version = "latest"
    return f"ddev/ddev-webserver:{version}"


def _eval_js(path):
    """Runs the file with Node inside the DDEV web image (no Node needed on
    the host). The project folder is mounted read-only."""
    from . import ddev  # late import: ddev imports nodeproj, which imports this module

    root = path.parent
    rel = path.name
    if path.suffix == ".ts":
        node = f"node --experimental-strip-types -e {shlex.quote(_EVAL)} /app/{shlex.quote(rel)}"
    else:
        node = f"node -e {shlex.quote(_EVAL)} /app/{shlex.quote(rel)}"
    cmd = (f"docker run --rm --network none -v {shlex.quote(str(root))}:/app:ro -w /app "
           f"--entrypoint bash {_ddev_image()} -c {shlex.quote(node)}")
    proc = subprocess.run(ddev.shell_argv(cmd), capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise Pm2Error((proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout).strip() else "node failed")
    return json.loads(proc.stdout)


def load(path):
    """The ecosystem as a dict (cached by modification time)."""
    path = Path(path)
    key = (str(path), path.stat().st_mtime)
    if key in _cache:
        return _cache[key]
    if path.suffix in (".json", ".json5"):
        text = path.read_text()
        if path.suffix == ".json5":  # good enough for comments and trailing commas
            text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r",(\s*[}\]])", r"\1", text)
        data = json.loads(text)
    elif path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(path.read_text())
    else:
        data = _eval_js(path)
    data = data if isinstance(data, dict) else {"apps": data if isinstance(data, list) else []}
    _cache[key] = data
    return data


def summary(root):
    """{'file', 'apps': [...], 'deploy': {env: {...}}} without secrets, or None."""
    path = find(root)
    if not path:
        return None
    try:
        data = load(path)
    except (Pm2Error, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"file": path, "apps": [], "deploy": {}, "error": str(exc)}
    apps = []
    for a in data.get("apps") or []:
        if not isinstance(a, dict) or not a.get("script"):
            continue
        port = None
        for block in ("env", "env_development", "env_production"):
            env = a.get(block) or {}
            if isinstance(env, dict) and str(env.get("PORT", "")).isdigit():
                port = int(env["PORT"])
                break
        apps.append({
            "name": str(a.get("name") or Path(a["script"]).stem),
            "script": str(a["script"]),
            "args": a.get("args") if isinstance(a.get("args"), str) else " ".join(map(str, a.get("args") or [])),
            "interpreter": a.get("interpreter"),
            "port": port,
            "instances": a.get("instances", 1),
        })
    deploy = {}
    for env_name, d in (data.get("deploy") or {}).items():
        if not isinstance(d, dict):
            continue
        hosts = d.get("host")
        hosts = hosts if isinstance(hosts, list) else ([hosts] if hosts else [])
        deploy[env_name] = {
            "user": d.get("user", ""),
            "hosts": [str(h) for h in hosts],
            "port": d.get("port"),
            "ref": d.get("ref", ""),
            "repo": d.get("repo", ""),
            "path": d.get("path", ""),
            "post_deploy": d.get("post-deploy", ""),
            "key": d.get("key"),
        }
    return {"file": path, "apps": apps, "deploy": deploy}


def script_path_in(root, app):
    """The app's script relative to the project root when it is inside it
    (production `cwd` values such as /var/www/site/current are ignored)."""
    script = Path(app["script"])
    if script.is_absolute():
        return None
    candidate = (Path(root) / script).resolve()
    try:
        return candidate.relative_to(Path(root).resolve())
    except ValueError:
        return None


# ------------------------------------------------------------ deploy commands
def _pm2():
    # pm2 from npm inside the web container; the npm cache keeps it after the first run
    return "npx --yes pm2@latest"


def deploy_cmd(file, env, action=None):
    """pm2 deploy <file> <env> [setup|revert 1|…], run in the project folder in the container."""
    extra = f" {action}" if action else ""
    return f"cd /var/www/html && {_pm2()} deploy {shlex.quote(Path(file).name)} {shlex.quote(env)}{extra}"


def ssh_target(d):
    host = d["hosts"][0] if d["hosts"] else ""
    return f"{d['user']}@{host}" if d["user"] else host


def remote_cmd(d, command, tty=False):
    """Runs `command` on the deploy server with a login shell (so pm2 is on PATH)."""
    opts = ["-o", "StrictHostKeyChecking=accept-new"]
    if d.get("port"):
        opts += ["-p", str(d["port"])]
    if tty:
        opts.append("-t")
    remote = "bash -lc " + shlex.quote(command)
    return "ssh " + " ".join(opts) + " " + shlex.quote(ssh_target(d)) + " " + shlex.quote(remote)


def in_container(command):
    """Wraps a shell command so it runs in the project's web container."""
    return "ddev exec " + shlex.quote(command)


def in_container_tty(command):
    return "ddev exec -s web --raw -- bash -c " + shlex.quote(command)
