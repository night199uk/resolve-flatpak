"""GTK4 installer GUI for DaVinci Resolve.

Public contract consumed by ``main.py`` is unchanged::

    app = InstallerApp(app_id=config.APP_ID)
    sys.exit(app.run(sys.argv))

Worker updates are marshalled to the GTK main loop with ``GLib.idle_add``;
``fraction is None`` still means "indeterminate / pulse".
"""

import sys
import threading
import time
import traceback
import urllib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib, Gtk

import config
from api import (
    get_latest_version_information, list_downloads, load_version_info,
    lookup_version_from_download_id, resolve_download_id_to_url,
    save_version_info, versions_match,
)
from download import download_file
from install import InstallationCancelled, install_application
from registration import SourceDialog, complete, load, version_from_filename


class InstallerWindow(Gtk.ApplicationWindow):
    def __init__(self, app_id=config.APP_ID, update=False, **kwargs):
        super().__init__(**kwargs)
        self._app_id = app_id
        self._update = update
        self.set_title(config.APP_NAME)
        self.set_default_size(650, 220)

        self.cancel_event = threading.Event()
        self._cancel_requested = False
        self._last_text = ""
        self._last_ui_at = 0.0
        self._pulse_src = None
        self._finished = False
        self._started = False
        self._source = None  # ("download", registration) or ("file", Path)

        self._build_ui()
        self.connect("map", self._on_map)

    # -- UI construction ---------------------------------------------------
    def _build_ui(self):
        self.step_label = Gtk.Label(label="Initializing ...", xalign=0.0)
        self.step_label.set_wrap(True)
        self.step_label.set_hexpand(True)
        self.step_label.set_css_classes(["status"])

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_hexpand(True)

        self.detail_label = Gtk.Label(
            label=f"Saving to: {config.DEST_DIR}", xalign=0.0, wrap=True
        )
        self.detail_label.set_css_classes(["detail"])

        # Failure output goes here rather than into the status label: a
        # read-only, selectable TextView in a scroller keeps a long traceback
        # readable and copyable. Hidden until a failure needs it.
        self.details = Gtk.TextView()
        self.details.set_editable(False)
        self.details.set_cursor_visible(False)
        self.details.set_monospace(True)
        self.details.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.details_scroller = Gtk.ScrolledWindow()
        self.details_scroller.set_child(self.details)
        self.details_scroller.set_vexpand(True)
        self.details_scroller.set_visible(False)

        self.button = Gtk.Button(label="Cancel")
        self.button.set_sensitive(False)
        self.button.connect("clicked", self._on_button_clicked)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.append(self.step_label)
        box.append(self.progress)
        box.append(self.detail_label)
        box.append(self.details_scroller)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_row.set_halign(Gtk.Align.END)
        button_row.append(self.button)
        box.append(button_row)

        self.set_child(box)
        self._install_css()

    @staticmethod
    def _install_css():
        css = b"""
        .status { font-weight: bold; }
        .detail { font-size: 11px; opacity: 0.7; }
        .error  { color: #e01b24; }
        .ok     { color: #2ec27e; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    # -- lifecycle ---------------------------------------------------------
    def _on_map(self, *_):
        if self._started:
            return
        self._started = True
        saved = load() if self._update else None
        if self._update and complete(saved):
            # The update was already confirmed and the registration details
            # are saved, so skip the source dialog and download directly.
            self._source = ("download", saved)
            self.button.set_sensitive(True)
            threading.Thread(target=self._work, daemon=True).start()
        else:
            # Ask where the installer comes from before anything touches the
            # network; queued so the dialog opens over the visible window.
            GLib.idle_add(self._choose_source)

    def _choose_source(self):
        dialog = SourceDialog(self)
        if not dialog.exec() or dialog.choice is None:
            self._finish(True, "Cancelled", "error")
            return False
        self._source = dialog.choice
        if self._source[0] == "file":
            config.STEPS = ["Installing application", "Complete"]
            self.detail_label.set_text(f"Installing from: {self._source[1]}")
        self.button.set_sensitive(True)
        threading.Thread(target=self._work, daemon=True).start()
        return False

    def _on_button_clicked(self, button):
        if button.get_label() == "Cancel":
            self._cancel_requested = True
            self.cancel_event.set()
            self.step_label.set_text("Cancelling ...")
            self.button.set_sensitive(False)
        else:  # Close
            self.close()

    # -- work flow (background thread) -------------------------------------
    def _work(self):
        # Set only for a download we started; a file the user picked in
        # _install_local must never be removed.
        dest = None
        try:
            kind, value = self._source
            if kind == "file":
                return self._install_local(value)
            registration_data = value

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

                final_url = resolve_download_id_to_url(download_id, self._step(1), registration_data)
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
                final_url = resolve_download_id_to_url(download_id, self._step(0), registration_data)
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
            self._finish(False, f"Failed: {exc}", "error", traceback.format_exc())
        finally:
            # The archive is multi-GB; don't leave it — or a partial download
            # after Cancel/failure — in downloads/ once we are done with it.
            if dest is not None:
                try:
                    dest.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    print(f"Warning: could not remove {dest}: {exc}", file=sys.stderr)

    def _install_local(self, path):
        """Install from an installer the user downloaded themselves."""
        try:
            version = version_from_filename(path.name)
            install_application(
                path,
                self._step(0),
                self.cancel_event,
                prefix=config.INSTALL_PREFIX,
                studio=config.STUDIO,
                version=version,
            )
            save_version_info(config.INSTALL_PREFIX, version, None)

            v = version
            msg = f"Complete - installed {v['major']}.{v['minor']}.{v['patch']}"
            self._report(f"[{len(config.STEPS)}/{len(config.STEPS)}] {msg}", 1.0)
            self._finish(False, msg, "ok")
        except InstallationCancelled:
            return self._finish(True, "Cancelled", "error")
        except Exception as exc:
            self._finish(False, f"Failed: {exc}", "error", traceback.format_exc())

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
            GLib.idle_add(self._ui_report, text, fraction)

    def _ui_report(self, text, fraction):
        self.step_label.set_text(text)
        if fraction is None:
            self.progress.set_fraction(0.0)
            self._start_pulse()
        else:
            self._stop_pulse()
            self.progress.set_fraction(max(0.0, min(1.0, fraction)))
        return False

    def _start_pulse(self):
        if self._pulse_src is None:
            self._pulse_src = GLib.timeout_add(100, self._pulse)

    def _stop_pulse(self):
        if self._pulse_src is not None:
            GLib.source_remove(self._pulse_src)
            self._pulse_src = None

    def _pulse(self):
        self.progress.pulse()
        return True

    # -- completion --------------------------------------------------------
    def _finish(self, cancelled, message, css_class, details=""):
        GLib.idle_add(self._ui_finish, cancelled, message, css_class, details)

    def _ui_finish(self, cancelled, message, css_class, details):
        if self._finished:
            return False
        self._finished = True
        self._stop_pulse()
        self.step_label.set_text(message or ("Cancelled" if cancelled else "Complete"))
        self.step_label.set_css_classes(["status", css_class])
        self.progress.set_fraction(1.0 if css_class == "ok" else 0.0)
        if details:
            self._show_details(details)
        self.button.set_label("Close")
        self.button.set_sensitive(True)
        return False

    def _show_details(self, details):
        """Reveal the full, copyable failure output and enlarge the window."""
        self.detail_label.set_visible(False)
        buffer = self.details.get_buffer()
        buffer.set_text(details)
        self.details_scroller.set_visible(True)
        self.set_default_size(820, 560)
        self.details.grab_focus()
        buffer.select_range(buffer.get_start_iter(), buffer.get_end_iter())


class InstallerApp(Gtk.Application):
    """GTK4 installer application.

        app = InstallerApp(app_id=config.APP_ID)
        sys.exit(app.run(sys.argv))
    """

    def __init__(self, app_id=None, update=False):
        super().__init__(
            application_id=app_id or config.APP_ID,
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self._update = update

    def do_activate(self):
        window = InstallerWindow(
            application=self,
            app_id=self.get_application_id(),
            update=self._update,
        )
        window.present()

    def run(self, argv=None):
        # The launcher passes main.py's argv; GTK would try to parse those
        # options, so only hand it the program name.
        return super().run([sys.argv[0]])
