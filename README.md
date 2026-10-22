# MAJOR UPDATE:
I have completely rewritten this Flatpak support with a little help from
Claude to use a Qt-based meta-installer style approach similar to Steam
or Discord. I had initially hoped to use Flatpak's extra-data approach,
however bugs in Flatpak's implementation of extra-data related to very
large downloads (>8GB) pushed me away from this.

I may not have carried over all fixes, but this approach should be much
more strategic and allow distribution of this package via e.g. Flathub
and Flatpak, opening it up to more users.

Contributions are welcome and apologies if any previous contributions
were lost in the migration.

resolve-flatpak
===============

This Flatpak installs DaVinci Resolve using Flatpak. 

Technically it is a Qt-based installer that installs DaVinci Resolve
from the Blackmagic website on-demand.  It manages the installation,
checks for updates on run, etc. The Flatpak itself contains no Blackmagic
binaries or copyright material; and thus can be distributed on Flathub,
Flatpark etc. It provides the illusion of installing Resolve from Flatpak
and makes installation simpler for users running - e.g. Silverblue and
other atomic distributions, or anyone who operates Flatpak-first.

The Flatpak installation is performed in the Flatpak run directory; e.g.
```
/home/<user>/.var/app/com.blackmagic.Resolve/data
```
Thus, each user will manage their own Resolve installation.

Usage
-----

1. **Download the latest davinci-resolve.flatpak or davinci-resolve-studio.flatpak from the releases page.**
2. **Install**
3. **Run DaVinci Resolve [or Studio].**
4. **The installer will prompt you to install the latest version of DaVinci Resolve [or Studio].**
5. **If you need udev rules for USB keys or other Blackmagic USB devices:**
This must be done *after* the real DaVinci Resolve has been installed and first run.
```
flatpak run com.blackmagic.Resolve --print-udev-rules | sudo sh
```
or
```
flatpak run com.blackmagic.ResolveStudio --print-udev-rules | sudo sh
```

Plugins
-------
I have not yet updated the ffmpeg plugin to support this latest packaging mechanism.

Advanced Stuff, Tools, and Compiling
------------------------------------

## Re-building the Flatpaks

1. Rebuild the top-level packages, and export to distributable single file installers.
NOTE: this does not package the resolve binaries; only the installer. The
installer will always obtain the Resolve binaries on run.

#### 
```
git clone https://github.com/night199uk/resolve-flatpak.git --recursive

# This line updates the static resources like icons, desktop files, etc
# that are packaged in the actual Flatpak.
installer/main.py --export-flatpak-resources .

flatpak-builder --install-deps-from=flathub --force-clean --repo=.repo .build-dir com.blackmagic.Resolve.yaml
flatpak build-bundle .repo DaVinciResolve.flatpak com.blackmagic.Resolve --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo

flatpak-builder --install-deps-from=flathub --force-clean --repo=.repo .build-dir com.blackmagic.ResolveStudio.yaml
flatpak build-bundle .repo DaVinciResolveStudio.flatpak com.blackmagic.ResolveStudio --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo
```

## Finding download IDs to install specific versions of Resolve

#### If you already have this Flatpak installed
This will list only the downloads for the version you have installed (Free or Studio):
```
flatpak run com.blackmagic.Resolve --list-downloads
```
or
```
flatpak run com.blackmagic.ResolveStudio --list-downloads
```

#### Directly from this repo:

```
git clone https://github.com/night199uk/resolve-flatpak.git --recursive
cd resolve-flatpak
installer/main.py --list-downloads [--studio]
```

## Installing a specific version of Resolve (using a download ID)

Install this Flatpak but do not install Resolve itself.
Or - if you already installed Resolve and want to go back to an older version:

```
rm -rf ~/.var/app/com.blackmagic.com/
```

Get a download ID for the version you want to install (see above).

Now:
```
flatpak run com.blackmagic.Resolve --download_id <download_id>
```

This will install and run the version you want.

## FlatPark

This project is also packaged for [FlatPark](https://flatpark.org) as
`com.blackmagic.Resolve` and `com.blackmagic.ResolveStudio` (registry entries in
the [FlatPark repo](https://github.com/flatpark/flatpark)). That package does not
use the KDE + PySide BaseApp these `.flatpak` bundles rely on: it fetches a
self-contained tarball of this installer/launcher as Flatpak **extra-data** and
runs it inside `org.freedesktop.Platform`.

| DaVinci Resolve | DaVinci Resolve Studio |
| --- | --- |
| [![Get it on FlatPark](https://flatpark.org/badges/get-it-on-flatpark.svg)](https://flatpark.org/apps/com.blackmagic.Resolve/) | [![Get it on FlatPark](https://flatpark.org/badges/get-it-on-flatpark.svg)](https://flatpark.org/apps/com.blackmagic.ResolveStudio/) |

```sh
flatpak remote-add --if-not-exists --user flatpark https://dl.flatpark.org/flatpark.flatpakrepo
flatpak install --user flatpark com.blackmagic.Resolve        # or com.blackmagic.ResolveStudio
```

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

## Support

If this is useful to you, you can buy me a coffee:

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/night199uk)

## Licensing
The icon in logo.png is licensed under the Creative [Commons Attribution-Share Alike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/deed.en) and fetched from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:DaVinci_Resolve_Studio.png). It was only cropped afterwards.

## Related

- [Flathub forum : DaVinci Resolve Feature Requests](https://discourse.flathub.org/t/davinci-resolve-flatpak-request/842)
- [blackmagicdesign forum : DaVinci Resolve Flatpak request](https://forum.blackmagicdesign.com/viewtopic.php?f=33&t=186259)

