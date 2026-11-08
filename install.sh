#!/usr/bin/env bash
# Installs Stackyard and everything it needs:
#   Docker (official repository), DDEV, mkcert (local HTTPS) and the app itself.
# Tested on Linux Mint 22 / Ubuntu 24.04. Works on Ubuntu and Debian derivatives.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jaayala03/stackyard/main/install.sh | bash
# or, from a copy of the repository:
#   ./install.sh            (installs the latest published release)
#   ./install.sh --local    (builds and installs the package from this source tree)
set -euo pipefail

REPO="jaayala03/stackyard"

# Messages follow the system language (Spanish or English).
case "${LANGUAGE:-${LC_ALL:-${LANG:-en}}}" in es*) ES=1 ;; *) ES=0 ;; esac
t()    { if [ "$ES" = 1 ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$(t "$1" "$2")"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$(t "$1" "$2")"; }
fail() { printf '\033[1;31m✘ %s\033[0m\n' "$(t "$1" "$2")" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "Run it as your normal user (it asks for sudo when needed)." \
                             "Ejecútalo con tu usuario normal (pedirá sudo cuando haga falta)."
command -v apt-get >/dev/null || fail "This installer needs a Debian/Ubuntu based distribution (apt)." \
                                      "Este instalador necesita una distribución basada en Debian/Ubuntu (apt)."

. /etc/os-release
DISTRO=ubuntu; CODENAME="${UBUNTU_CODENAME:-}"
if [ -z "$CODENAME" ]; then DISTRO=debian; CODENAME="${VERSION_CODENAME:-}"; fi
[ -n "$CODENAME" ] || fail "Could not detect your system version." "No se pudo detectar la versión de tu sistema."
ARCH=$(dpkg --print-architecture)

step "Base packages" "Paquetes base"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl gnupg git libnss3-tools \
  python3 python3-gi python3-yaml gir1.2-gtk-3.0 gir1.2-vte-2.91 gir1.2-gtksource-4 \
  gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 >/dev/null
ok "Done" "Listo"

sudo install -m 0755 -d /etc/apt/keyrings

if ! command -v docker >/dev/null; then
  step "Installing Docker" "Instalando Docker"
  sudo curl -fsSL "https://download.docker.com/linux/$DISTRO/gpg" -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DISTRO $CODENAME stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  ok "Docker installed" "Docker instalado"
else
  ok "Docker was already installed" "Docker ya estaba instalado"
fi
sudo systemctl enable --now docker >/dev/null 2>&1 || true
NEEDS_RELOGIN=0
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
  NEEDS_RELOGIN=1
fi

if ! command -v ddev >/dev/null; then
  step "Installing DDEV" "Instalando DDEV"
  curl -fsSL https://pkg.ddev.com/apt/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/ddev.gpg >/dev/null
  echo "deb [signed-by=/etc/apt/keyrings/ddev.gpg] https://pkg.ddev.com/apt/ * *" \
    | sudo tee /etc/apt/sources.list.d/ddev.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq ddev >/dev/null
  ok "DDEV installed" "DDEV instalado"
else
  ok "DDEV was already installed" "DDEV ya estaba instalado"
fi

step "Local HTTPS certificates (mkcert)" "Certificados HTTPS locales (mkcert)"
mkcert -install

step "Installing Stackyard" "Instalando Stackyard"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ "${1:-}" = "--local" ]; then
  DIR=$(cd "$(dirname "$0")" && pwd)
  DEB=$(bash "$DIR/packaging/build-deb.sh")
elif command -v gh >/dev/null && gh auth status >/dev/null 2>&1 \
     && gh release download --repo "$REPO" --pattern '*_all.deb' --dir "$TMP" 2>/dev/null; then
  DEB=$(ls "$TMP"/*_all.deb | head -1)
else
  URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
        | grep -o '"browser_download_url": *"[^"]*_all\.deb"' | head -1 | cut -d'"' -f4) \
    || true
  [ -n "${URL:-}" ] || fail "No .deb found in https://github.com/$REPO/releases" \
                            "No se encontró ningún .deb publicado en https://github.com/$REPO/releases"
  DEB="$TMP/$(basename "$URL")"
  curl -fsSL "$URL" -o "$DEB"
fi
sudo apt-get install -y -qq "$DEB" >/dev/null
VERSION=$(dpkg-query -W -f='${Version}' stackyard)
ok "Stackyard $VERSION installed" "Stackyard $VERSION instalado"

echo
ok "All set. Open “Stackyard” from the applications menu." "Todo listo. Abre «Stackyard» desde el menú de aplicaciones."
if [ "$NEEDS_RELOGIN" = 1 ]; then
  printf '\033[1;33m! %s\033[0m\n' "$(t "Log out and back in to use Docker without sudo." "Cierra sesión y vuelve a entrar para usar Docker sin sudo.")"
fi
printf '  %s\n' "$(t "Restart your browser so it trusts the local HTTPS certificates." "Reinicia el navegador para que acepte los certificados HTTPS locales.")"
