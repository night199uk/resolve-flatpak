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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

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


class SourceDialog(QDialog):
    """Ask how to get the installer. After exec(), read `.choice`:

    ("download", registration_dict) or ("file", Path).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle(f"Install {config.APP_NAME}")
        self.setMinimumWidth(520)

        self.download_radio = QRadioButton("Download it from Blackmagic Design")
        self.file_radio = QRadioButton("Use an installer I already downloaded")
        group = QButtonGroup(self)
        group.addButton(self.download_radio)
        group.addButton(self.file_radio)

        # -- download: Blackmagic's registration form ----------------------
        intro = QLabel(
            "Blackmagic Design asks for these details before each download. "
            "They are sent only to blackmagicdesign.com, exactly as on its "
            "download page."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #888;")

        saved = load() or {}
        self.inputs = {}
        form = QFormLayout()
        for key, label, required, example in FIELDS:
            edit = QLineEdit(saved.get(key, ""))
            if key == "country":
                edit.setMaxLength(2)
            if not required:
                edit.setPlaceholderText("optional")
            edit.textChanged.connect(self._update_ok)
            self.inputs[key] = edit
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            hint = QLabel(f"e.g. {example}" if example else "")
            hint.setStyleSheet("color: #888;")
            hint.setMinimumWidth(110)
            row.addWidget(hint)
            form.addRow(label, row)

        self.remember = QCheckBox("Remember these details for updates")
        self.remember.setChecked(True)

        self.download_box = QWidget()
        dl_layout = QVBoxLayout(self.download_box)
        dl_layout.setContentsMargins(24, 0, 0, 0)
        dl_layout.addWidget(intro)
        dl_layout.addLayout(form)
        dl_layout.addWidget(self.remember)

        # -- file: an installer the user fetched in a browser --------------
        hint = QLabel(
            f'Download the Linux installer from <a href="{DOWNLOAD_PAGE}">'
            f"Blackmagic's download page</a>, then choose the .zip or .run file."
        )
        hint.setWordWrap(True)
        hint.setOpenExternalLinks(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("No file chosen")
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._browse)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse)

        self.file_box = QWidget()
        f_layout = QVBoxLayout(self.file_box)
        f_layout.setContentsMargins(24, 0, 0, 0)
        f_layout.addWidget(hint)
        f_layout.addLayout(file_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Install")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.download_radio)
        layout.addWidget(self.download_box)
        layout.addSpacing(8)
        layout.addWidget(self.file_radio)
        layout.addWidget(self.file_box)
        layout.addStretch(1)
        layout.addWidget(self.buttons)

        self.download_radio.toggled.connect(self._update_mode)
        self.file_radio.toggled.connect(self._update_mode)
        self.download_radio.setChecked(True)

    # -- state -------------------------------------------------------------
    def _registration(self):
        return {key: self.inputs[key].text().strip() for key, *_ in FIELDS}

    def _missing(self):
        data = self._registration()
        missing = [label for key, label, required, _ in FIELDS if required and not data[key]]
        if data["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["email"]):
            missing.append("a valid e-mail")
        if data["country"] and not re.fullmatch(r"[A-Za-z]{2}", data["country"]):
            missing.append("a two-letter country code")
        return missing

    def _update_mode(self):
        downloading = self.download_radio.isChecked()
        self.download_box.setEnabled(downloading)
        self.file_box.setEnabled(not downloading)
        self._update_ok()

    def _update_ok(self):
        if self.download_radio.isChecked():
            ok = not self._missing()
        else:
            ok = bool(self.file_edit.text())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose the DaVinci Resolve installer",
            str(Path.home() / "Downloads"),
            "DaVinci Resolve installer (*.zip *.run)",
        )
        if path:
            self.file_edit.setText(path)
            self._update_ok()

    def _accept(self):
        if self.download_radio.isChecked():
            data = self._registration()
            data["country"] = data["country"].lower()
            data["product"] = config.APP_NAME
            if self.remember.isChecked():
                save(data)
            else:
                forget()
            self.choice = ("download", data)
            return self.accept()

        path = Path(self.file_edit.text())
        is_studio_file = "studio" in path.name.lower()
        if is_studio_file != bool(config.STUDIO):
            want = "DaVinci Resolve Studio" if config.STUDIO else "DaVinci Resolve (free)"
            QMessageBox.warning(
                self, config.APP_NAME,
                f"{path.name} does not look like the {want} installer. "
                "Choose the installer for this edition.",
            )
            return
        if version_from_filename(path.name) is None:
            QMessageBox.warning(
                self, config.APP_NAME,
                f"Cannot tell the version from {path.name}. Keep the file name "
                "Blackmagic gave it (e.g. DaVinci_Resolve_20.3.3_Linux.zip).",
            )
            return
        self.choice = ("file", path)
        self.accept()
