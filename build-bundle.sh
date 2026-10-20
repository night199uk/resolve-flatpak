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

# Do not ship the build machine's libxkbcommon. Qt's xcb platform plugin
# compiles the X keymap with libxkbcommon-x11, which FlatPark's runtime
# supplies (1.13.x); the Ubuntu wheel/build machine's libxkbcommon (1.6) that
# PyInstaller collects is ABI-incompatible with it, and the first key press in
# any text field segfaults in the keymap parser. Dropping both copies makes the
# runtime provide a matched pair. (Same shadowing as the launcher's
# LD_LIBRARY_PATH_ORIG fix, but for the Qt GUI itself.)
rm -f "$build_root/dist/resolve-flatpak/_internal/libxkbcommon.so.0"*
rm -f "$build_root/dist/resolve-flatpak/_internal/libxkbcommon-x11.so.0"*

# Likewise use the runtime's fontconfig. The build machine's copy (Ubuntu 2.15,
# Fedora 2.17) predates the runtime's 2.18 configuration syntax (`xsi:nil`,
# `<const>`), so it logs a warning for every construct it does not understand
# while parsing /etc/fonts/conf.d. The runtime's libfontconfig parses its own
# configuration cleanly.
rm -f "$build_root/dist/resolve-flatpak/_internal/libfontconfig.so.1"*

# Build libcrypt.so.1 for Resolve. Its bundled libaprutil-1.so.0 binds crypt
# symbols versioned GLIBC_2.2.5; the FlatPark runtime ships libxcrypt as
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
mkdir -p "$build_root/dist/resolve-flatpak/libcrypt"
cp -a "$libxcrypt_root/stage/lib/libcrypt.so.1"* \
    "$build_root/dist/resolve-flatpak/libcrypt/"
[ -e "$build_root/dist/resolve-flatpak/libcrypt/libcrypt.so.1" ] \
    || { echo "libcrypt.so.1 missing after build" >&2; exit 1; }

echo ">> packing $out"
tar -C "$build_root/dist" -czf "$out" resolve-flatpak

echo ">> result"
sha256sum "$out"
stat -c 'size: %s' "$out"
