"""Export Flatpak resources (desktop files, icons, MIME types) for meta-Flatpak packaging."""

import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib
import zipfile
from pathlib import Path

import requests

import config
from api import get_latest_version_information, resolve_download_id_to_url
from download import download_file
from install import _find_squashfs_offset


def export_flatpak_resources(repo_dir, prefix=None, download_id=None):
    """Export desktop files, icons, and MIME types for Flatpak packaging.
    
    Downloads the latest DaVinci Resolve installer, extracts icons, and exports
    all resources directly to the repository structure. This exports for both
    Resolve and Resolve Studio versions.
    
    Args:
        repo_dir: Repository root directory (desktop/, mime/, icons/ will be created here)
        prefix: Installation prefix (used for path references in desktop files)
        download_id: Optional specific download ID to use instead of latest
    """
    if prefix is None:
        prefix = config.INSTALL_PREFIX
    repo_dir = Path(repo_dir)
    
    # Export for both Resolve and Resolve Studio
    for studio in [False, True]:
        app = "resolve-studio.py" if studio else "resolve.py"
        app_id = "com.blackmagic.ResolveStudio" if studio else "com.blackmagic.Resolve"
        app_description = "DaVinci Resolve Studio" if studio else "DaVinci Resolve"
        app_tag = "davinci-resolve-studio" if studio else "davinci-resolve"
        prefix = Path(prefix)
        
        print(f"\n{'='*60}")
        print(f"Exporting resources for {app_description}...")
        print(f"{'='*60}")
        
        # Step 1: Download the installer
        print("\n[1/5] Downloading DaVinci Resolve installer...")
        installer_path = _download_installer(app_tag, prefix, download_id)
        
        # Step 2: Extract the installer
        print("\n[2/5] Extracting installer...")
        extract_dir = _extract_installer(installer_path)
        
        try:
            # Step 3: Export desktop files and MIME types
            print("\n[3/5] Exporting desktop files and MIME types...")
            _export_desktop_and_mime(repo_dir, app, app_id, app_description, prefix, studio)
            
            # Step 4: Export icons
            print("\n[4/5] Exporting icons...")
            _export_icons(repo_dir, extract_dir, app_id)
            
            # Step 5: Build metainfo
            print("\n[5/5] Building metainfo...")
            _build_metainfo(repo_dir, app_id, app_description, app_tag)
            
        finally:
            # Clean up extracted directory
            print("\nCleaning up temporary files...")
            shutil.rmtree(extract_dir, ignore_errors=True)
    
    print(f"\n{'='*60}")
    print(f"✓ Successfully exported all resources to {repo_dir}")
    print(f"  - Desktop files: {repo_dir / 'desktop'}")
    print(f"  - MIME types: {repo_dir / 'mime'}")
    print(f"  - Icons: {repo_dir / 'icons'}")
    print(f"  - Metainfo: {repo_dir / 'metainfo'}")
    print(f"{'='*60}")


def _download_installer(app_tag, prefix, download_id=None):
    """Download the DaVinci Resolve installer."""
    if download_id:
        print(f"  Using specified download ID: {download_id}")
        final_url = resolve_download_id_to_url(download_id, lambda t, f: None)
    else:
        print("  Fetching latest version information...")
        version, _, download_id = get_latest_version_information(
            app_tag,
            lambda t, f: None,
            stable=not config.WANT_BETA
        )
        print(f"  Latest version: {version['major']}.{version['minor']}.{version['patch']}")
        print(f"  Download ID: {download_id}")
        final_url = resolve_download_id_to_url(download_id, lambda t, f: None)
    
    # Determine filename from URL
    name = urllib.parse.unquote(urllib.parse.urlsplit(final_url).path.split("/")[-1])
    dest = config.DEST_DIR / (name or "DaVinci_Resolve_Linux.run")
    
    print(f"  Downloading to: {dest}")
    
    # Download with progress
    cancel_event = threading.Event()
    
    def progress_callback(text, fraction):
        if fraction is not None:
            percent = int(fraction * 100)
            print(f"\r  Downloading: {percent}%", end="", flush=True)
    
    if not download_file(final_url, dest, progress_callback, cancel_event):
        raise RuntimeError("Download failed or was cancelled")
    
    print(f"\n  ✓ Downloaded: {dest.name}")
    return dest


def _extract_installer(installer_path):
    """Extract the DaVinci Resolve installer (handles both .zip and .run files)."""
    extract_dir = Path(tempfile.mkdtemp(prefix="resolve-export-"))
    
    # Check if it's a zip file
    if str(installer_path).endswith('.zip'):
        print(f"  Extracting zip file...")
        with zipfile.ZipFile(installer_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Find the .run file inside
        run_files = list(extract_dir.glob('*.run'))
        if not run_files:
            raise RuntimeError("No .run file found in zip archive")
        
        run_file = run_files[0]
        print(f"  Found .run file: {run_file.name}")
        squashfs_root = extract_dir / "squashfs-root"
    else:
        # It's already a .run file
        run_file = installer_path
        squashfs_root = extract_dir / "squashfs-root"
    
    print(f"  Finding squashfs offset...")
    offset = _find_squashfs_offset(run_file)
    print(f"  Offset: {offset}")
    
    unsquashfs = shutil.which("unsquashfs")
    if unsquashfs is None:
        raise RuntimeError("unsquashfs not found in PATH (install squashfs-tools)")
    
    print(f"  Extracting with unsquashfs...")
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
    
    print(f"  ✓ Extracted to: {extract_dir}")
    return extract_dir


def _export_desktop_and_mime(repo_dir, app, app_id, app_description, prefix, studio):
    """Export desktop files and MIME type definitions."""
    desktop_dir = repo_dir / "desktop"
    mime_dir = repo_dir / "mime"
    
    desktop_dir.mkdir(parents=True, exist_ok=True)
    mime_dir.mkdir(parents=True, exist_ok=True)
    
    # The installer script path that desktop files will call (always /app/bin inside Flatpak)
    installer_path = Path("/app/bin") / app
    
    # Export main Resolve desktop file
    _write_desktop(desktop_dir / f"{app_id}.desktop",
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name={app_description}
Name[en_US]={app_description}
GenericName={app_description}
Comment=Revolutionary new tools for editing, visual effects, color correction and professional audio post production, all in a single application!
Exec={installer_path} --run-resolve %U
Icon={app_id}
Terminal=false
MimeType=application/x-resolveproj;application/x-resolvebin;application/x-resolvetimeline;application/x-resolvetemplatebundle;application/x-resolvedbkey;
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
""")
    
    # Export BRAW Player desktop file
    _write_desktop(desktop_dir / f"{app_id}.RAWPlayer.desktop",
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Blackmagic RAW Player
Exec={installer_path} --run-brawplayer %U
Icon={app_id}.RAWPlayer
Terminal=false
MimeType=application/x-braw-clip;application/x-braw-sidecar;
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
""")
    
    # Export BRAW Speed Test desktop file
    _write_desktop(desktop_dir / f"{app_id}.RAWSpeedTest.desktop",
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Blackmagic RAW Speed Test
Exec={installer_path} --run-brawspeedtest
Icon={app_id}.RAWSpeedTest
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
""")
    
    # Export Panel Setup desktop file
    _write_desktop(desktop_dir / f"{app_id}.PanelSetup.desktop",
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Resolve Panels Setup
Exec={installer_path} --run-panel-setup
Icon={app_id}.PanelSetup
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
""")
    
    # Export Remote Monitoring desktop file
    _write_desktop(desktop_dir / f"{app_id}.RemoteMonitoring.desktop",
        f"""[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Remote Monitoring
Exec={installer_path} --run-remote-monitoring
Icon={app_id}.RemoteMonitoring
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
""")
    
    # Export MIME type definitions
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
    (mime_dir / "blackmagicraw.xml").write_text(braw_mime_xml)
    
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
    (mime_dir / "blackmagicresolve.xml").write_text(resolve_mime_xml)
    
    print(f"  ✓ Desktop files: {list(desktop_dir.glob('*.desktop'))}")
    print(f"  ✓ MIME types: {list(mime_dir.glob('*.xml'))}")


def _export_icons(repo_dir, extract_dir, app_id):
    """Export icons from the extracted installer."""
    graphics_dir = extract_dir / "squashfs-root" / "graphics"
    
    if not graphics_dir.exists():
        print(f"  Warning: Graphics directory not found at {graphics_dir}")
        return
    
    # Create icon directories
    icons_base = repo_dir / "icons" / "hicolor"
    
    # Application icons (128x128 and 256x256)
    app_icons_128 = icons_base / "128x128" / "apps"
    app_icons_256 = icons_base / "256x256" / "apps"
    app_icons_128.mkdir(parents=True, exist_ok=True)
    app_icons_256.mkdir(parents=True, exist_ok=True)
    
    # MIME type icons
    mime_icons_128 = icons_base / "128x128" / "mimetypes"
    mime_icons_256 = icons_base / "256x256" / "mimetypes"
    mime_icons_48 = icons_base / "48x48" / "mimetypes"
    mime_icons_128.mkdir(parents=True, exist_ok=True)
    mime_icons_256.mkdir(parents=True, exist_ok=True)
    mime_icons_48.mkdir(parents=True, exist_ok=True)
    
    icon_count = 0
    
    # Helper function to copy icon with proper permissions
    def copy_icon(src, dst):
        if dst.exists():
            dst.chmod(0o644)
        shutil.copy2(src, dst)
    
    # Copy main application icon (DV_Resolve.png -> 128x128)
    src = graphics_dir / "DV_Resolve.png"
    if src.exists():
        copy_icon(src, app_icons_128 / f"{app_id}.png")
        icon_count += 1
        print(f"  ✓ {app_id}.png (128x128)")
    
    # Copy BRAW Player icon (256x256)
    src = graphics_dir / "blackmagicraw-player_256x256_apps.png"
    if src.exists():
        copy_icon(src, app_icons_256 / f"{app_id}.RAWPlayer.png")
        icon_count += 1
        print(f"  ✓ {app_id}.RAWPlayer.png (256x256)")
    
    # Copy BRAW Speed Test icon (256x256)
    src = graphics_dir / "blackmagicraw-speedtest_256x256_apps.png"
    if src.exists():
        copy_icon(src, app_icons_256 / f"{app_id}.RAWSpeedTest.png")
        icon_count += 1
        print(f"  ✓ {app_id}.RAWSpeedTest.png (256x256)")
    
    # Copy Panel Setup icon (128x128)
    src = graphics_dir / "DV_Panels.png"
    if src.exists():
        copy_icon(src, app_icons_128 / f"{app_id}.PanelSetup.png")
        icon_count += 1
        print(f"  ✓ {app_id}.PanelSetup.png (128x128)")
    
    # Copy Remote Monitoring icon (128x128)
    src = graphics_dir / "Remote_Monitoring.png"
    if src.exists():
        copy_icon(src, app_icons_128 / f"{app_id}.RemoteMonitoring.png")
        icon_count += 1
        print(f"  ✓ {app_id}.RemoteMonitoring.png (128x128)")
    
    # Copy MIME type icons (multiple sizes)
    mime_icon_mappings = [
        ("DV_ResolveBin.png", "application-x-resolvebin.png"),
        ("DV_ResolveProj.png", "application-x-resolveproj.png"),
        ("DV_ResolveTimeline.png", "application-x-resolvetimeline.png"),
        ("DV_TemplateBundle.png", "application-x-resolvetemplatebundle.png"),
        ("DV_ServerAccess.png", "application-x-resolvedbkey.png"),
    ]
    
    for src_name, dest_name in mime_icon_mappings:
        src = graphics_dir / src_name
        if src.exists():
            copy_icon(src, mime_icons_128 / dest_name)
            icon_count += 1
            print(f"  ✓ {dest_name} (128x128)")
    
    # BRAW MIME icons (256x256 and 48x48)
    for size, dest_dir in [("256x256", mime_icons_256), ("48x48", mime_icons_48)]:
        for mime_type in ["braw-clip", "braw-sidecar"]:
            src = graphics_dir / f"application-x-{mime_type}_{size}_mimetypes.png"
            if src.exists():
                dest_name = f"application-x-{mime_type}.png"
                copy_icon(src, dest_dir / dest_name)
                icon_count += 1
                print(f"  ✓ {dest_name} ({size})")
    
    print(f"  ✓ Total icons exported: {icon_count}")


def _build_metainfo(repo_dir, app_id, app_description, app_tag):
    """Build metainfo.xml file with release information from Blackmagic Design API."""
    metainfo_dir = repo_dir / "metainfo"
    metainfo_dir.mkdir(parents=True, exist_ok=True)
    
    # Fetch downloads.json from Blackmagic Design
    print("  Fetching release information from Blackmagic Design...")
    response = requests.get('https://www.blackmagicdesign.com/api/support/en/downloads.json')
    response.raise_for_status()
    parsed_response = response.json()
    
    latest_description = ""
    releases = ""
    
    for idx, download in enumerate(parsed_response["downloads"]):
        if "Linux" not in download["urls"] or download["urls"]["Linux"][0]["product"] != app_tag:
            continue
        
        linux = download["urls"]["Linux"][0]
        description = download["desc"]
        
        # Parse version information
        beta_match = re.compile(r'.*Beta (\d+)').match(linux["downloadTitle"])
        major = linux["major"]
        minor = linux["minor"]
        patch = linux["releaseNum"]
        build = linux["releaseId"]
        beta = -1 if beta_match is None or beta_match.group(1) == "" else int(beta_match.group(1))
        
        # Format version string
        if beta == -1:
            version_str = f"{major}.{minor}.{patch}"
        else:
            version_str = f"{major}.{minor}.{patch}.{beta}+{build}"
        
        # Parse and format date
        date = datetime.datetime.strptime(download["date"], '%d %b %Y').strftime("%Y-%m-%d")
        
        # Store latest description
        if idx == 0 or latest_description == "":
            latest_description = description
        
        # Build release entry
        release = f"""<release version="{version_str}" date="{date}">
              <description>
                 {description}
              </description>
            </release>"""
        
        releases += release
    
    # Build complete metainfo XML
    template = f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{app_id}</id>
  <metadata_license>FSFAP</metadata_license>
  <project_license>LicenseRef-proprietary</project_license>
  <name>{app_description}</name>
  <summary>Professional Editing, Color, Effects and Audio Post!</summary>

  <description>
    <p>
      {latest_description}
    </p>
  </description>

  <launchable type="desktop-id">{app_id}.desktop</launchable>

  <screenshots>
    <screenshot type="default">
      <caption>DaVinci Resolve 18 Cut Page</caption>
      <image>https://images.blackmagicdesign.com/images/products/davinciresolve/overview/onesolution/carousel/cut.jpg</image>
    </screenshot>
    <screenshot>
      <caption>DaVinci Resolve 18 Edit Page</caption>
      <image>https://images.blackmagicdesign.com/images/products/davinciresolve/overview/onesolution/carousel/edit.jpg</image>
    </screenshot>
    <screenshot>
      <caption>DaVinci Resolve 18 Color Page</caption>
      <image>https://images.blackmagicdesign.com/images/products/davinciresolve/overview/onesolution/carousel/color.jpg</image>
    </screenshot>
    <screenshot>
      <caption>DaVinci Resolve 18 Fusion Page</caption>
      <image>https://images.blackmagicdesign.com/images/products/davinciresolve/overview/onesolution/carousel/fusion.jpg</image>
    </screenshot>
    <screenshot>
      <caption>DaVinci Resolve 18 Fairlight Page</caption>
      <image>https://images.blackmagicdesign.com/images/products/davinciresolve/overview/onesolution/carousel/fairlight.jpg</image>
    </screenshot>
  </screenshots>

  <url type="homepage">https://www.blackmagicdesign.com/products/davinciresolve</url>
  <project_group>Blackmagicdesign</project_group>

  <provides>
    <binary>resolve</binary>
  </provides>

  <releases>    
    {releases}
  </releases>
</component>
"""
    
    # Write metainfo file
    metainfo_file = metainfo_dir / f"{app_id}.metainfo.xml"
    metainfo_file.write_text(template)
    print(f"  ✓ Generated metainfo: {metainfo_file.name}")


def _write_desktop(path, content):
    """Write a desktop file."""
    path.write_text(content)
