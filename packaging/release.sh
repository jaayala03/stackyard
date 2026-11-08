#!/usr/bin/env bash
# Publishes a GitHub release for the current version:
#   builds the .deb, tags v<version>, and uses the CHANGELOG section as notes.
# Requires a clean, pushed main branch and an authenticated GitHub CLI.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
VERSION=$(python3 -c "import stackyard; print(stackyard.__version__)")
TAG="v$VERSION"

[ -z "$(git status --porcelain)" ] || { echo "Working tree is not clean." >&2; exit 1; }
git fetch -q origin
[ "$(git rev-parse HEAD)" = "$(git rev-parse '@{u}')" ] || { echo "Push your commits first." >&2; exit 1; }
! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "$TAG already exists." >&2; exit 1; }

DEB=$(bash packaging/build-deb.sh)

NOTES=$(mktemp)
trap 'rm -f "$NOTES"' EXIT
{
  echo "## Install"
  echo
  echo '```bash'
  echo "curl -fsSL https://raw.githubusercontent.com/jaayala03/stackyard/main/install.sh | bash"
  echo '```'
  echo
  echo "Already have Docker and DDEV? Download the \`.deb\` below and run \`sudo apt install ./$(basename "$DEB")\`."
  echo
  # The CHANGELOG section of this version, without its heading
  awk -v v="$VERSION" '
    $0 ~ "^## \\[" v "\\]" { on = 1; next }
    on && /^## \[/ { exit }
    on { print }
  ' CHANGELOG.md | sed 's/^### /## /'
  echo
  echo "Full changelog: [CHANGELOG.md](https://github.com/jaayala03/stackyard/blob/main/CHANGELOG.md) · [Terms](https://github.com/jaayala03/stackyard/blob/main/TERMS.md)"
} > "$NOTES"

git tag -a "$TAG" -m "Stackyard $VERSION"
git push -q origin "$TAG"
gh release create "$TAG" "$DEB" --title "Stackyard $VERSION" --notes-file "$NOTES" --latest
