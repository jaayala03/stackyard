#!/usr/bin/env bash
# Installs a built .deb on a clean Ubuntu (run as root in a container) and
# starts the app under a virtual display for a few seconds.
# Usage: smoke-test.sh path/to/stackyard_X_all.deb
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
DEB=$(realpath "$1")
apt-get update -qq
apt-get install -y -qq "$DEB" xvfb dbus-x11 >/dev/null
echo "installed: $(dpkg-query -W -f='${Package} ${Version}' stackyard)"
command -v stackyard
test -f /usr/share/applications/stackyard.desktop
test -f /usr/share/icons/hicolor/scalable/apps/stackyard.svg

useradd -m tester
set +e
su - tester -c 'timeout 10 xvfb-run -a dbus-launch stackyard' > /tmp/app.log 2>&1
code=$?
set -e
if grep -q "Traceback" /tmp/app.log; then
  cat /tmp/app.log
  echo "The app crashed on start." >&2
  exit 1
fi
# 124 = still running when the timeout stopped it, which is what we want
if [ "$code" != 124 ]; then
  cat /tmp/app.log
  echo "The app exited early with code $code." >&2
  exit 1
fi
echo "The app started and kept running."
