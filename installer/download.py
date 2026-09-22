"""Download functionality for DaVinci Resolve installer."""

import requests

from config import CHUNK_SIZE


def download_file(url, dest, report, cancel_event):
    """Stream `url` to `dest`, reporting 0..1 progress on the way.
    
    Args:
        url: The URL to download from
        dest: Path object for the destination file
        report: Progress callback function(text, fraction)
        cancel_event: threading.Event that can be set to cancel the download
    
    Returns:
        True if download completed successfully, False if cancelled
    """
    if dest.exists():
        dest.unlink()

    report("Downloading ... connecting", 0.0)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0

        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if cancel_event.is_set():
                    return False
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)

                if total:
                    frac = downloaded / total
                    text = f"Downloading ... {downloaded / (1024 * 1024):.1f} MiB of {total / (1024 * 1024):.1f} MiB"
                else:
                    frac = None  # server gave no size -> indeterminate bar
                    text = f"Downloading ... {downloaded / (1024 * 1024):.1f} MiB"
                report(text, frac)

    report("Download finished.", 1.0)
    return True
