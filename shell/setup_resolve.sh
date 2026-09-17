#!/bin/bash
####
# Build DaVinci Resolve in a Flatpak
#
# This script leverages heavily on work from makeresolvedeb, with great thanks:
# https://www.danieltufvesson.com/makeresolvedeb
####
PREFIX='/app/extra'
STUDIO=false

usage()
{
  echo "Usage: $0 [ -s | --studio ] [ -p | --prefix PREFIX ]"
  exit 2
}

PARSED_ARGUMENTS=$(getopt -a -n setup_resolve.sh -o sp: --long studio,prefix: -- "$@")
VALID_ARGUMENTS=$?
if [ "$VALID_ARGUMENTS" != "0" ]; then
  usage
fi

eval set -- "$PARSED_ARGUMENTS"
while :
do
  case "$1" in
    -s | --studio)  STUDIO=true ; shift   ;;
    -p | --prefix)  PREFIX="$2" ; shift 2 ;;
    --) shift; break ;;
    *) echo "Unexpected option: $1 - this should not happen."
       usage ;;
  esac
done

APP_ID="com.blackmagic.Resolve"
APP_DESCRIPTION="DaVinci Resolve"
if [ "${STUDIO}" = true ] ; then
  APP_ID="com.blackmagic.ResolveStudio"
  APP_DESCRIPTION="DaVinci Resolve Studio"
fi

echo "Building ${APP_ID}"
unappimage ./DaVinci_Resolve_*_Linux.run
rm DaVinci_Resolve_*_Linux.run
mv squashfs-root/* "${PREFIX}"

# For extension points
mkdir -p "${PREFIX}/IOPlugins"
chmod 755 "${PREFIX}/IOPlugins"

tar -xzvf share/panels/dvpanel-framework-linux-x86_64.tgz -C "${PREFIX}/libs" libDaVinciPanelAPI.so libFairlightPanelAPI.so

# Quiet some errors
mkdir -p "${PREFIX}/Apple Immersive/Calibration" "${PREFIX}/Immersive/Canon/STMap"
mkdir -p "${PREFIX}/bin/BlackmagicRawAPI/"
cp "${PREFIX}/libs/libBlackmagicRawAPI.so" "${PREFIX}/bin/libBlackmagicRawAPI.so"
#ln -s "${PREFIX}/libs/libBlackmagicRawAPI.so" "${PREFIX}/bin/libBlackmagicRawAPI.so"
#ln -s ../../libs/libBlackmagicRawAPI.so "${PREFIX}/bin/BlackmagicRawAPI/libBlackmagicRawAPI.so"

EXPORT_DIR="/app/extra/export"
mkdir -p "${EXPORT_DIR}/share/applications" "${EXPORT_DIR}/share/icons/hicolor/256x256/apps" "${EXPORT_DIR}/share/icons/hicolor/128x128/apps"

if [[ -e BlackmagicRAWPlayer ]]; then
    echo "Adding RAWPlayer"

    cp -rp BlackmagicRAWPlayer ${PREFIX}
    cat <<EOF > "${EXPORT_DIR}/share/applications/${APP_ID}.RAWPlayer.desktop"
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
    cp -p "graphics/blackmagicraw-player_256x256_apps.png" "${EXPORT_DIR}/share/icons/hicolor/256x256/apps/${APP_ID}.RAWPlayer.png"
fi
if [[ -e squashfs-root/BlackmagicRAWSpeedTest ]]; then
    echo "Adding BlackmagicRAWSpeedTest"

    cat <<EOF > "${EXPORT_DIR}/share/applications/${APP_ID}.RAWSpeedTest.desktop"
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
    cp -p graphics/blackmagicraw-speedtest_256x256_apps.png "${EXPORT_DIR}/share/icons/hicolor/256x256/apps/${APP_ID}.RAWSpeedTest.png"
fi

####
# Create udev rules
#
# Figure out how to do this under Flatpak
#
####
#mkdir -p ${PREFIX}/lib/udev/rules.d
#chmod 755 ${PREFIX}/lib/udev/rules.d
#cat > ${PREFIX}/lib/udev/rules.d/75-davincipanel.rules <<EOF
#SUBSYSTEM=="usb", ATTRS{idVendor}=="1edb", MODE="0666"
#EOF
#cat > ${PREFIX}/lib/udev/rules.d/75-davincikb.rules <<EOF
#SUBSYSTEMS=="usb", ENV{.LOCAL_ifNum}="\$attr{bInterfaceNumber}"
# Editor Keyboard
#SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0b", ENV{.LOCAL_ifNum}=="04", MODE="0666"
# Speed Editor Keyboard
#SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0e", ENV{.LOCAL_ifNum}=="02", MODE="0666"
#EOF
#cat > ${PREFIX}/lib/udev/rules.d/75-sdx.rules <<EOF
#SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTRS{idVendor}=="096e", MODE="0666"
#EOF


cat <<EOF > "${EXPORT_DIR}/share/applications/${APP_ID}.desktop"
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
cp -rp graphics/DV_Resolve.png "${EXPORT_DIR}/share/icons/hicolor/128x128/apps/${APP_ID}.png"

# if [[ -e "${PREFIX}/DaVinci Resolve Panels Setup/DaVinci Resolve Panels Setup" ]]; then
#     cat << EOF > ${PREFIX}/share/applications/${APP_ID}.PanelSetup.desktop
# [Desktop Entry]
# Version=1.0
# Type=Application
# Name=DaVinci Resolve Panels Setup
# Exec="/app/DaVinci Resolve Panels Setup/DaVinci Resolve Panels Setup"
# Icon=${APP_ID}.PanelSetup
# Terminal=false
# StartupNotify=true
# Categories=AudioVideo
# EOF
#     cp -rp graphics/DV_Panels.png "${EXPORT_DIR}/share/icons/hicolor/128x128/apps/${APP_ID}.PanelSetup.png"
# fi
if [[ -e "${PREFIX}/DaVinci Control Panels Setup/DaVinci Control Panels Setup" ]]; then
    cat <<EOF > "${EXPORT_DIR}/share/applications/${APP_ID}.PanelSetup.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Resolve Panels Setup
Exec="/app/DaVinci Resolve Panels Setup/DaVinci Resolve Panels Setup"
Icon=${APP_ID}.PanelSetup
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -rp graphics/DV_Panels.png "${EXPORT_DIR}/share/icons/hicolor/128x128/apps/${APP_ID}.PanelSetup.png"
fi
if [[ -e "${PREFIX}/bin/DaVinci Remote Monitoring" ]]; then
    cat <<EOF > "${EXPORT_DIR}/share/applications/${APP_ID}.RemoteMonitoring.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=DaVinci Remote Monitoring
Exec="/app/bin/DaVinci Remote Monitoring"
Icon=${APP_ID}.RemoteMonitoring
Terminal=false
StartupNotify=true
Categories=AudioVideo
PrefersNonDefaultGPU=true
EOF
    cp -rp graphics/Remote_Monitoring.png "${EXPORT_DIR}/share/icons/hicolor/128x128/apps/${APP_ID}.RemoteMonitoring.png"
fi
