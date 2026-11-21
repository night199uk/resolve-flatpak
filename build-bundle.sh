#!/usr/bin/env bash
#
# Build the FlatPark extra-data bundle.
#
# FlatPark packages this project as a Flatpak that runs *this* installer rather
# than the Blackmagic payload: the package fetches this tarball as Flatpak
# extra-data at install time and runs the installer/launcher inside
# org.gnome.Platform//51. The tarball carries only the installer Python sources.
# Python, PyGObject, GTK4, requests and libxcrypt come from the runtime and the
# FlatPark manifest; unsquashfs comes from FlatPark's appimage-tools stack.
#
# Output: resolve-flatpak-<version>-x86_64.tar.gz (a single version-stamped top
# directory containing installer/), plus its sha256 and size.
#
# Usage:
#   ./build-bundle.sh            # version from `git describe`, or 0.0.0
#   VERSION=0.0.11 ./build-bundle.sh
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
stage="$build_root/stage/resolve-flatpak"
mkdir -p "$stage/installer"

echo ">> staging installer sources"
install -m644 installer/*.py "$stage/installer/"

echo ">> packing $out"
tar -C "$build_root/stage" -czf "$out" resolve-flatpak

echo ">> result"
sha256sum "$out"
stat -c 'size: %s' "$out"
