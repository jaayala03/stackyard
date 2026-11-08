"""Smoke tests for the bash scripts the app generates.

For every UI language: each generated script must pass `bash -n`, a simple
script must run to completion, and a failing one must report the error
message and a non-zero exit code. Run by build-deb.sh before packaging.
"""

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stackyard import ddev, i18n, nodeproj, pm2, resources, updates  # noqa: E402
from stackyard.terminal import wrapper_command  # noqa: E402

OPTIONS = {
    "name": "demo-app", "path": "/tmp/demo app's folder", "repo": "https://example.com/a b.git",
    "branch": "feature/x", "type": "laravel", "docroot": "public", "php": "8.4", "node": "24",
    "webserver": "apache-fpm", "db": "mariadb:11.8", "scaffold": True, "deps": True,
    "phpmyadmin": True, "launch": True,
}


def bash(script, *args):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
    try:
        return subprocess.run(["bash", *args, f.name], capture_output=True, text=True)
    finally:
        pathlib.Path(f.name).unlink()


def main():
    failures = []
    for lang in i18n.SUPPORTED:
        i18n.set_language(lang)
        scripts = {
            "new": ddev.script_create({**OPTIONS, "mode": "new"}),
            "clone": ddev.script_create({**OPTIONS, "mode": "clone"}),
            "existing": ddev.script_create({**OPTIONS, "mode": "existing", "type": ""}),
            "edit": ddev.script_edit("/tmp", OPTIONS, "mysql:8.0"),
            "simple": ddev.script_simple("/tmp", [("It's a step", "true")], "Done"),
        }
        for name, script in scripts.items():
            r = bash(script, "-n")
            if r.returncode:
                failures.append(f"[{lang}] {name}: bash -n failed: {r.stderr.strip()}")

        ok = bash(scripts["simple"])
        if ok.returncode or "✔" not in ok.stdout:
            failures.append(f"[{lang}] simple script did not complete: {ok.stdout}{ok.stderr}")

        bad = bash(ddev.script_simple("/tmp", [("Fails", "false")], "never"))
        expected = i18n._("Something went wrong. Check the messages above.")
        if bad.returncode == 0 or expected not in bad.stdout or "never" in bad.stdout:
            failures.append(f"[{lang}] failing script not reported correctly: {bad.stdout}{bad.stderr}")

    # the wrapper used by the terminal must keep the script's exit code and clean up
    for script, expected_code in (("exit 0", 0), ("exit 3", 3)):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(script)
        r = subprocess.run(["bash", "-c", wrapper_command(f.name)])
        if r.returncode != expected_code or pathlib.Path(f.name).exists():
            failures.append(f"wrapper: '{script}' exited {r.returncode} (expected {expected_code}) or left the file")

    # update installer script and version comparison
    release = {"version": "9.9.9", "url": "https://example.com", "deb": "https://example.com/stackyard_9.9.9_all.deb"}
    if bash(updates.install_script(release), "-n").returncode:
        failures.append("update install script: bash -n failed")
    if not (updates.is_newer("1.10.0", "1.9.9") and not updates.is_newer("1.2.0", "1.2.0")):
        failures.append("updates.is_newer is wrong")

    # Node monorepo: backend (Express) + frontend (Vite) are detected and configured
    for scheme in ("https", "http"):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "backend/src").mkdir(parents=True)
            (root / "frontend").mkdir()
            (root / "package.json").write_text('{"scripts": {"dev": "concurrently \\"cd backend && npm run dev\\""}}')
            (root / "backend/package.json").write_text('{"scripts": {"dev": "node src/server.js"}, "dependencies": {"express": "4", "bcrypt": "5"}}')
            (root / "backend/src/server.js").write_text("const PORT = process.env.PORT || 3001; const s = process.env.JWT_SECRET;")
            (root / "backend/.env.example").write_text("PORT=3001\nFRONTEND_URL=http://localhost:5173\nGEMINI_API_KEY=your-key-here\n")
            (root / "frontend/package.json").write_text('{"scripts": {"dev": "vite"}, "devDependencies": {"vite": "6"}}')
            (root / "frontend/vite.config.js").write_text("export default { server: { port: 5173 } }")
            (root / "frontend/.env.development").write_text("\ufeffVITE_API_URL=http://localhost:3001/api\n")
            plan = nodeproj.analyze(root, scheme)
            report = nodeproj.apply(plan, "demo", "local")
            env = (root / "backend/.env").read_text()
            front = (root / "frontend/.env.development.local").read_text()
            base = f"{scheme}://demo.local"
            checks = {
                "two services": [s["kind"] for s in plan["services"]] == ["server", "vite"],
                "frontend is primary": plan["services"][1]["public_port"] == (443 if scheme == "https" else 80),
                "backend keeps its port": plan["services"][0]["public_port"] == 3001,
                "no database": plan["database"] is None and "--omit-containers=db" in nodeproj.ddev_config_flags(plan),
                "env urls": f"FRONTEND_URL={base}\n" in env,
                "jwt generated": "JWT_SECRET=" in env,
                "api key reported": any("GEMINI_API_KEY" in line for line in report),
                "vite api url": f"VITE_API_URL={base}:3001/api" in front,
                "prepare script": bash(nodeproj.prepare_script(plan), "-n").returncode == 0,
                "hmr": (("wss" if scheme == "https" else "'ws'") in (root / ".ddev/vite.frontend.ddev.config.mjs").read_text()),
            }
            failures += [f"node [{scheme}]: {k}" for k, ok in checks.items() if not ok]

    # pm2 ecosystem (JSON and YAML; JS needs Docker, tested by hand): apps are merged with
    # the detected services and the deploy section is read without secrets
    for fname, content in (
        ("ecosystem.config.json", '{"apps": [{"name": "api", "script": "./backend/src/server.js", "env_production": {"PORT": 3005, "API_KEY": "s3cr3t"}},'
                                  ' {"name": "queue", "script": "./backend/worker.js"}],'
                                  ' "deploy": {"production": {"user": "deploy", "host": "example.com", "ref": "origin/main", "path": "/srv/app"}}}'),
        ("ecosystem.config.yml", "apps:\n  - name: api\n    script: ./backend/src/server.js\n    env_production: {PORT: 3005, API_KEY: s3cr3t}\n"
                                 "  - name: queue\n    script: ./backend/worker.js\ndeploy:\n  production: {user: deploy, host: example.com, ref: origin/main, path: /srv/app}\n"),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "backend/src").mkdir(parents=True)
            (root / "backend/package.json").write_text('{"scripts": {"dev": "node src/server.js"}, "dependencies": {"express": "4"}}')
            (root / "backend/src/server.js").write_text("const PORT = process.env.PORT || 3001;")
            (root / fname).write_text(content)
            info = pm2.summary(root)
            plan = nodeproj.analyze(root)
            services = {s["name"]: s for s in plan["services"]}
            checks = {
                "found": info and info["file"].name == fname,
                "apps": [a["name"] for a in info["apps"]] == ["api", "queue"],
                "no secret": "s3cr3t" not in repr(info),
                "deploy": pm2.ssh_target(info["deploy"]["production"]) == "deploy@example.com",
                "backend = pm2 api": services["backend"].get("pm2") == "api" and services["backend"]["port"] == 3005,
                "worker added": services.get("queue", {}).get("kind") == "worker",
                "worker not exposed": "name: queue\n    container_port" not in nodeproj.ddev_yaml(plan),
                "deploy cmd": bash(pm2.in_container(pm2.deploy_cmd(info["file"], "production")), "-n").returncode == 0,
            }
            failures += [f"pm2 [{fname}]: {k}" for k, ok in checks.items() if not ok]

    # idle tracker: quiet for 30 min -> idle; traffic or CPU resets the timer
    t = resources.IdleTracker()
    st = {"p": {"cpu": 0.1, "mem": 1, "web_cpu": 0.1, "web_rx": 100}}
    t.update(st, ["p"], now=0)
    checks = [t.idle_projects(30, now=1799) == [], t.idle_projects(30, now=1800) == ["p"]]
    st["p"]["web_rx"] = 200
    t.update(st, ["p"], now=1900)
    checks.append(t.idle_projects(30, now=1901) == [])
    t.update(st, [], now=2000)
    checks.append(t.last_active == {})
    if not all(checks):
        failures.append(f"idle tracker: {checks}")

    for f in failures:
        print(f)
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
