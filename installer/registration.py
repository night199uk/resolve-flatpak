"""Where the DaVinci Resolve installer comes from: the user's own Blackmagic
registration, or an installer the user already downloaded.

Blackmagic asks for a name, e-mail, phone and address before every Linux
download. These are the user's own details, typed in once and sent only to
blackmagicdesign.com; they are kept in the app's data directory so updates do
not ask again. A user who would rather not share them downloads the installer
from Blackmagic's site in a browser and picks the file here instead.
"""

import json
import re
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk

import config

DOWNLOAD_PAGE = "https://www.blackmagicdesign.com/support/family/davinci-resolve-and-fusion"

# (key in Blackmagic's form, label, required, example shown after the field)
FIELDS = [
    ("firstname", "First name", True, "Flatpak"),
    ("lastname", "Last name", True, "Builder"),
    ("email", "E-mail", True, None),
    ("phone", "Phone", True, "202-555-0194"),
    ("country", "Country code", True, "us"),
    ("state", "State / province", False, "New York"),
    ("city", "City", True, "FPK"),
    ("street", "Street address", True, "Bowery 146"),
]


def _path(prefix):
    return Path(prefix) / "share" / "blackmagic-registration.json"


def load(prefix=None):
    """Return the saved registration dict, or None."""
    path = _path(prefix or config.INSTALL_PREFIX)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def complete(data):
    """True if `data` has every required registration field."""
    if not isinstance(data, dict):
        return False
    for key, _label, required, _example in FIELDS:
        if required and not str(data.get(key, "")).strip():
            return False
    return True


def save(data, prefix=None):
    path = _path(prefix or config.INSTALL_PREFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    path.chmod(0o600)


def forget(prefix=None):
    _path(prefix or config.INSTALL_PREFIX).unlink(missing_ok=True)


def version_from_filename(name):
    """'DaVinci_Resolve_Studio_20.3.3_Linux.zip' -> version dict, or None."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", name)
    if not match:
        return None
    return {
        "major": int(match.group(1)),
        "minor": int(match.group(2)),
        "patch": int(match.group(3) or 0),
        "build": 0,
        "beta": -1,
    }


class SourceDialog(Gtk.Window):
    """Ask how to get the installer.

    After ``exec()`` read ``.choice``: ``("download", registration_dict)`` or
    ``("file", Path)``. ``exec()`` runs its own GLib main loop, matching the
    modal, blocking behaviour of the old QDialog.
    """

    def __init__(self, parent=None):
        super().__init__()
        self.choice = None
        self._loop = None
        self.set_title(f"Install {config.APP_NAME}")
        self.set_default_size(560, -1)
        self.set_modal(True)
        if parent is not None:
            self.set_transient_for(parent)

        self.download_radio = Gtk.CheckButton(
            label="Download it from Blackmagic Design"
        )
        self.file_radio = Gtk.CheckButton(
            label="Use an installer I already downloaded"
        )
        self.file_radio.set_group(self.download_radio)

        # -- download: Blackmagic's registration form ----------------------
        intro = Gtk.Label(
            label=(
                "Blackmagic Design asks for these details before each download. "
                "They are sent only to blackmagicdesign.com, exactly as on its "
                "download page."
            ),
            xalign=0.0,
            wrap=True,
        )
        intro.set_css_classes(["dim-label"])

        saved = load() or {}
        self.inputs = {}
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        for row, (key, label, required, example) in enumerate(FIELDS):
            caption = Gtk.Label(label=label, xalign=0.0)
            grid.attach(caption, 0, row, 1, 1)

            edit = Gtk.Entry(text=str(saved.get(key, "")))
            edit.set_hexpand(True)
            if key == "country":
                edit.set_max_length(2)
            if not required:
                edit.set_placeholder_text("optional")
            edit.connect("changed", self._update_ok)
            self.inputs[key] = edit
            grid.attach(edit, 1, row, 1, 1)

            hint = Gtk.Label(label=f"e.g. {example}" if example else "", xalign=0.0)
            hint.set_css_classes(["dim-label"])
            hint.set_size_request(110, -1)
            grid.attach(hint, 2, row, 1, 1)

        self.remember = Gtk.CheckButton(label="Remember these details for updates")
        self.remember.set_active(True)

        self.download_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.download_box.set_margin_start(24)
        self.download_box.append(intro)
        self.download_box.append(grid)
        self.download_box.append(self.remember)

        # -- file: an installer the user fetched in a browser --------------
        hint_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hint_row.append(Gtk.Label(label="Download the Linux installer from", xalign=0.0))
        hint_row.append(Gtk.LinkButton(uri=DOWNLOAD_PAGE, label="Blackmagic's download page"))
        hint_row.append(
            Gtk.Label(label=", then choose the .zip or .run file.", xalign=0.0)
        )
        hint_row.set_halign(Gtk.Align.START)

        self.file_edit = Gtk.Entry()
        self.file_edit.set_editable(False)
        self.file_edit.set_hexpand(True)
        self.file_edit.set_placeholder_text("No file chosen")
        browse = Gtk.Button(label="Choose…")
        browse.connect("clicked", self._browse)

        file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_row.append(self.file_edit)
        file_row.append(browse)

        self.file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.file_box.set_margin_start(24)
        self.file_box.append(hint_row)
        self.file_box.append(file_row)

        self.error = Gtk.Label(xalign=0.0, wrap=True)
        self.error.set_css_classes(["error"])

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._cancel)
        self.install = Gtk.Button(label="Install")
        self.install.set_sensitive(False)
        self.install.connect("clicked", self._accept)
        self.install.set_receives_default(True)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        buttons.append(cancel)
        buttons.append(self.install)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.append(self.download_radio)
        box.append(self.download_box)
        box.append(Gtk.Separator())
        box.append(self.file_radio)
        box.append(self.file_box)
        box.append(self.error)
        box.append(buttons)
        self.set_child(box)

        self.download_radio.connect("toggled", self._update_mode)
        self.file_radio.connect("toggled", self._update_mode)
        self.download_radio.set_active(True)
        self.connect("close-request", self._on_close_request)

    # -- modal behaviour ---------------------------------------------------
    def exec(self):
        self._loop = GLib.MainLoop()
        self.present()
        self._loop.run()
        return self.choice is not None

    def _on_close_request(self, *_):
        if self._loop is not None:
            self._loop.quit()
        return False

    def _cancel(self, *_):
        self.choice = None
        self.close()

    # -- state -------------------------------------------------------------
    def _registration(self):
        return {key: self.inputs[key].get_text().strip() for key, *_ in FIELDS}

    def _missing(self):
        data = self._registration()
        missing = [
            label for key, label, required, _ in FIELDS if required and not data[key]
        ]
        if data["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["email"]):
            missing.append("a valid e-mail")
        if data["country"] and not re.fullmatch(r"[A-Za-z]{2}", data["country"]):
            missing.append("a two-letter country code")
        return missing

    def _update_mode(self, *_):
        downloading = self.download_radio.get_active()
        self.download_box.set_sensitive(downloading)
        self.file_box.set_sensitive(not downloading)
        self._update_ok()

    def _update_ok(self, *_):
        if self.download_radio.get_active():
            ok = not self._missing()
        else:
            ok = bool(self.file_edit.get_text())
        self.install.set_sensitive(ok)

    def _browse(self, *_):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose the DaVinci Resolve installer")
        dialog.set_initial_folder(
            Gio.File.new_for_path(str(Path.home() / "Downloads"))
        )
        filters = Gio.ListStore.new(Gtk.FileFilter)
        installer_filter = Gtk.FileFilter()
        installer_filter.set_name("DaVinci Resolve installer")
        installer_filter.add_pattern("*.zip")
        installer_filter.add_pattern("*.run")
        filters.append(installer_filter)
        dialog.set_filters(filters)
        dialog.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path()
        if path:
            self.file_edit.set_text(path)
            self._update_ok()

    def _accept(self, *_):
        self.error.set_text("")
        if self.download_radio.get_active():
            data = self._registration()
            data["country"] = data["country"].lower()
            data["product"] = config.APP_NAME
            if self.remember.get_active():
                save(data)
            else:
                forget()
            self.choice = ("download", data)
            self.close()
            return

        path = Path(self.file_edit.get_text())
        is_studio_file = "studio" in path.name.lower()
        if is_studio_file != bool(config.STUDIO):
            want = "DaVinci Resolve Studio" if config.STUDIO else "DaVinci Resolve (free)"
            self.error.set_text(
                f"{path.name} does not look like the {want} installer. "
                "Choose the installer for this edition."
            )
            return
        if version_from_filename(path.name) is None:
            self.error.set_text(
                f"Cannot tell the version from {path.name}. Keep the file name "
                "Blackmagic gave it (e.g. DaVinci_Resolve_20.3.3_Linux.zip)."
            )
            return
        self.choice = ("file", path)
        self.close()
