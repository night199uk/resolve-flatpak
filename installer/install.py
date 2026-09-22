"""Installation logic for DaVinci Resolve."""

import os
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import zipfile
from pathlib import Path

import config


class InstallationCancelled(Exception):
    """Raised by the worker thread when the user cancels the install."""


def _copy_tree(src, dst):
    """cp -rp equivalent: recursive copy preserving symlinks and metadata."""
    shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)


def _make_symlink(target, link):
    """ln -s equivalent; recreates `link` if it already exists."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target)


def _find_squashfs_offset(path):
    """Return the byte offset of the embedded squashfs superblock.

    AppImage-style installers prepend an ELF runtime to a squashfs image, so
    unsquashfs needs the offset of the 'hsqs' superblock magic. The magic is
    searched in a streaming fashion to avoid loading the (multi-GB) archive
    into memory.
    """
    magic = b"hsqs"
    found_offsets = []
    
    # Find all occurrences of the magic bytes
    with open(path, "rb") as fh:
        carry = b""
        pos = 0
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            haystack = carry + chunk
            idx = 0
            while True:
                idx = haystack.find(magic, idx)
                if idx == -1:
                    break
                found_offsets.append(pos + idx)
                idx += 1
            carry = haystack[-(len(magic) - 1):]
            pos += len(chunk)

    if not found_offsets:
        raise RuntimeError("could not find squashfs superblock ('hsqs') in installer")

    # Validate each occurrence by checking the block size
    with open(path, "rb") as fh:
        for offset in found_offsets:
            fh.seek(offset + 12)
            bs_bytes = fh.read(4)
            if len(bs_bytes) == 4:
                block_size = int.from_bytes(bs_bytes, "little")
                # Valid squashfs block sizes are typically 4KB to 1MB
                if 4096 <= block_size <= 1024 * 1024:
                    return offset

    raise RuntimeError(f"found {len(found_offsets)} squashfs superblocks but none have valid block sizes")


def _locate_run_archive(dest, workdir):
    """Return the path to the .run installer, unwrapping a .zip wrapper if needed.

    Blackmagic now distributes the installer as a .zip (e.g.
    DaVinci_Resolve_21.1_Linux.zip) whose contents include the .run file that
    embeds the squashfs image. Older downloads are already the bare .run file.
    """
    if str(dest).lower().endswith(".zip"):
        with zipfile.ZipFile(dest) as archive:
            archive.extractall(workdir)
        run_files = [p for p in Path(workdir).iterdir() if p.suffix.lower() == ".run"]
        if not run_files:
            raise RuntimeError("no .run file found inside downloaded zip archive")
        return run_files[0]
    return dest


def install_application(dest, report, cancel_event, prefix=None, studio=None, version=None):
    """
    Extracts the DaVinci Resolve .run installer into a temporary directory and
    copies the payload into `prefix` (default /app).
    """
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    if studio is None:
        studio = config.STUDIO
    if version is None:
        version = {"major": 21, "minor": 0, "patch": 0}  # Default to latest
    
    app_id = "com.blackmagic.ResolveStudio" if studio else "com.blackmagic.Resolve"
    app_description = "DaVinci Resolve Studio" if studio else "DaVinci Resolve"
    major_version = version.get("major", 21)

    def check_cancel():
        if cancel_event.is_set():
            raise InstallationCancelled()

    def task(label, fraction, fn):
        check_cancel()
        report(label, fraction)
        fn()

    prefix = Path(prefix)
    workdir = Path(tempfile.mkdtemp(dir=config.DEST_DIR, prefix="resolve-install-"))
    squashfs_root = workdir / "squashfs-root"

    try:
        report("Extracting installer archive (this can take a while)", None)
        run_file = _locate_run_archive(dest, workdir)
        os.chmod(run_file, os.stat(run_file).st_mode | 0o111)
        offset = _find_squashfs_offset(run_file)
        unsquashfs = shutil.which("unsquashfs")
        if unsquashfs is None:
            raise RuntimeError("unsquashfs not found in PATH (install squashfs-tools)")
        extraction = subprocess.run(
            [unsquashfs,
             "-quiet", "-no-progress", "-no-xattrs",
             "-d", str(squashfs_root),
             "-offset", str(offset),
             str(run_file)],
            check=False,
            capture_output=True,
            text=True,
        )
        if extraction.returncode != 0:
            detail = (extraction.stderr or extraction.stdout or "").strip()
            raise RuntimeError(f"unsquashfs failed: {detail}")
        if not squashfs_root.is_dir():
            raise RuntimeError("unsquashfs did not produce squashfs-root")

        def chmod_path(path, extra_mode):
            if not path.is_symlink():
                os.chmod(path, os.stat(path).st_mode | extra_mode)

        def chmod_tree(root, file_mode, dir_mode):
            for dirpath, dirnames, filenames in os.walk(root):
                for name in dirnames:
                    chmod_path(Path(dirpath) / name, dir_mode)
                for name in filenames:
                    chmod_path(Path(dirpath) / name, file_mode)

        task("Applying permissions to extracted files", 0.1,
             lambda: chmod_tree(squashfs_root, 0o644, 0o755))

        def make_dirs():
            # Common directories for all versions
            dirs = [
                "easyDCP", "scripts", "share", "Fairlight",
                ".license",
                "share/applications",
                "share/icons/hicolor/128x128/apps",
                "share/icons/hicolor/256x256/apps",
                "IOPlugins",
            ]
            
            # Version 15 specific directories
            if major_version == 15:
                dirs.extend([
                    "configs", "logs", ".LUT", ".crashreport",
                    "DolbyVision", "Media", "Resolve Disk Database",
                ])
            
            # Version 20+ specific directories
            if major_version >= 20:
                dirs.extend([
                    "Extras",
                    "Apple Immersive/Calibration",
                ])
            
            # Version 21 specific directories
            if major_version >= 21:
                dirs.append("Immersive")
            
            for rel in dirs:
                directory = prefix / rel
                os.makedirs(directory, exist_ok=True)
                os.chmod(directory, 0o755)

        task("Creating directory structure", 0.15, make_dirs)

        def copy_payload():
            # Common directories for all versions
            dirs = ["bin", "Control", "DaVinci Control Panels Setup", "Developer", 
                    "docs", "Fusion", "graphics", "libs", "LUT", "Onboarding", "plugins", "UI_Resource"]
            
            # Version 18+: adds Certificates and Fairlight Studio Utility
            if major_version >= 18:
                dirs.extend(["Certificates", "Fairlight Studio Utility"])
            
            # Version 17+: adds Technical Documentation
            if major_version >= 17:
                dirs.append("Technical Documentation")
            
            # Version 16: skip Technical Documentation for 16.0b
            if major_version == 16:
                minor = version.get("minor", 0)
                if minor == 0 and "b" in str(version.get("build", "")):
                    pass  # Don't add Technical Documentation
                else:
                    dirs.append("Technical Documentation")
            
            for rel in dirs:
                src = squashfs_root / rel
                if src.exists():
                    _copy_tree(src, prefix / rel)

        task("Copying application payload", 0.25, copy_payload)

        def strip_glib():
            # Version 19+: move problematic libs to libs/disabled/
            # Earlier versions: don't strip them
            if major_version < 19:
                return
            
            libs_dir = prefix / "libs"
            if not libs_dir.exists():
                return
            
            disabled_dir = libs_dir / "disabled"
            disabled_dir.mkdir(exist_ok=True)
            
            for pattern in ("libglib*", "libgio*", "libgmodule*", "libgobject*"):
                for lib in libs_dir.glob(pattern):
                    shutil.move(str(lib), str(disabled_dir / lib.name))

        task("Disabling bundled GLib libraries", 0.5, strip_glib)

        def copy_scripts_and_share():
            for name in ("script.checkfirmware", "script.getlogs.v4", "script.start"):
                src = squashfs_root / "scripts" / name
                if src.exists():
                    shutil.copy2(src, prefix / "scripts")
            for name in ("default-config.dat", "default_cm_config.bin", "log-conf.xml"):
                src = squashfs_root / "share" / name
                if src.exists():
                    shutil.copy2(src, prefix / "share")
            
            # Version 18: remote-monitoring-log-conf.xml
            # Version 19+: remote-monitor-log-conf.xml (note the different name)
            if major_version == 18:
                remote = squashfs_root / "share" / "remote-monitoring-log-conf.xml"
                if remote.exists():
                    shutil.copy2(remote, prefix / "share")
            elif major_version >= 19:
                remote = squashfs_root / "share" / "remote-monitor-log-conf.xml"
                if remote.exists():
                    shutil.copy2(remote, prefix / "share")

        task("Copying scripts and shared configuration", 0.6, copy_scripts_and_share)

        def extract_panel_api():
            tgz = squashfs_root / "share" / "panels" / "dvpanel-framework-linux-x86_64.tgz"
            if not tgz.exists():
                return
            
            # Version 15-16: only libDaVinciPanelAPI
            # Version 17+: both libDaVinciPanelAPI and libFairlightPanelAPI
            if major_version >= 17:
                members = ("libDaVinciPanelAPI.so", "libFairlightPanelAPI.so")
            else:
                members = ("libDaVinciPanelAPI.so",)
            
            with tarfile.open(tgz, "r:*") as archive:
                for member in members:
                    try:
                        archive.getmember(member)
                    except KeyError:
                        continue
                    archive.extract(member, prefix / "libs")

        task("Extracting panel framework API", 0.65, extract_panel_api)

        def quiet_errors():
            # Version 16-17.1: create BlackmagicRawAPI symlinks
            # Version 17.2.2+: skip (no longer needed)
            # Version 15: skip (different handling)
            if major_version == 15:
                return
            
            # Check if we need to create symlinks
            # Version 17.2.2+ doesn't need them
            needs_symlinks = True
            if major_version == 17:
                # Check minor.patch version
                minor = version.get("minor", 0)
                patch = version.get("patch", 0)
                if minor > 2 or (minor == 2 and patch >= 2):
                    needs_symlinks = False
            
            if not needs_symlinks:
                return
            
            api_dir = prefix / "bin" / "BlackmagicRawAPI"
            os.makedirs(api_dir, exist_ok=True)
            _make_symlink(Path("..") / "libs" / "libBlackmagicRawAPI.so", prefix / "bin" / "libBlackmagicRawAPI.so")
            _make_symlink(Path("..") / ".." / "libs" / "libBlackmagicRawAPI.so", api_dir / "libBlackmagicRawAPI.so")

        task("Linking Blackmagic RAW API", 0.7, quiet_errors)

        def write_desktop(name, content):
            (prefix / "share" / "applications" / name).write_text(content)

        def copy_icon(src, icon_dir, name):
            if src.exists():
                shutil.copy2(src, prefix / icon_dir / name)

        def add_raw_player():
            bundle = squashfs_root / "BlackmagicRAWPlayer"
            if not bundle.exists():
                return
            _copy_tree(bundle, prefix / "BlackmagicRAWPlayer")
            write_desktop(f"{app_id}.RAWPlayer.desktop",
                textwrap.dedent(
                f"""[Desktop Entry]
                    Version=1.0
                    Type=Application
                    Name=Blackmagic RAW Player
                    Exec={prefix}/BlackmagicRAWPlayer/BlackmagicRAWPlayer
                    Icon={app_id}.RAWPlayer
                    Terminal=false
                    MimeType=application/x-braw-clip;application/x-braw-sidecar;
                    StartupNotify=true
                    Categories=AudioVideo
                    PrefersNonDefaultGPU=true
                    """))
            copy_icon(squashfs_root / "graphics" / "blackmagicraw-player_256x256_apps.png",
                      "share/icons/hicolor/256x256/apps", f"{app_id}.RAWPlayer.png")

        task("Adding BlackmagicRAWPlayer", 0.76, add_raw_player)

        def add_raw_speed_test():
            bundle = squashfs_root / "BlackmagicRAWSpeedTest"
            if not bundle.exists():
                return
            _copy_tree(bundle, prefix / "BlackmagicRAWSpeedTest")
            write_desktop(f"{app_id}.RAWSpeedTest.desktop",
                textwrap.dedent(
                f"""[Desktop Entry]
                    Version=1.0
                    Type=Application
                    Name=Blackmagic RAW Speed Test
                    Exec={prefix}/BlackmagicRAWSpeedTest/BlackmagicRAWSpeedTest
                    Icon={app_id}.RAWSpeedTest
                    Terminal=false
                    StartupNotify=true
                    Categories=AudioVideo
                    PrefersNonDefaultGPU=true
                    """))
            copy_icon(squashfs_root / "graphics" / "blackmagicraw-speedtest_256x256_apps.png",
                      "share/icons/hicolor/256x256/apps", f"{app_id}.RAWSpeedTest.png")

        task("Adding BlackmagicRAWSpeedTest", 0.82, add_raw_speed_test)

        def add_main_desktop():
            write_desktop(f"{app_id}.desktop",
                textwrap.dedent(
                f"""[Desktop Entry]
                    Version=1.0
                    Type=Application
                    Name={app_description}
                    Name[en_US]={app_description}
                    GenericName={app_description}
                    Comment=Revolutionary new tools for editing, visual effects, color correction and professional audio post production, all in a single application!
                    Exec={prefix}/bin/resolve.sh %U
                    Icon={app_id}
                    Terminal=false
                    MimeType=application/x-resolveproj;application/x-resolvebin;application/x-resolvetimeline;application/x-resolvetemplatebundle;application/x-resolvedbkey;
                    StartupNotify=true
                    Categories=AudioVideo
                    PrefersNonDefaultGPU=true
                    """))
            copy_icon(squashfs_root / "graphics" / "DV_Resolve.png",
                      "share/icons/hicolor/128x128/apps", f"{app_id}.png")

        task("Installing desktop entry", 0.88, add_main_desktop)

        def add_panel_setup():
            # Check for both naming variants
            # Version 15-16: "DaVinci Resolve Panels Setup"
            # Version 17+: "DaVinci Control Panels Setup"
            binary = None
            panel_dir = None
            
            if (prefix / "DaVinci Control Panels Setup" / "DaVinci Control Panels Setup").exists():
                binary = prefix / "DaVinci Control Panels Setup" / "DaVinci Control Panels Setup"
                panel_dir = "DaVinci Control Panels Setup"
            elif (prefix / "DaVinci Resolve Panels Setup" / "DaVinci Resolve Panels Setup").exists():
                binary = prefix / "DaVinci Resolve Panels Setup" / "DaVinci Resolve Panels Setup"
                panel_dir = "DaVinci Resolve Panels Setup"
            
            if not binary:
                return
            
            write_desktop(f"{app_id}.PanelSetup.desktop",
                textwrap.dedent(
                f"""[Desktop Entry]
                    Version=1.0
                    Type=Application
                    Name=DaVinci Resolve Panels Setup
                    Exec="{prefix}/{panel_dir}/{panel_dir}"
                    Icon={app_id}.PanelSetup
                    Terminal=false
                    StartupNotify=true
                    Categories=AudioVideo
                    PrefersNonDefaultGPU=true
                    """))
            copy_icon(squashfs_root / "graphics" / "DV_Panels.png",
                      "share/icons/hicolor/128x128/apps", f"{app_id}.PanelSetup.png")

        task("Installing panel setup entry", 0.92, add_panel_setup)

        def add_remote_monitoring():
            # Check for both naming variants
            # Older versions: "DaVinci Remote Monitoring"
            # Newer versions: "DaVinci Remote Monitor"
            binary = None
            binary_name = None
            
            if (prefix / "bin" / "DaVinci Remote Monitoring").exists():
                binary = prefix / "bin" / "DaVinci Remote Monitoring"
                binary_name = "DaVinci Remote Monitoring"
            elif (prefix / "bin" / "DaVinci Remote Monitor").exists():
                binary = prefix / "bin" / "DaVinci Remote Monitor"
                binary_name = "DaVinci Remote Monitor"
            
            if not binary:
                return
            
            write_desktop(f"{app_id}.RemoteMonitoring.desktop",
                textwrap.dedent(
                f"""[Desktop Entry]
                    Version=1.0
                    Type=Application
                    Name={binary_name}
                    Exec="{prefix}/bin/{binary_name}"
                    Icon={app_id}.RemoteMonitoring
                    Terminal=false
                    StartupNotify=true
                    Categories=AudioVideo
                    PrefersNonDefaultGPU=true
                    """))
            copy_icon(squashfs_root / "graphics" / "Remote_Monitoring.png",
                      "share/icons/hicolor/128x128/apps", f"{app_id}.RemoteMonitoring.png")

        task("Installing remote monitoring entry", 0.96, add_remote_monitoring)

        def install_mime_types():
            # Install BRAW MIME types
            braw_mime_xml = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-braw-clip">
    <comment>Blackmagic RAW Clip</comment>
    <glob pattern="*.braw"/>
  </mime-type>
  <mime-type type="application/x-braw-sidecar">
    <comment>Blackmagic RAW Sidecar</comment>
    <glob pattern="*.sidecar"/>
  </mime-type>
</mime-info>
"""
            mime_packages_dir = prefix / "share" / "mime" / "packages"
            mime_packages_dir.mkdir(parents=True, exist_ok=True)
            (mime_packages_dir / "blackmagicraw.xml").write_text(braw_mime_xml)
            
            # Copy BRAW MIME icons
            for size in ["256x256", "48x48"]:
                icon_dir = prefix / "share" / "icons" / "hicolor" / size / "mimetypes"
                icon_dir.mkdir(parents=True, exist_ok=True)
                
                # BRAW clip icon
                src = squashfs_root / "graphics" / f"application-x-braw-clip_{size}_mimetypes.png"
                if src.exists():
                    shutil.copy2(src, icon_dir / "application-x-braw-clip.png")
                
                # BRAW sidecar icon
                src = squashfs_root / "graphics" / f"application-x-braw-sidecar_{size}_mimetypes.png"
                if src.exists():
                    shutil.copy2(src, icon_dir / "application-x-braw-sidecar.png")
            
            # Install Resolve MIME types
            resolve_mime_xml = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-resolveproj">
    <comment>DaVinci Resolve Project</comment>
    <glob pattern="*.drp"/>
  </mime-type>
  <mime-type type="application/x-resolvebin">
    <comment>DaVinci Resolve Bin</comment>
    <glob pattern="*.drb"/>
  </mime-type>
  <mime-type type="application/x-resolvetimeline">
    <comment>DaVinci Resolve Timeline</comment>
    <glob pattern="*.drt"/>
  </mime-type>
  <mime-type type="application/x-resolvetemplatebundle">
    <comment>DaVinci Resolve Template Bundle</comment>
    <glob pattern="*.drfx"/>
  </mime-type>
  <mime-type type="application/x-resolvedbkey">
    <comment>DaVinci Resolve Database Access Key</comment>
    <glob pattern="*.resolvedbkey"/>
  </mime-type>
</mime-info>
"""
            (mime_packages_dir / "blackmagicresolve.xml").write_text(resolve_mime_xml)
            
            # Copy Resolve MIME icons
            icon_dir = prefix / "share" / "icons" / "hicolor" / "128x128" / "mimetypes"
            icon_dir.mkdir(parents=True, exist_ok=True)
            
            mime_icons = [
                ("DV_ResolveBin.png", "application-x-resolvebin.png"),
                ("DV_ResolveProj.png", "application-x-resolveproj.png"),
                ("DV_ResolveTimeline.png", "application-x-resolvetimeline.png"),
                ("DV_TemplateBundle.png", "application-x-resolvetemplatebundle.png"),
                ("DV_ServerAccess.png", "application-x-resolvedbkey.png"),
            ]
            
            for src_name, dest_name in mime_icons:
                src = squashfs_root / "graphics" / src_name
                if src.exists():
                    shutil.copy2(src, icon_dir / dest_name)
        
        task("Installing MIME types and icons", 0.97, install_mime_types)

        def install_udev_rules():
            # Create udev rules directory
            udev_dir = prefix / "lib" / "udev" / "rules.d"
            udev_dir.mkdir(parents=True, exist_ok=True)
            
            # 75-davincipanel.rules - for DaVinci panels
            davincipanel_rules = """# DaVinci Resolve Panel USB permissions
SUBSYSTEM=="usb", ATTRS{idVendor}=="1edb", MODE="0666"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0777", GROUP="resolve"
"""
            (udev_dir / "75-davincipanel.rules").write_text(davincipanel_rules)
            
            # 75-davincikb.rules - for DaVinci keyboards
            davincikb_rules = """# DaVinci Resolve Keyboard USB permissions
SUBSYSTEMS=="usb", ENV{.LOCAL_ifNum}="$attr{bInterfaceNumber}"
# Editor Keyboard
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0b", ENV{.LOCAL_ifNum}=="04", MODE="0666"
# Speed Editor Keyboard
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0e", ENV{.LOCAL_ifNum}=="02", MODE="0666"
# Micro Color Panel
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0f", ENV{.LOCAL_ifNum}=="00", MODE="0666"
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0f", ENV{.LOCAL_ifNum}=="01", MODE="0666"
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0f", ENV{.LOCAL_ifNum}=="02", MODE="0666"
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0f", ENV{.LOCAL_ifNum}=="03", MODE="0666"
"""
            (udev_dir / "75-davincikb.rules").write_text(davincikb_rules)
            
            # 75-sdx.rules - for SDX devices
            sdx_rules = """# SDX USB permissions
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTRS{idVendor}=="096e", MODE="0666"
"""
            (udev_dir / "75-sdx.rules").write_text(sdx_rules)
        
        task("Installing udev rules", 0.98, install_udev_rules)

        def fix_permissions():
            # Common writable directories for all versions
            writable_dirs = [
                "easyDCP",
                ".license",
                "Fairlight",
            ]
            
            # Version 15 specific directories
            if major_version == 15:
                writable_dirs.extend([
                    "configs",
                    "logs",
                    ".LUT",
                    ".crashreport",
                    "DolbyVision",
                    "Media",
                    "Resolve Disk Database",
                ])
            
            # Version 20+ specific directories
            if major_version >= 20:
                writable_dirs.extend([
                    "Extras",
                    "Apple Immersive",
                ])
            
            # Version 21 specific directories
            if major_version >= 21:
                writable_dirs.append("Immersive")
            
            for rel in writable_dirs:
                directory = prefix / rel
                if directory.exists():
                    # chmod -R a+rw
                    for dirpath, dirnames, filenames in os.walk(directory):
                        for name in dirnames + filenames:
                            path = Path(dirpath) / name
                            try:
                                os.chmod(path, os.stat(path).st_mode | 0o666)
                            except OSError:
                                pass
                    # Also chmod the directory itself
                    try:
                        os.chmod(directory, os.stat(directory).st_mode | 0o777)
                    except OSError:
                        pass

        task("Fixing directory permissions", 0.99, fix_permissions)

        report("Installation complete.", 1.0)
        return True
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
