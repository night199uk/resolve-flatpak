"""Launcher functionality for DaVinci Resolve applications (PySide6).

PySide6 port of the original GTK ``launcher.py``.  The public contract used by
``main.py`` is unchanged:

* ``check_installation(prefix=INSTALL_PREFIX)`` -> version dict or None
* ``check_for_updates(prefix, studio=STUDIO)`` -> latest version dict or None
* ``prompt_installation(studio=False, parent_window=None)`` -> bool
* ``prompt_update(latest_version, studio=False, parent_window=None)`` ->
  one of ``"install_now"`` / ``"install_later"`` / ``"dont_prompt"``
* ``launch_application(app_name, prefix=..., args=..., studio=...)`` ->
  int exit code (handoff via ``os.execvpe``)

The only change from the committed GTK version is that user prompts use
``QMessageBox`` (PySide6) instead of ``Gtk.MessageDialog``.  Installation / URL
resolution / version / exec handoff logic is otherwise identical.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import config
from api import (
    get_latest_version_information, load_version_info,
    lookup_version_from_download_id, resolve_download_id_to_url,
    save_version_info, versions_match,
)
from download import download_file
from install import InstallationCancelled, install_application


def check_installation(prefix=None):
    """Check if DaVinci Resolve is installed.

    Returns:
        dict with version info if installed, None otherwise
    """
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    return load_version_info(prefix)


def check_for_updates(prefix=None, studio=None):
    """Check if a newer version is available.

    Returns:
        dict with latest version info if newer version available, None otherwise
    """
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    if studio is None:
        studio = config.STUDIO
    
    installed = check_installation(prefix)
    if not installed:
        return None

    try:
        # Get latest version from API
        app_tag = "davinci-resolve-studio" if studio else "davinci-resolve"
        latest_version, _, _ = get_latest_version_information(
            app_tag,
            lambda text, frac: None,  # No progress reporting
            stable=not config.WANT_BETA,
        )

        # Check if newer version available
        if not versions_match(latest_version, installed["version"]):
            return latest_version
    except Exception as e:
        print(f"Warning: Could not check for updates: {e}", file=sys.stderr)

    return None


def _dont_prompt_file(prefix=None):
    """Return path to the dont_prompt preferences file."""
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    return Path(prefix) / ".dont_prompt_versions.json"


def load_dont_prompt_versions(prefix=None):
    """Load the set of version strings the user has suppressed."""
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    path = _dont_prompt_file(prefix)
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data)
    except (json.JSONDecodeError, OSError):
        return set()


def save_dont_prompt_version(version, prefix=None):
    """Record that the user doesn't want to be prompted for this version."""
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    path = _dont_prompt_file(prefix)
    suppressed = load_dont_prompt_versions(prefix)
    version_str = f"{version['major']}.{version['minor']}.{version['patch']}"
    suppressed.add(version_str)
    try:
        with open(path, "w") as f:
            json.dump(list(suppressed), f)
    except OSError as e:
        print(f"Warning: Could not save dont_prompt preference: {e}", file=sys.stderr)


def is_version_suppressed(version, prefix=None):
    """Check if the user has suppressed prompts for this version."""
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    suppressed = load_dont_prompt_versions(prefix)
    version_str = f"{version['major']}.{version['minor']}.{version['patch']}"
    return version_str in suppressed


def prompt_installation(studio=False, parent_window=None):
    """Prompt the user to install DaVinci Resolve.

    Returns:
        True if user wants to install, False otherwise
    """
    app_name = "DaVinci Resolve Studio" if studio else "DaVinci Resolve"

    app = QApplication.instance() or QApplication(sys.argv[:1])
    box = QMessageBox(parent_window)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(config.APP_NAME)
    box.setText(f"{app_name} is not installed.")
    box.setInformativeText(f"Would you like to install {app_name} now?")
    yes = box.addButton("Install Now", QMessageBox.ButtonRole.YesRole)
    box.addButton("Install Later", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(yes)
    box.exec()

    return box.clickedButton() is yes


def prompt_update(latest_version, studio=False, parent_window=None):
    """Prompt the user to update DaVinci Resolve.

    Returns:
        One of "install_now", "install_later", or "dont_prompt"
    """
    app_name = "DaVinci Resolve Studio" if studio else "DaVinci Resolve"

    app = QApplication.instance() or QApplication(sys.argv[:1])
    box = QMessageBox(parent_window)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(config.APP_NAME)
    box.setText(f"A new version of {app_name} is available.")
    v = latest_version
    box.setInformativeText(
        f"Version {v['major']}.{v['minor']}.{v['patch']} is now available. "
        "Would you like to install it now?"
    )

    install_now = box.addButton("Install Now", QMessageBox.ButtonRole.YesRole)
    install_later = box.addButton("Install Later", QMessageBox.ButtonRole.NoRole)
    dont_prompt = box.addButton("Don't prompt again", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(install_now)
    box.exec()

    clicked = box.clickedButton()
    if clicked is install_now:
        return "install_now"
    elif clicked is install_later:
        return "install_later"
    else:
        return "dont_prompt"


def launch_application(app_name, prefix=None, args=None, studio=None):
    """Launch a DaVinci Resolve application.

    Args:
        app_name: Name of the application to launch
        prefix: Installation prefix
        args: Additional arguments to pass to the application
        studio: Whether this is the Studio version

    Returns:
        Exit code from the application
    """
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    if studio is None:
        studio = config.STUDIO
    
    prefix = Path(prefix)

    # Gate: Check if installed, prompt to install if not
    installed = check_installation(prefix)
    if not installed:
        if prompt_installation(studio=studio):
            # User accepted - kick off installer GUI
            from gui import InstallerApp
            app_id = "com.blackmagic.ResolveStudio" if studio else "com.blackmagic.Resolve"
            installer = InstallerApp(app_id=app_id)
            exit_code = installer.run(sys.argv)
            
            # Check if installation succeeded
            if exit_code == 0:
                installed = check_installation(prefix)
                if not installed:
                    print(f"Installation completed but Resolve not found", file=sys.stderr)
                    return 1
                # Continue to launch Resolve
            else:
                # Installation failed
                return exit_code
        else:
            # User declined
            print(f"DaVinci Resolve is not installed", file=sys.stderr)
            return 1

    # Gate: Check for updates, prompt if available and not suppressed
    latest = check_for_updates(prefix, studio=studio)
    if latest and not is_version_suppressed(latest, prefix=prefix):
        choice = prompt_update(latest, studio=studio)
        if choice == "install_now":
            # User wants to update - kick off installer GUI
            from gui import InstallerApp
            app_id = "com.blackmagic.ResolveStudio" if studio else "com.blackmagic.Resolve"
            installer = InstallerApp(app_id=app_id)
            exit_code = installer.run(sys.argv)
            
            # Check if update succeeded
            if exit_code == 0:
                installed = check_installation(prefix)
                if not installed:
                    print(f"Update completed but Resolve not found", file=sys.stderr)
                    return 1
                # Continue to launch Resolve
            else:
                # Update failed
                return exit_code
        elif choice == "dont_prompt":
            # User doesn't want to be prompted for this version again
            save_dont_prompt_version(latest, prefix=prefix)
        # "install_later" or "dont_prompt" - continue to handoff

    # Handoff to Resolve
    app_bin = prefix / "bin"
    resolver_path = app_bin / "resolve"

    cmd = [str(resolver_path)]
    if args:
        cmd.extend(args)

    # Set up environment
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(prefix / "libs") + ":" + env.get("LD_LIBRARY_PATH", "")

    # Ensure the app can find its own bundled libraries and resources
    # env["QT_QPA_PLATFORM"] = "xcb"
    env["RESOLVE_INSTALL_LOCATION"] = str(prefix)
    env["DAVINCI_RESOLVE_CONFIG_DIR"] = str(prefix / "config")
    env["DAVINCI_RESOLVE_LOG_DIR"] = str(prefix / "logs")

    print(f"Launching {resolver_path} (studio={studio})")
    try:
        os.execvpe(str(resolver_path), cmd, env)
    except Exception as e:
        print(f"Failed to launch DaVinci Resolve: {e}", file=sys.stderr)
        return 1
