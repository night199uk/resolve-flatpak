#!/usr/bin/env bash
#
# Build the FlatPark extra-data bundle.
#
# FlatPark packages this project as a Flatpak that runs *this* installer rather
# than the Blackmagic payload: the package fetches this tarball as Flatpak
# extra-data at install time and runs the installer/launcher inside
# org.freedesktop.Platform. So the tarball has to be self-contained — it carries
# Python and PySide6, because nothing Python or Qt comes from the freedesktop
# runtime. The one tool it does not carry is unsquashfs, which the installer uses
# to unpack the DaVinci Resolve download; FlatPark supplies that from its
# appimage-tools stack.
#
# Output: resolve-flatpak-<version>-x86_64.tar.gz (a PyInstaller onedir tree with
# a single version-stamped top directory), plus its sha256 and size.
#
# Usage:
#   ./build-bundle.sh            # version from `git describe`, or 0.0.0
#   VERSION=0.0.4 ./build-bundle.sh
#   PYTHON=python3.12 ./build-bundle.sh
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

# On a tag push use the tag; otherwise derive from git (a PR ref like
# "123/merge" must not leak into the filename, so GITHUB_REF_NAME is only used
# for tags).
if [ -z "${VERSION:-}" ] && [ "${GITHUB_REF_TYPE:-}" = "tag" ] && [ -n "${GITHUB_REF_NAME:-}" ]; then
    VERSION="$GITHUB_REF_NAME"
fi
version="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo 0.0.0)}"
version="${version#v}"
out="resolve-flatpak-${version}-x86_64.tar.gz"

build_root="${BUILD_ROOT:-$here/.bundle-build}"
rm -rf "$build_root"
mkdir -p "$build_root"

python="${PYTHON:-python3}"
command -v "$python" >/dev/null 2>&1 || { echo "missing interpreter: $python" >&2; exit 1; }

echo ">> creating build venv ($python)"
"$python" -m venv "$build_root/venv"
"$build_root/venv/bin/python" -m pip install --quiet --upgrade pip wheel

echo ">> installing bundle requirements"
"$build_root/venv/bin/python" -m pip install --quiet -r requirements-bundle.txt

echo ">> running PyInstaller"
"$build_root/venv/bin/pyinstaller" \
    --noconfirm --clean --log-level WARN \
    --onedir --name resolve-flatpak \
    --paths installer \
    --collect-all PySide6 \
    --distpath "$build_root/dist" \
    --workpath "$build_root/pyinstaller-build" \
    --specpath "$build_root" \
    installer/main.py

[ -x "$build_root/dist/resolve-flatpak/resolve-flatpak" ] \
    || { echo "pyinstaller did not produce the launcher" >&2; exit 1; }

echo ">> packing $out"
tar -C "$build_root/dist" -czf "$out" resolve-flatpak

echo ">> result"
sha256sum "$out"
stat -c 'size: %s' "$out"
