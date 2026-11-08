#!/usr/bin/env bash
# Construye dist/panel-ddev_<versión>_all.deb a partir del código del repositorio.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import panel_ddev; print(panel_ddev.__version__)")
PKG=panel-ddev
BUILD="$ROOT/build/${PKG}_${VERSION}"
OUT="$ROOT/dist/${PKG}_${VERSION}_all.deb"

rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN" "$BUILD/usr/lib/$PKG" "$BUILD/usr/bin" \
         "$BUILD/usr/share/applications" "$BUILD/usr/share/icons/hicolor/scalable/apps" \
         "$BUILD/usr/share/doc/$PKG" "$ROOT/dist"

# Código
cp -r "$ROOT/panel_ddev" "$BUILD/usr/lib/$PKG/"
find "$BUILD/usr/lib/$PKG" -name '__pycache__' -prune -exec rm -rf {} +
install -m 755 "$ROOT/panel-ddev" "$BUILD/usr/lib/$PKG/panel-ddev"
install -m 644 "$ROOT/icono.svg" "$BUILD/usr/lib/$PKG/icono.svg"
ln -s "/usr/lib/$PKG/panel-ddev" "$BUILD/usr/bin/panel-ddev"

# Menú e icono
install -m 644 "$ROOT/icono.svg" "$BUILD/usr/share/icons/hicolor/scalable/apps/$PKG.svg"
cat > "$BUILD/usr/share/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Panel DDEV
GenericName=Entornos de desarrollo web
Comment=Crea, clona y gestiona tus proyectos DDEV
Exec=panel-ddev
Icon=$PKG
Terminal=false
Categories=Development;WebDevelopment;
Keywords=ddev;docker;php;laravel;wordpress;servidor;git;
StartupWMClass=panel-ddev
EOF

# Documentación
install -m 644 "$ROOT/LICENSE" "$BUILD/usr/share/doc/$PKG/copyright"
install -m 644 "$ROOT/TERMINOS.md" "$ROOT/README.md" "$ROOT/CHANGELOG.md" "$BUILD/usr/share/doc/$PKG/"

SIZE=$(du -sk "$BUILD/usr" | cut -f1)
cat > "$BUILD/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: devel
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-vte-2.91, python3-yaml, git
Recommends: ddev, gir1.2-ayatanaappindicator3-0.1, gir1.2-notify-0.7, gh
Maintainer: Jonathan Alberto Ayala Mendoza <17535726+jaayala03@users.noreply.github.com>
Homepage: https://github.com/jaayala03/panel-ddev
Description: Interfaz gráfica para gestionar proyectos DDEV
 Crea, clona y administra entornos de desarrollo web locales con DDEV
 (PHP, Node, Apache/nginx, MariaDB/MySQL/PostgreSQL) desde una ventana,
 con terminal integrada, herramientas de base de datos y cliente git.
EOF

fakeroot dpkg-deb --build --root-owner-group "$BUILD" "$OUT" >/dev/null
echo "$OUT"
