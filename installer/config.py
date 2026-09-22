"""Configuration constants for DaVinci Resolve installer."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration - adjust these for your real use case
# ---------------------------------------------------------------------------
APP_NAME = "DaVinci Resolve"
APP_TAG = "davinci-resolve"
WANT_BETA = False

# Where the downloaded file is saved.
DEST_DIR = Path.home() / "Downloads"

# Where the .run payload is installed to.
# In Flatpak, /app is read-only, so we install to the user's data directory.
# This will be overridden by main.py based on the app-id.
INSTALL_PREFIX = Path.home() / ".var" / "app" / "com.blackmagic.Resolve" / "data"

STUDIO = False
DOWNLOAD_ID = None

CHUNK_SIZE = 512 * 1024  # 64 KiB

STEPS = ["Finding Latest Version", "Resolving Download URL", "Downloading file", "Installing application", "Complete"]

DOWNLOAD_DATA = {
    "firstname": "Flatpak",
    "lastname": "Builder",
    "email": "someone@flathub.org",
    "phone": "202-555-0194",
    "country": "us",
    "state": "New York",
    "city": "FPK",
    "street": "Bowery 146",
    "product": "DaVinci Resolve"
}

COOKIES = {
    '_ga': 'GA1.2.1849503966.1518103294',
    '_gid': 'GA1.2.953840595.1518103294',
}

HEADERS = {
    'Host': 'www.blackmagicdesign.com',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.blackmagicdesign.com',
    'User-Agent': "Mozilla/5.0 (X11; Linux) \
        AppleWebKit/537.36 (KHTML, like Gecko) \
        Chrome/77.0.3865.75 \
        Safari/537.36",
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Authority': 'www.blackmagicdesign.com',
    'Cookie': '_ga=GA1.2.1849503966.1518103294; _gid=GA1.2.953840595.1518103294',
}
