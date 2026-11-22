# Agent notes

Notes for coding agents working in this repository. User-facing documentation
lives in `README.md`; FlatPark packaging details are kept here.

## FlatPark packaging

This project is also packaged for [FlatPark](https://flatpark.org) as
`com.blackmagic.Resolve` and `com.blackmagic.ResolveStudio` (registry entries in
the [FlatPark repo](https://github.com/flatpark/flatpark)). The `.flatpak`
bundles use `org.gnome.Platform` 51; the FlatPark packages must use the same
runtime, because the GTK4 installer needs the runtime's Python 3.14 with
PyGObject/GTK4. Do not move FlatPark back to `org.freedesktop.Platform` 26.08
(no PyGObject/GTK4) or reintroduce PySide6.

`build-bundle.sh` produces the extra-data tarball consumed by FlatPark. It is
not a PyInstaller tree; it contains:

- `installer/` — the installer/launcher Python sources;
- `vendor/` — `requests` and its pure-Python dependencies, installed from the
  hashed pins in `requirements-bundle.txt`;
- `libcrypt/libcrypt.so.1` — built with `--enable-obsolete-api=glibc` for
  Resolve's bundled libaprutil.

The FlatPark wrapper puts `vendor/` on `PYTHONPATH` and `libcrypt/` on
`LD_LIBRARY_PATH`, and `apply_extra.sh` checks `installer/main.py`,
`libcrypt/libcrypt.so.1` and `vendor/requests` after unpacking. The installer
selects free vs Studio from `RESOLVE_STUDIO` (or `--studio`), so one tarball
serves both apps.

### FlatPark review rules

FlatPark rejects app-specific build modules in the app ref. Only shared
`flatpark/prebuilt` stacks may be archive modules; the app payload and every
single-app dependency (including Python packages and libcrypt) must arrive as
extra-data. This caused two rejected FlatPark PRs: do **not** add `libxcrypt`
from git or `python3-requests`/pip wheels to the FlatPark manifest. Put them in
this project's release tarball instead. See FlatPark's
[Phase 3 review rules](https://github.com/flatpark/flatpark/blob/main/docs/reviewers/review-runbook.md#phase-3--descriptor--manifest-static-review).

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
  (the v0.0.12 tarball added `vendor/` and `libcrypt/`, so the wrapper sets
  `PYTHONPATH`/`LD_LIBRARY_PATH`);
- a runtime/base switch (e.g. the GTK4/GNOME 51 move, which the FlatPark
  manifest had to follow);
- a renamed launcher, a changed archive layout, or a versioned top directory the
  unpack script relies on;
- changes to `finish-args`/permissions, the packaging level, the app id, or the
  bundle's payload format or file name.

In those cases the automatic bump can land while the app still does not launch.
If the new bundle fails FlatPark's unpack check, the previous version stays
available and the package is fixed by hand.
