#!/usr/bin/env bash
# Instalador de Panel DDEV y todo lo que necesita:
#   Docker (repositorio oficial), DDEV, mkcert (HTTPS local) y la propia app.
# Probado en Linux Mint 22 / Ubuntu 24.04. Funciona en derivados de Ubuntu y Debian.
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/jaayala03/panel-ddev/main/instalar.sh | bash
# o, desde una copia del repositorio:
#   ./instalar.sh            (instala la última versión publicada)
#   ./instalar.sh --local    (construye e instala el paquete desde este código)
set -euo pipefail

REPO="jaayala03/panel-ddev"
paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
fallo(){ printf '\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fallo "Ejecútalo con tu usuario normal (pedirá sudo cuando haga falta)."
command -v apt-get >/dev/null || fallo "Este instalador necesita una distribución basada en Debian/Ubuntu (apt)."

. /etc/os-release
DISTRO=ubuntu; CODENAME="${UBUNTU_CODENAME:-}"
if [ -z "$CODENAME" ]; then DISTRO=debian; CODENAME="${VERSION_CODENAME:-}"; fi
[ -n "$CODENAME" ] || fallo "No se pudo detectar la versión de tu sistema."
ARCH=$(dpkg --print-architecture)

paso "Paquetes base"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl gnupg git libnss3-tools \
  python3 python3-gi python3-yaml gir1.2-gtk-3.0 gir1.2-vte-2.91 \
  gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7 >/dev/null
ok "Listo"

sudo install -m 0755 -d /etc/apt/keyrings

if ! command -v docker >/dev/null; then
  paso "Instalando Docker"
  sudo curl -fsSL "https://download.docker.com/linux/$DISTRO/gpg" -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DISTRO $CODENAME stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  ok "Docker instalado"
else
  ok "Docker ya estaba instalado"
fi
sudo systemctl enable --now docker >/dev/null 2>&1 || true
NEEDS_RELOGIN=0
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
  NEEDS_RELOGIN=1
fi

if ! command -v ddev >/dev/null; then
  paso "Instalando DDEV"
  curl -fsSL https://pkg.ddev.com/apt/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/ddev.gpg >/dev/null
  echo "deb [signed-by=/etc/apt/keyrings/ddev.gpg] https://pkg.ddev.com/apt/ * *" \
    | sudo tee /etc/apt/sources.list.d/ddev.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq ddev >/dev/null
  ok "DDEV instalado"
else
  ok "DDEV ya estaba instalado"
fi

paso "Certificados HTTPS locales (mkcert)"
mkcert -install

paso "Instalando Panel DDEV"
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
  [ -n "${URL:-}" ] || fallo "No se encontró ningún .deb publicado en https://github.com/$REPO/releases"
  DEB="$TMP/$(basename "$URL")"
  curl -fsSL "$URL" -o "$DEB"
fi
sudo apt-get install -y -qq "$DEB" >/dev/null
ok "Panel DDEV $(dpkg-query -W -f='${Version}' panel-ddev) instalado"

echo
ok "Todo listo. Abre «Panel DDEV» desde el menú de aplicaciones."
if [ "$NEEDS_RELOGIN" = 1 ]; then
  printf '\033[1;33m! Cierra sesión y vuelve a entrar para usar Docker sin sudo.\033[0m\n'
fi
printf '  Reinicia el navegador para que acepte los certificados HTTPS locales.\n'
