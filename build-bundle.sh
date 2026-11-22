#!/usr/bin/env bash
#
# Build the FlatPark extra-data bundle.
#
# FlatPark packages this project as a Flatpak that runs *this* installer rather
# than the Blackmagic payload: the package fetches this tarball as Flatpak
# extra-data at install time and runs the installer/launcher inside
# org.gnome.Platform//51. The tarball carries the installer Python sources, the
# vendored Python dependencies (requests and friends) and the glibc-ABI
# libcrypt.so.1, so FlatPark does not build app-specific packages into its ref.
# Python, PyGObject and GTK4 come from the runtime; unsquashfs comes from
# FlatPark's appimage-tools stack.
#
# Output: resolve-flatpak-<version>-x86_64.tar.gz (a single version-stamped top
# directory containing installer/, vendor/ and libcrypt/), plus its sha256 and
# size.
#
# Usage:
#   ./build-bundle.sh            # version from `git describe`, or 0.0.0
#   VERSION=0.0.12 ./build-bundle.sh
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

command -v python3 >/dev/null 2>&1 || { echo "missing python3" >&2; exit 1; }

echo ">> staging installer sources"
install -m644 installer/*.py "$stage/installer/"

# Vendor requests and its pure-Python dependencies. FlatPark's review rules do
# not allow app-specific packages to be built into the app ref, so they ship in
# the extra-data tarball instead and the wrapper puts vendor/ on PYTHONPATH.
echo ">> vendoring requests"
python3 -m pip install --quiet --no-compile --no-deps --require-hashes \
    --target "$stage/vendor" -r requirements-bundle.txt
[ -d "$stage/vendor/requests" ] || { echo "requests missing after vendoring" >&2; exit 1; }
# The target install also drops console scripts and package tests, which are
# not used at runtime; keep the tarball limited to importable modules.
rm -rf "$stage/vendor/bin"
find "$stage/vendor" -type d -name tests -prune -exec rm -rf {} +

# Build libcrypt.so.1 for Resolve. Its bundled libaprutil-1.so.0 binds crypt
# symbols versioned GLIBC_2.2.5; org.gnome.Platform ships libxcrypt as
# libcrypt.so.2, which defines XCRYPT_* but not GLIBC_2.2.5. Build libxcrypt with
# the obsolete glibc API (the same recipe the .flatpak manifests use) and ship
# the result beside the installer. The FlatPark wrapper puts libcrypt/ on
# Resolve's LD_LIBRARY_PATH.
LIBCRYPT_VERSION=4.5.2
LIBCRYPT_SHA256=71513a31c01a428bccd5367a32fd95f115d6dac50fb5b60c779d5c7942aec071
libxcrypt_root="$build_root/libxcrypt"
rm -rf "$libxcrypt_root"
mkdir -p "$libxcrypt_root"
echo ">> building libxcrypt $LIBCRYPT_VERSION (glibc-ABI libcrypt.so.1)"
curl -fsSL -o "$libxcrypt_root/libxcrypt.tar.xz" \
    "https://github.com/besser82/libxcrypt/releases/download/v$LIBCRYPT_VERSION/libxcrypt-$LIBCRYPT_VERSION.tar.xz"
echo "$LIBCRYPT_SHA256  $libxcrypt_root/libxcrypt.tar.xz" | sha256sum -c -
tar -C "$libxcrypt_root" -xf "$libxcrypt_root/libxcrypt.tar.xz"
(
    cd "$libxcrypt_root/libxcrypt-$LIBCRYPT_VERSION"
    CFLAGS="${CFLAGS:-} -Wno-error=discarded-qualifiers" \
        ./configure --prefix="$libxcrypt_root/stage" \
                    --enable-obsolete-api=glibc --disable-static
    make -j"$(nproc)"
    make install
)
mkdir -p "$stage/libcrypt"
cp -a "$libxcrypt_root/stage/lib/libcrypt.so.1"* "$stage/libcrypt/"
[ -e "$stage/libcrypt/libcrypt.so.1" ] \
    || { echo "libcrypt.so.1 missing after build" >&2; exit 1; }

echo ">> packing $out"
tar -C "$build_root/stage" -czf "$out" resolve-flatpak

echo ">> result"
sha256sum "$out"
stat -c 'size: %s' "$out"
