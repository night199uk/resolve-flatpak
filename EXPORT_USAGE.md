# Export Usage Guide

The `--export-flatpak-resources` option automatically downloads and extracts all necessary resources from the DaVinci Resolve installer.

## What It Does

When you run the export command, it will:

1. **Download the latest installers** from Blackmagic Design
2. **Extract the installers** (handles both .zip and .run formats)
3. **Export desktop files** to `desktop/` directory
4. **Export MIME types** to `mime/` directory  
5. **Export icons** to `icons/` directory with proper hicolor structure

## Usage

### Export Latest Version

```bash
python3 installer/main.py --export-flatpak-resources .
```

### Export Specific Version

```bash
python3 installer/main.py --export-flatpak-resources . --prefix /app --download_id <id>
```

## Output Structure

After running the export, your repository will have:

```
.
├── desktop/
│   ├── com.blackmagic.Resolve.desktop
│   ├── com.blackmagic.Resolve.RAWPlayer.desktop
│   ├── com.blackmagic.Resolve.RAWSpeedTest.desktop
│   ├── com.blackmagic.Resolve.PanelSetup.desktop
│   └── com.blackmagic.Resolve.RemoteMonitoring.desktop
├── mime/
│   ├── blackmagicraw.xml
│   └── blackmagicresolve.xml
└── icons/
    └── hicolor/
        ├── 128x128/
        │   ├── apps/
        │   │   ├── com.blackmagic.Resolve.png
        │   │   └── com.blackmagic.Resolve.PanelSetup.png
        │   └── mimetypes/
        │       ├── application-x-resolvebin.png
        │       ├── application-x-resolvedbkey.png
        │       ├── application-x-resolveproj.png
        │       ├── application-x-resolvetemplatebundle.png
        │       └── application-x-resolvetimeline.png
        ├── 256x256/
        │   ├── apps/
        │   │   ├── com.blackmagic.Resolve.RAWPlayer.png
        │   │   └── com.blackmagic.Resolve.RAWSpeedTest.png
        │   └── mimetypes/
        │       ├── application-x-braw-clip.png
        │       └── application-x-braw-sidecar.png
        └── 48x48/
            └── mimetypes/
                ├── application-x-braw-clip.png
                └── application-x-braw-sidecar.png
```

## Building the Flatpak

After exporting resources, you can build the Flatpak:

```bash
# Build free version
flatpak-builder --user --install --force-clean build-dir com.blackmagic.Resolve.meta.yaml

# Build Studio version
flatpak-builder --user --install --force-clean build-dir com.blackmagic.ResolveStudio.meta.yaml
```

## Notes

- Extraction requires `unsquashfs` (from squashfs-tools package)
- Temporary files are automatically cleaned up
- The installer is cached in `~/Downloads/` for reuse
- Desktop files reference `/app/bin/installer.py` as the executable
