"""Blackmagic Design API interactions for DaVinci Resolve installer."""

import json
import re
import time
from pathlib import Path

import requests

from config import COOKIES, DOWNLOAD_DATA, HEADERS


def get_latest_version_information(app_tag: str, report, refer_id: str = '77ef91f67a9e411bbbe299e595b4cfcc', stable=True):
    """Fetch the latest version information from Blackmagic Design API.
    
    Args:
        app_tag: Product tag (e.g., 'davinci-resolve' or 'davinci-resolve-studio')
        report: Progress callback function(text, fraction)
        refer_id: Blackmagic download page reference ID
        stable: If True, fetch stable version; if False, fetch latest (including beta)
    
    Returns:
        Tuple of (version_dict, release_id, download_id)
    """
    report("Resolving latest version", 0.25)
    response: requests.Response = requests.get(
        f"https://www.blackmagicdesign.com/api/support/latest-stable-version/{app_tag}/linux"
        if stable else
        f"https://www.blackmagicdesign.com/api/support/latest-version/{app_tag}/linux",
        cookies=COOKIES,
        headers={
            **HEADERS,
            'Referer': 'https://www.blackmagicdesign.com/support/download/' + refer_id + '/Linux',
        },
    )

    report("Parsing response", 0.75)
    parsed_response = json.loads(response.content.decode('utf-8'))

    report("Finished", 1.0)
    version = {
        "major": parsed_response["linux"]["major"],
        "minor": parsed_response["linux"]["minor"],
        "patch": parsed_response["linux"]["releaseNum"],
        "build": parsed_response["linux"]["build"],
        "beta": parsed_response["linux"]["beta"] if "beta" in parsed_response["linux"] else -1
    }
    return (version, parsed_response["linux"]["releaseId"], parsed_response["linux"]["downloadId"])


def resolve_download_id_to_url(download_id, report, refer_id: str = '77ef91f67a9e411bbbe299e595b4cfcc'):
    """Convert a download ID to an actual download URL.
    
    Args:
        download_id: The download ID from Blackmagic
        report: Progress callback function(text, fraction)
        refer_id: Blackmagic download page reference ID
    
    Returns:
        The actual download URL as a string
    """
    report("Submitting form and resolving download link", 0.25)

    download_url_response = requests.post(
        'https://www.blackmagicdesign.com/api/register/us/download/' + download_id,
        cookies=COOKIES,
        headers={
            **HEADERS,
            "Referer": "https://www.blackmagicdesign.com/support/download/" + refer_id + "/Linux",
        },
        data=json.dumps(DOWNLOAD_DATA),
    )

    report("Download link obtained", 1.0)
    return download_url_response.content.decode('utf-8')


def list_downloads(app_tag: str, refer_id: str = '77ef91f67a9e411bbbe299e595b4cfcc'):
    """List all available downloads for the specified product.

    Queries the Blackmagic Design support API and prints, for every Linux
    release of the requested product, one line per download:

        <downloadId>  <downloadTitle>  <date>

    Columns are tab separated so the output can be fed to other tools.
    """
    referer = f"https://www.blackmagicdesign.com/support/download/{refer_id}/Linux"
    response = requests.get(
        'https://www.blackmagicdesign.com/api/support/en/downloads.json',
        headers={
            'Accept': 'application/json, text/plain, */*',
            'Referer': referer,
            'User-Agent': HEADERS['User-Agent'],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    for entry in data.get('downloads', []):
        date = entry.get('date', '')
        for url_entry in entry.get('urls', {}).get('Linux', []):
            if url_entry.get('product') == app_tag:
                download_id = url_entry.get('downloadId', '')
                download_title = url_entry.get('downloadTitle', '')
                print(f"{download_id}\t{download_title}\t{date}")


def get_version_file_path(prefix):
    """Return the path to the version tracking file."""
    return Path(prefix) / "share" / "davinci-resolve-version.json"


def save_version_info(prefix, version_info, download_id):
    """Save version information to disk."""
    version_file = get_version_file_path(prefix)
    version_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": version_info,
        "download_id": download_id,
        "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(version_file, "w") as f:
        json.dump(data, f, indent=2)


def load_version_info(prefix):
    """Load version information from disk. Returns None if not found."""
    version_file = get_version_file_path(prefix)
    if not version_file.exists():
        return None
    with open(version_file) as f:
        return json.load(f)


def versions_match(v1, v2):
    """Compare two version dicts. Returns True if major.minor.patch match."""
    return (v1["major"] == v2["major"] and 
            v1["minor"] == v2["minor"] and 
            v1["patch"] == v2["patch"])


def lookup_version_from_download_id(download_id, app_tag, refer_id: str = '77ef91f67a9e411bbbe299e595b4cfcc'):
    """Look up version information for a specific download_id.
    
    Queries downloads.json and parses the version from the download title.
    Returns a version dict or None if not found.
    """
    referer = f"https://www.blackmagicdesign.com/support/download/{refer_id}/Linux"
    response = requests.get(
        'https://www.blackmagicdesign.com/api/support/en/downloads.json',
        headers={
            'Accept': 'application/json, text/plain, */*',
            'Referer': referer,
            'User-Agent': HEADERS['User-Agent'],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    
    # Find the entry with matching downloadId
    for entry in data.get('downloads', []):
        for url_entry in entry.get('urls', {}).get('Linux', []):
            if url_entry.get('product') == app_tag and url_entry.get('downloadId') == download_id:
                # Parse version from title like "DaVinci Resolve 21.1" or "DaVinci Resolve Studio 20.3.3"
                title = url_entry.get('downloadTitle', '')
                match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', title)
                if match:
                    major = int(match.group(1))
                    minor = int(match.group(2))
                    patch = int(match.group(3)) if match.group(3) else 0
                    return {
                        "major": major,
                        "minor": minor,
                        "patch": patch,
                        "build": 0,
                        "beta": -1
                    }
    return None
