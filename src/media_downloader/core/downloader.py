import os
import re
import json
import urllib.parse
import requests
import logging

logger = logging.getLogger(__name__)

def download_file(url: str, filepath: str, referer: str = 'https://www.instagram.com/') -> None:
    """Downloads a media file from a CDN URL using requests."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer
    }
    logger.info(f"Downloading file from: {url[:80]}...")
    logger.debug(f"Saving to: {filepath}")
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"Saved file: {filepath}")

def extract_url_digits(url: str) -> str:
    """Extracts the numerical digits segment of the filename from a CDN URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed.path)
        base, _ = os.path.splitext(filename)
        digits = re.findall(r'\d+', base)
        if digits:
            return "_".join(digits)
    except Exception:
        pass
    return ""

def is_cdn_media_url(url: str) -> bool:
    """Returns True if the URL points to a Meta CDN media asset."""
    if not url:
        return False
    if "static.cdninstagram.com" in url or "/rsrc.php" in url:
        return False
    return any(d in url for d in (
        "scontent", "cdninstagram", "fbcdn.net", "fbsbx.com",
    ))

def deduplicate_by_cdn_path(urls: list[str]) -> list[str]:
    """Deduplicate URLs by their CDN path."""
    seen_paths: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        path = urllib.parse.urlparse(url).path
        if path not in seen_paths:
            seen_paths.add(path)
            deduped.append(url)
        else:
            logger.info(f"Deduplicated: {url[:80]}...")
    return deduped

def build_filename(url: str, post_id: str, index: int, suffix: str = None, is_video: bool = False) -> str:
    """Builds a deterministic filename for the downloaded asset."""
    parsed = urllib.parse.urlparse(url)
    original_name = os.path.basename(parsed.path)
    base, ext = os.path.splitext(original_name)
    
    if not ext:
        ext = ".mp4" if (".mp4" in url.lower() or is_video) else ".jpg"

    digits = re.findall(r'\d+', base)
    base = "_".join(digits) if digits else f"{post_id}_{index}"

    if suffix:
        clean_suffix = re.sub(r'[\\/*?:"<>|]', "", suffix)
        base = f"{base}{clean_suffix}"

    return f"{base}{ext}"

def write_metadata(download_dir: str, metadata: dict) -> str:
    """Writes metadata dictionary to a JSON file."""
    metadata_file = os.path.join(download_dir, "metadata.json")
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    return metadata_file
