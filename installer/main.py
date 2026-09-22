#!/usr/bin/env python3
"""DaVinci Resolve installer and launcher (GTK4 / Wayland).

This script serves two purposes:
1. As an installer: Downloads and installs DaVinci Resolve with a progress bar
2. As a launcher: Launches DaVinci Resolve applications, checking for installation/updates

For meta-Flatpak packaging, use --export-flatpak-resources to export desktop files,
icons, and MIME types that Flatpak needs at packaging time.

Run:  python3 main.py --help
"""

import argparse
import sys
import textwrap
from pathlib import Path

import config
from api import list_downloads
from gui import InstallerApp
from export import export_flatpak_resources
from launcher import launch_application
from udev import print_udev_rules

def main():
    called_name = Path(sys.argv[0]).name
    parser = argparse.ArgumentParser(
        description="DaVinci Resolve installer and launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            f"""
                Examples:
                  # Install DaVinci Resolve
                  python3 {called_name}

                  # Install DaVinci Resolve Studio
                  python3 {called_name} --studio

                  # List available downloads
                  python3 {called_name} --list-downloads

                  # Launch DaVinci Resolve (checks installation first)
                  python3 {called_name} --run-resolve

                  # Export Flatpak resources for packaging
                  python3 {called_name} --export-flatpak-resources /path/to/output
                """
    ))
    
    # Installation options
    if called_name == "main.py":
      parser.add_argument("--studio", action="store_true", help="Install DaVinci Resolve Studio")

    parser.add_argument("--install", action="store_true", help="Open the standalone installer GUI")
    parser.add_argument("--list-downloads", action="store_true", help="List available downloads and exit")
    parser.add_argument("--download_id", help="Skip URL resolution, download specific package by ID")
    parser.add_argument("--prefix", type=Path, help="Installation prefix (default: ~/.var/app/{app-id}/data)")

    # Flatpak export options
    parser.add_argument("--export-flatpak-resources", type=Path, metavar="DIR",
                       help="Export desktop files, icons, and MIME types for Flatpak packaging")

    # Flatpak export options
    parser.add_argument("--print-udev-rules", action="store_true",
                       help="Print the udev rules - | tee /etc/udev/rules.d/95-davinci.rules")

    # Launcher options
    parser.add_argument("--run-resolve", action="store_true", help="Launch DaVinci Resolve")
    parser.add_argument("--run-brawplayer", action="store_true", help="Launch Blackmagic RAW Player")
    parser.add_argument("--run-brawspeedtest", action="store_true", help="Launch Blackmagic RAW Speed Test")
    parser.add_argument("--run-panel-setup", action="store_true", help="Launch DaVinci Resolve Panels Setup")
    parser.add_argument("--run-remote-monitoring", action="store_true", help="Launch DaVinci Remote Monitoring")
    
    args = parser.parse_args()
    
    if called_name == "main.py":
      config.STUDIO = args.studio
    elif called_name == "resolve.py":
      config.STUDIO = False
    elif called_name == "resolve-studio.py":
      config.STUDIO = True
    else:
      print("Error: could not decode called script name", file=sys.stderr)
      sys.exit(1)

    config.DOWNLOAD_ID = args.download_id
    
    if config.STUDIO:
        config.APP_NAME = "DaVinci Resolve Studio"
        config.APP_TAG = "davinci-resolve-studio"
        app_id = "com.blackmagic.ResolveStudio"
    else:
        config.APP_NAME = "DaVinci Resolve"
        config.APP_TAG = "davinci-resolve"
        app_id = "com.blackmagic.Resolve"
    
    # Set default prefix
    if args.prefix:
        config.INSTALL_PREFIX = args.prefix
    else:
        config.INSTALL_PREFIX = Path.home() / ".var" / "app" / app_id / "data"
    
    # Handle --list-downloads
    if args.list_downloads:
        list_downloads(config.APP_TAG)
        sys.exit(0)
    
    # Handle --export-flatpak-resources
    if args.export_flatpak_resources:
        if args.studio:
            print("Error: --studio cannot be used with --export-flatpak-resources", file=sys.stderr)
            print("The export command will export resources for both Resolve and Resolve Studio.", file=sys.stderr)
            sys.exit(1)
        export_flatpak_resources(args.export_flatpak_resources, prefix=config.INSTALL_PREFIX)
        sys.exit(0)
    
    # Handle --print-udev-rules
    if args.print_udev_rules:
        print_udev_rules(config.INSTALL_PREFIX)
        sys.exit(0)
    
    # Handle launcher options
    if args.run_resolve:
        sys.exit(launch_application("resolve", prefix=config.INSTALL_PREFIX, studio=config.STUDIO))
    
    if args.run_brawplayer:
        sys.exit(launch_application("brawplayer", prefix=config.INSTALL_PREFIX, args=sys.argv[2:], studio=config.STUDIO))
    
    if args.run_brawspeedtest:
        sys.exit(launch_application("brawspeedtest", prefix=config.INSTALL_PREFIX, studio=config.STUDIO))
    
    if args.run_panel_setup:
        sys.exit(launch_application("panel-setup", prefix=config.INSTALL_PREFIX, studio=config.STUDIO))
    
    if args.run_remote_monitoring:
        sys.exit(launch_application("remote-monitoring", prefix=config.INSTALL_PREFIX, studio=config.STUDIO))
    
    # Standalone installer GUI (--install)
    if args.install:
        if config.DOWNLOAD_ID:
            config.STEPS = ["Resolving Download URL", "Downloading file", "Installing application", "Complete"]
        else:
            config.STEPS = ["Finding Latest Version", "Resolving Download URL", "Downloading file", "Installing application", "Complete"]
        
        app = InstallerApp(app_id=app_id)
        sys.exit(app.run(sys.argv))
    
    # Default action (`flatpak run com.blackmagic.Resolve`): launcher flow.
    # Check installation and updates; if the current version is installed,
    # hand over execution to DaVinci Resolve immediately.
    sys.exit(launch_application("resolve", prefix=config.INSTALL_PREFIX, studio=config.STUDIO))


if __name__ == "__main__":
    main()
