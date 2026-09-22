#!/bin/bash
# Build script for DaVinci Resolve Meta-Flatpak

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}DaVinci Resolve Meta-Flatpak Builder${NC}"
echo "=================================="
echo

# Check if flatpak-builder is installed
if ! command -v flatpak-builder &> /dev/null; then
    echo -e "${RED}Error: flatpak-builder is not installed${NC}"
    echo "Please install it with: sudo dnf install flatpak-builder"
    exit 1
fi

# Check if required runtimes are installed
if ! flatpak list --app --columns=application | grep -q "org.freedesktop.Platform"; then
    echo -e "${YELLOW}Warning: freedesktop runtime may not be installed${NC}"
    echo "Install with: flatpak install flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08"
fi

# Parse command line arguments
INSTALL=false
EXPORT=false
REPO_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --install)
            INSTALL=true
            shift
            ;;
        --export)
            EXPORT=true
            REPO_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Options:"
            echo "  --install    Install the Flatpak after building"
            echo "  --export DIR Export to a Flatpak repository"
            echo "  --help       Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Clean previous build
echo -e "${YELLOW}Cleaning previous build...${NC}"
rm -rf .build-dir

# Build the Flatpak
echo -e "${GREEN}Building meta-Flatpak...${NC}"
if [ "$INSTALL" = true ]; then
    flatpak-builder --user --install --force-clean .build-dir com.blackmagic.Resolve.meta.yaml
elif [ "$EXPORT" = true ]; then
    if [ -z "$REPO_DIR" ]; then
        echo -e "${RED}Error: --export requires a repository directory${NC}"
        exit 1
    fi
    flatpak-builder --repo="$REPO_DIR" --force-clean .build-dir com.blackmagic.Resolve.meta.yaml
else
    flatpak-builder --force-clean .build-dir com.blackmagic.Resolve.meta.yaml
fi

echo
echo -e "${GREEN}Build completed successfully!${NC}"
echo

if [ "$INSTALL" = true ]; then
    echo "The Flatpak has been installed. You can launch it with:"
    echo "  flatpak run com.blackmagic.Resolve"
elif [ "$EXPORT" = true ]; then
    echo "The Flatpak has been exported to: $REPO_DIR"
    echo "To install from the repository:"
    echo "  flatpak --user remote-add --if-not-exists resolve-repo $REPO_DIR"
    echo "  flatpak --user install resolve-repo com.blackmagic.Resolve"
else
    echo "To install the Flatpak:"
    echo "  flatpak-builder --user --install .build-dir com.blackmagic.Resolve.meta.yaml"
    echo
    echo "Or to export to a repository:"
    echo "  flatpak-builder --repo=repo .build-dir com.blackmagic.Resolve.meta.yaml"
fi
