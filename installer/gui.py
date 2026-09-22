"""PySide6 (Qt for Python) port of the installer GUI for DaVinci Resolve.

Faithful port of the committed GTK4 ``gui.py`` (243 lines).  Public contract
consumed by ``main.py`` is unchanged::

    app = InstallerApp(app_id=app_id)
    sys.exit(app.run(sys.argv))

Thread → UI marshalling uses Qt queued signals instead of ``GLib.idle_add`` /
``GLib.timeout_add``.  ``fraction is None`` still means "indeterminate / pulse".
"""

import threading
import time
import urllib

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from api import (
    get_latest_version_information, list_downloads, load_version_info,
    lookup_version_from_download_id, resolve_download_id_to_url,
    save_version_info, versions_match,
)
from download import download_file
from install import InstallationCancelled, install_application


class _InstallerSignals(QObject):
    """Thread-safe bridge: worker thread -> Qt main (UI) thread.

    Signals are emitted from the background worker and delivered on the main
    thread via automatic queued connections (safe cross-thread marshalling).
    """

    report = Signal(str, object)      # text, fraction (None => pulse; else 0..1)
    finish = Signal(bool, str, str)   # cancelled, message, css_class


class InstallerWindow(QMainWindow):
    def __init__(self, app_id=config.APP_TAG):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(650, 220)
        self.setMinimumSize(650, 220)
        self.setMaximumSize(650, 220)

        self._app_id = app_id
        self.cancel_event = threading.Event()
        self._cancel_requested = False
        self._last_text = ""
        self._last_ui_at = 0.0
        self._pulse_src = None
        self._pulse_timer = None
        self._finished = False
        self._started = False

        self._signals = _InstallerSignals()
        self._signals.report.connect(self._on_report)
        self._signals.finish.connect(self._on_finish)

        self._build_ui()

    # -- UI construction ---------------------------------------------------
    def _build_ui(self):
        self.step_label = QLabel("Initializing ...")
        self.step_label.setWordWrap(True)
        self.step_label.setObjectName("step_label")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        self.detail_label = QLabel(f"Saving to: {config.DEST_DIR}")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #888; font-size: 11px;")

        self.button = QPushButton("Cancel")
        self.button.setEnabled(False)
        self.button.clicked.connect(self._on_button_clicked)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(self.step_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.detail_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.button)
        layout.addLayout(button_row)

        self.setCentralWidget(central)

    # -- lifecycle ---------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            self.button.setEnabled(True)
            worker = threading.Thread(target=self._work, daemon=True)
            worker.start()

    def _on_button_clicked(self):
        if self.button.text() == "Cancel":
            self._cancel_requested = True
            self.cancel_event.set()
            self.step_label.setText("Cancelling ...")
            self._report("Cancelling ...", None)
            self.button.setEnabled(False)
        else:  # Close
            self.close()

    # -- work flow (background thread) -------------------------------------
    def _work(self):
        try:
            if config.DOWNLOAD_ID is None:
                # Get latest version from API
                (version, release_id, download_id) = get_latest_version_information(
                    config.APP_TAG,
                    self._step(0),
                    refer_id='77ef91f67a9e411bbbe299e595b4cfcc',
                    stable=not config.WANT_BETA,
                )

                # Check if already installed
                installed = load_version_info(config.INSTALL_PREFIX)
                if installed and versions_match(version, installed["version"]):
                    v = version
                    msg = f"Already installed: {v['major']}.{v['minor']}.{v['patch']}"
                    self._finish(False, f"[{len(config.STEPS)}/{len(config.STEPS)}] {msg}", "ok")
                    return

                final_url = resolve_download_id_to_url(download_id, self._step(1))
                download_step_index = 2
            else:
                # Look up version from download_id
                self._report("Looking up version information", 0.25)
                version = lookup_version_from_download_id(config.DOWNLOAD_ID, config.APP_TAG)
                if version is None:
                    raise RuntimeError(f"Could not find download with ID: {config.DOWNLOAD_ID}")

                # Check if already installed
                installed = load_version_info(config.INSTALL_PREFIX)
                if installed and versions_match(version, installed["version"]):
                    v = version
                    msg = f"Already installed: {v['major']}.{v['minor']}.{v['patch']}"
                    self._finish(False, f"[{len(config.STEPS)}/{len(config.STEPS)}] {msg}", "ok")
                    return

                download_id = config.DOWNLOAD_ID
                final_url = resolve_download_id_to_url(download_id, self._step(0))
                download_step_index = 1

            name = urllib.parse.unquote(urllib.parse.urlsplit(final_url).path.split("/")[-1])
            dest = config.DEST_DIR / (name or "download.bin")

            if not download_file(final_url, dest, self._step(download_step_index), self.cancel_event):
                return self._finish(True, "Cancelled", "error")

            install_application(
                dest,
                self._step(download_step_index + 1),
                self.cancel_event,
                prefix=config.INSTALL_PREFIX,
                studio=config.STUDIO,
                version=version,
            )

            # Save version info after successful installation
            save_version_info(config.INSTALL_PREFIX, version, download_id)

            v = version
            msg = f"Complete - installed {v['major']}.{v['minor']}.{v['patch']}"
            self._report(f"[{len(config.STEPS)}/{len(config.STEPS)}] {msg}", 1.0)
            self._finish(False, msg, "ok")
        except InstallationCancelled:
            return self._finish(True, "Cancelled", "error")
        except Exception as exc:
            self._finish(False, f"Failed: {exc}", "error")

    def _step(self, index):
        """Return a `report(text, fraction)` bound to step number `index`."""

        def report(text, fraction):
            self._report(f"[{index + 1}/{len(config.STEPS)}] {config.STEPS[index]} - {text}", fraction)

        return report

    # -- UI marshalling (thread -> main loop) ------------------------------
    def _report(self, text, fraction):
        """Callable from the worker thread: throttle then marshal to the UI."""
        now = time.monotonic()
        force = fraction == 1.0 or fraction is None or text != self._last_text
        if force or (now - self._last_ui_at >= 0.1):
            self._last_text = text
            self._last_ui_at = now
            self._signals.report.emit(text, fraction)

    def _on_report(self, text, fraction):
        self.step_label.setText(text)
        if fraction is None:
            self.progress.setRange(0, 0)
            self.progress.setValue(0)
            self._start_pulse()
        else:
            self._stop_pulse()
            self.progress.setRange(0, 100)
            self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def _start_pulse(self):
        if self._pulse_timer is None:
            self._pulse_timer = QTimer(self)
            self._pulse_timer.timeout.connect(self._pulse)
            self._pulse_timer.start(100)

    def _stop_pulse(self):
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer.deleteLater()
            self._pulse_timer = None

    def _pulse(self):
        value = (self.progress.value() + 1) % 101
        self.progress.setValue(value)

    # -- completion --------------------------------------------------------
    def _finish(self, cancelled, message, css_class):
        self._signals.finish.emit(cancelled, message, css_class)

    def _on_finish(self, cancelled, message, css_class):
        if self._finished:
            return
        self._finished = True
        self._stop_pulse()
        self.step_label.setText(message or ("Cancelled" if cancelled else "Complete"))
        if css_class == "ok":
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.step_label.setStyleSheet("color: #2ec27e; font-weight: bold;")
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.step_label.setStyleSheet("color: #e01b24; font-weight: bold;")
        self.button.setText("Close")
        self.button.setEnabled(True)


class InstallerApp:
    """PySide6 installer application.

        app = InstallerApp(app_id=APP_TAG)
        sys.exit(app.run(sys.argv))
    """

    def __init__(self, app_id=config.APP_TAG):
        self.app_id = app_id
        self._app = None
        self._window = None

    def run(self, argv):
        app = QApplication.instance() or QApplication(argv)
        self._app = app

        self._window = InstallerWindow(app_id=self.app_id)
        self._window.show()

        return self._app.exec()
