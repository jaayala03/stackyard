"""Resource usage of DDEV containers (docker stats) and idle detection used
to stop projects automatically."""

import json
import re
import subprocess
import time

from . import ddev

IDLE_OPTIONS = [("0", "Never"), ("30", "After 30 minutes idle"), ("60", "After 1 hour idle"), ("120", "After 2 hours idle")]
ACTIVE_CPU = 1.0  # % of web container CPU that counts as activity

_UNITS = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
          "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4}


def _bytes(text):
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text or "")
    if not m:
        return 0
    return int(float(m.group(1)) * _UNITS.get(m.group(2).lower(), 1))


def _run(command):
    proc = subprocess.run(ddev.shell_argv(command), capture_output=True, text=True, timeout=30)
    return proc.stdout if proc.returncode == 0 else ""


def sample():
    """{project: {"cpu": %, "mem": bytes, "web_cpu": %, "web_rx": bytes}} plus
    "__ddev__" for the shared router and ssh-agent."""
    owners = {}
    for line in _run("docker ps --format '{{.Names}}|{{.Label \"com.ddev.site-name\"}}|{{.Label \"com.docker.compose.service\"}}'").splitlines():
        name, site, service = (line.split("|") + ["", ""])[:3]
        if name.startswith("ddev-"):
            owners[name] = (site or "__ddev__", service)
    out = {}
    for line in _run("docker stats --no-stream --format '{{json .}}'").splitlines():
        try:
            st = json.loads(line)
        except ValueError:
            continue
        owner = owners.get(st.get("Name"))
        if not owner:
            continue
        site, service = owner
        cpu = float(st.get("CPUPerc", "0").rstrip("%") or 0)
        mem = _bytes(st.get("MemUsage", "").split("/")[0])
        agg = out.setdefault(site, {"cpu": 0.0, "mem": 0, "web_cpu": 0.0, "web_rx": 0})
        agg["cpu"] += cpu
        agg["mem"] += mem
        if service == "web":
            agg["web_cpu"] = cpu
            agg["web_rx"] = _bytes(st.get("NetIO", "").split("/")[0])
    return out


def human(n):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


class IdleTracker:
    """Remembers when each running project was last active."""

    def __init__(self):
        self.last_active = {}
        self.last_rx = {}

    def update(self, stats, running_names, now=None):
        now = time.monotonic() if now is None else now
        for name in running_names:
            st = stats.get(name)
            if st is None:
                continue
            rx_grew = st["web_rx"] > self.last_rx.get(name, st["web_rx"])
            if name not in self.last_active or st["web_cpu"] >= ACTIVE_CPU or rx_grew:
                self.last_active[name] = now
            self.last_rx[name] = st["web_rx"]
        for name in list(self.last_active):
            if name not in running_names:  # stopped: start counting again next time
                self.last_active.pop(name, None)
                self.last_rx.pop(name, None)

    def idle_projects(self, minutes, now=None):
        if minutes <= 0:
            return []
        now = time.monotonic() if now is None else now
        return [n for n, t in self.last_active.items() if now - t >= minutes * 60]

    def reset(self, name):
        self.last_active[name] = time.monotonic()
