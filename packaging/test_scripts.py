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
from panel_ddev import ddev, i18n  # noqa: E402
from panel_ddev.terminal import wrapper_command  # noqa: E402

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

    for f in failures:
        print(f)
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
