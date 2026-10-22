# Agent notes

Notes for coding agents working in this repository. User-facing documentation
lives in `README.md`; FlatPark packaging details are kept here.

## FlatPark packaging

This project is also packaged for [FlatPark](https://flatpark.org) as
`com.blackmagic.Resolve` and `com.blackmagic.ResolveStudio` (registry entries in
the [FlatPark repo](https://github.com/flatpark/flatpark)). That package does not
use the KDE + PySide BaseApp the `.flatpak` bundles rely on: it fetches a
self-contained tarball of this installer/launcher as Flatpak **extra-data** and
runs it inside `org.freedesktop.Platform`.

`build-bundle.sh` produces that tarball — a PyInstaller onedir tree carrying
Python and PySide6-Essentials — and the `bundle` CI job builds it on every run
and attaches `resolve-flatpak-<version>-x86_64.tar.gz` to each tagged release.
The installer selects free vs Studio from the `RESOLVE_STUDIO` environment
variable (or `--studio`), so one tarball serves both apps.

```sh
VERSION=$(git describe --tags) ./build-bundle.sh
# -> resolve-flatpak-<version>-x86_64.tar.gz (+ its sha256 and size)
```

### Keeping FlatPark up to date

Tagged releases notify FlatPark automatically: the `flatpark` job in
`.github/workflows/ci.yml` runs
[`flatpark/publish-action`](https://github.com/flatpark/publish-action) for both
app ids after the GitHub release is published. FlatPark then re-pins the new
`resolve-flatpak-<version>-x86_64.tar.gz` (URL, sha256, size), checks that it
unpacks, and opens, merges and publishes the bump itself — usually within
minutes. No token or secret is involved; FlatPark verifies the app id, the
repository and the published tag against public facts.

The twice-daily FlatPark check still runs as a backstop, and also catches a
release whose Linux asset is uploaded after the notification.

**When a PR is still needed.** The automation only bumps the pin and adds a
`<release>` entry. Open a PR (or issue) on
[flatpark/flatpark](https://github.com/flatpark/flatpark) when a release also
changes the package itself, for example:

- a new runtime library or tool the FlatPark wrapper/`apply_extra` must stage
  (e.g. the `libcrypt.so.1` change, which added `libcrypt/` to
  `LD_LIBRARY_PATH`);
- a renamed launcher, a changed archive layout, or a versioned top directory the
  unpack script relies on;
- changes to `finish-args`/permissions, the packaging level, the app id, or the
  bundle's payload format or file name.

In those cases the automatic bump can land while the app still does not launch.
If the new bundle fails FlatPark's unpack check, the previous version stays
available and the package is fixed by hand.
