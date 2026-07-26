#!/bin/sh
####
# Build DaVinci Resolve in a Flatpak
#
# This script leverages heavily on work from makeresolvedeb, with great thanks:
# https://www.danieltufvesson.com/makeresolvedeb
####
PREFIX='/app'
STUDIO=false

usage() {
    printf 'Usage: %s [ -s | --studio ] [ -p | --prefix PREFIX ]\n' "$0"
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        -s|--studio) STUDIO=true; shift ;;
        -p|--prefix) PREFIX="$2"; shift 2 ;;
        --beta) shift ;;
        --) shift; break ;;
        *) usage ;;
    esac
done

APP_ID="com.blackmagic.Resolve"
APP_DESCRIPTION="DaVinci Resolve"
if [ "$STUDIO" = true ]; then
    APP_ID="com.blackmagic.ResolveStudio"
    APP_DESCRIPTION="DaVinci Resolve Studio"
fi

printf 'Building %s\n' "${APP_ID}"

./DaVinci_Resolve_*_Linux.run --appimage-extract 2>&1
find squashfs-root -type f -exec chmod a+r,u+w {} \;
find squashfs-root -type d -exec chmod a+rx,u+w {} \;

# Create directories
mkdir -p \
    "${PREFIX}/easyDCP" \
    "${PREFIX}/scripts" \
    "${PREFIX}/share" \
    "${PREFIX}/Fairlight" \
    "${PREFIX}/share/applications" \
    "${PREFIX}/share/icons/hicolor/128x128/apps" \
    "${PREFIX}/share/icons/hicolor/256x256/apps" \
    "${PREFIX}/Apple Immersive/Calibration" \
    "${PREFIX}/Extras" \
    "${PREFIX}/IOPlugins"
chmod 755 \
    "${PREFIX}/easyDCP" \
    "${PREFIX}/scripts" \
    "${PREFIX}/share" \
    "${PREFIX}/Fairlight" \
    "${PREFIX}/share/applications" \
    "${PREFIX}/share/icons/hicolor/128x128/apps" \
    "${PREFIX}/share/icons/hicolor/256x256/apps" \
    "${PREFIX}/Apple Immersive/Calibration" \
    "${PREFIX}/Extras" \
    "${PREFIX}/IOPlugins"

# Copy objects
cp -rp squashfs-root/bin "${PREFIX}/"
cp -rp squashfs-root/Control "${PREFIX}/"
cp -rp squashfs-root/Certificates "${PREFIX}/"
cp -rp "squashfs-root/DaVinci Control Panels Setup" "${PREFIX}/"
cp -rp squashfs-root/Developer "${PREFIX}/"
cp -rp squashfs-root/docs "${PREFIX}/"
cp -rp "squashfs-root/Fairlight Studio Utility" "${PREFIX}/"
cp -rp squashfs-root/Fusion "${PREFIX}/"
cp -rp squashfs-root/graphics "${PREFIX}/"

# https://www.reddit.com/r/Fedora/comments/12z32r1/davinci_resolve_libpango_undefined_symbol_g/
rm squashfs-root/libs/libglib*
rm squashfs-root/libs/libgio*
rm squashfs-root/libs/libgmodule*
rm squashfs-root/libs/libgobject*
cp -rp squashfs-root/libs "${PREFIX}/"

cp -rp squashfs-root/LUT "${PREFIX}/"
cp -rp squashfs-root/Onboarding "${PREFIX}/"
cp -rp squashfs-root/plugins "${PREFIX}/"
cp -rp "squashfs-root/Technical Documentation" "${PREFIX}/"
cp -rp squashfs-root/UI_Resource "${PREFIX}/"
cp -rp squashfs-root/scripts/script.checkfirmware "${PREFIX}/scripts/"
cp -rp squashfs-root/scripts/script.getlogs.v4 "${PREFIX}/scripts/"
cp -rp squashfs-root/scripts/script.start "${PREFIX}/scripts/"
cp -rp squashfs-root/share/default-config.dat "${PREFIX}/share/"
cp -rp squashfs-root/share/default_cm_config.bin "${PREFIX}/share/"
cp -rp squashfs-root/share/log-conf.xml "${PREFIX}/share/"
if [ -e squashfs-root/share/remote-monitoring-log-conf.xml ]; then
    cp -rp squashfs-root/share/remote-monitoring-log-conf.xml "${PREFIX}/share/"
fi

tar -xzvf squashfs-root/share/panels/dvpanel-framework-linux-x86_64.tgz -C "${PREFIX}/libs" libDaVinciPanelAPI.so libFairlightPanelAPI.so

# Quiet some errors
mkdir -p "${PREFIX}/bin/BlackmagicRawAPI/"
ln -s ../libs/libBlackmagicRawAPI.so "${PREFIX}/bin/libBlackmagicRawAPI.so"
ln -s ../../libs/libBlackmagicRawAPI.so "${PREFIX}/bin/BlackmagicRawAPI/libBlackmagicRawAPI.so"

if [ -e squashfs-root/BlackmagicRAWPlayer ]; then
    printf 'Adding RAWPlayer\n'
    cp -rp squashfs-root/BlackmagicRAWPlayer "${PREFIX}"
    cat <<EOF > "${PREFIX}/share/applications/${APP_ID}.RAWPlayer.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Blackmagic RAW Player
Exec=/app/BlackmagicRAWPlayer/BlackmagicRAWPlayer
Icon=${APP_ID}.RAWPlayer
Terminal=false
MimeType=application/x-braw-clip;application/x-braw-sidecar
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -p squashfs-root/graphics/blackmagicraw-player_256x256_apps.png "${PREFIX}/share/icons/hicolor/256x256/apps/${APP_ID}.RAWPlayer.png"
fi

if [ -e squashfs-root/BlackmagicRAWSpeedTest ]; then
    printf 'Adding BlackmagicRAWSpeedTest\n'
    cp -rp squashfs-root/BlackmagicRAWSpeedTest "${PREFIX}"
    cat <<EOF > "${PREFIX}/share/applications/${APP_ID}.RAWSpeedTest.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Blackmagic RAW Speed Test
Exec=/app/BlackmagicRAWSpeedTest/BlackmagicRAWSpeedTest
Icon=${APP_ID}.RAWSpeedTest
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -p squashfs-root/graphics/blackmagicraw-speedtest_256x256_apps.png "${PREFIX}/share/icons/hicolor/256x256/apps/${APP_ID}.RAWSpeedTest.png"
fi

cat <<EOF > "${PREFIX}/share/applications/${APP_ID}.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=${APP_DESCRIPTION}
Name[en_US]=${APP_DESCRIPTION}
GenericName=${APP_DESCRIPTION}
Comment=Revolutionary new tools for editing, visual effects, color correction and professional audio post production, all in a single application!
Exec=/app/bin/resolve.sh %U
Icon=${APP_ID}
Terminal=false
MimeType=application/x-resolveproj;
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
cp -rp squashfs-root/graphics/DV_Resolve.png "${PREFIX}/share/icons/hicolor/128x128/apps/${APP_ID}.png"

if [ -e "${PREFIX}/DaVinci Control Panels Setup/DaVinci Control Panels Setup" ]; then
    cat <<EOF > "${PREFIX}/share/applications/${APP_ID}.PanelSetup.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Resolve Panels Setup
Exec=/app/DaVinci Resolve Panels Setup/DaVinci Resolve Panels Setup
Icon=${APP_ID}.PanelSetup
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -rp squashfs-root/graphics/DV_Panels.png "${PREFIX}/share/icons/hicolor/128x128/apps/${APP_ID}.PanelSetup.png"
fi

if [ -e "${PREFIX}/bin/DaVinci Remote Monitoring" ]; then
    cat <<EOF > "${PREFIX}/share/applications/${APP_ID}.RemoteMonitoring.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Remote Monitoring
Exec=/app/bin/DaVinci Remote Monitoring
Icon=${APP_ID}.RemoteMonitoring
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -rp squashfs-root/graphics/Remote_Monitoring.png "${PREFIX}/share/icons/hicolor/128x128/apps/${APP_ID}.RemoteMonitoring.png"
fi
