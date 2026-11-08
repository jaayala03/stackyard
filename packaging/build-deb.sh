#!/usr/bin/env bash
# Builds dist/stackyard_<version>_all.deb from the repository sources.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import stackyard; print(stackyard.__version__)")
PKG=stackyard
BUILD="$ROOT/build/${PKG}_${VERSION}"
OUT="$ROOT/dist/${PKG}_${VERSION}_all.deb"

python3 "$ROOT/packaging/check_translations.py" >/dev/null
python3 "$ROOT/packaging/test_scripts.py" >/dev/null

rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN" "$BUILD/usr/lib/$PKG/bin" "$BUILD/usr/bin" \
         "$BUILD/usr/share/applications" "$BUILD/usr/share/icons/hicolor/scalable/apps" \
         "$BUILD/usr/share/doc/$PKG" "$ROOT/dist"

# Application code
cp -r "$ROOT/stackyard" "$BUILD/usr/lib/$PKG/"
find "$BUILD/usr/lib/$PKG" -name '__pycache__' -prune -exec rm -rf {} +
install -m 755 "$ROOT/bin/stackyard" "$BUILD/usr/lib/$PKG/bin/stackyard"
install -m 644 "$ROOT/icon.svg" "$BUILD/usr/lib/$PKG/icon.svg"
ln -s "/usr/lib/$PKG/bin/stackyard" "$BUILD/usr/bin/stackyard"

# Menu entry and icon
install -m 644 "$ROOT/icon.svg" "$BUILD/usr/share/icons/hicolor/scalable/apps/$PKG.svg"
cat > "$BUILD/usr/share/applications/$PKG.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Stackyard
GenericName=Local web development environments
GenericName[es]=Entornos de desarrollo web
Comment=Create, clone and manage your DDEV projects
Comment[es]=Crea, clona y gestiona tus proyectos DDEV
Exec=stackyard
Icon=$PKG
Terminal=false
Categories=Development;WebDevelopment;
Keywords=ddev;docker;php;laravel;wordpress;server;git;
StartupWMClass=stackyard
DESKTOP

# Documentation
install -m 644 "$ROOT/LICENSE" "$BUILD/usr/share/doc/$PKG/copyright"
install -m 644 "$ROOT/README.md" "$ROOT/TERMS.md" "$ROOT/CHANGELOG.md" "$BUILD/usr/share/doc/$PKG/"

SIZE=$(du -sk "$BUILD/usr" | cut -f1)
cat > "$BUILD/DEBIAN/control" <<CONTROL
Package: $PKG
Conflicts: panel-ddev
Replaces: panel-ddev
Provides: panel-ddev
Version: $VERSION
Section: devel
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-vte-2.91, gir1.2-gtksource-4, python3-yaml, git
Recommends: ddev, gir1.2-ayatanaappindicator3-0.1, gir1.2-notify-0.7, gh
Maintainer: Jonathan Alberto Ayala Mendoza <17535726+jaayala03@users.noreply.github.com>
Homepage: https://github.com/jaayala03/stackyard
Description: Desktop app to manage DDEV projects
 Create, clone and manage local web development environments with DDEV
 (PHP, Node, Apache/nginx, MariaDB/MySQL/PostgreSQL) from one window,
 with an embedded terminal, database tools, a git client and a tray icon.
 Available in English and Spanish.
CONTROL

fakeroot dpkg-deb --build --root-owner-group "$BUILD" "$OUT" >/dev/null
echo "$OUT"
