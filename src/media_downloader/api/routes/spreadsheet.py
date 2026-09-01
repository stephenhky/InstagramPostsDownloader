from fastapi import APIRouter, Request, HTTPException
from typing import Optional, List, Dict, Any
import logging
import os
import subprocess
import re
from media_downloader.core.models import (
    SpreadsheetPostItem,
    SpreadsheetSyncResponse,
    SpreadsheetDownloadPostRequest,
    SpreadsheetDownloadPendingResponse,
    SpreadsheetRenameRequest,
    SpreadsheetLocalDownloadRequest,
)
from media_downloader.core.spreadsheet import (
    read_sheet_data,
    update_row_status,
    update_row_fields,
    save_spreadsheet_metadata,
    load_all_spreadsheet_metadata,
    upload_directory_to_s3,
    normalize_row_keys,
    rename_s3_media_files,
    download_post_from_s3,
    get_s3_media_url,
    list_s3_post_files,
)
from media_downloader.platforms.instagram import InstagramDownloader
from media_downloader.platforms.threads import ThreadsDownloader

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_downloader_for_platform(platform: str):
    platform = platform.lower().strip()
    if platform == "instagram":
        return InstagramDownloader()
    elif platform == "threads":
        return ThreadsDownloader()
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def _build_s3_prefix(platform: str, identifier: str) -> str:
    """Build a consistent S3 prefix for a post."""
    return f"spreadsheet/{platform}/{identifier}"


def _find_metadata_for_row(nrow: dict, metadata_list: list) -> Optional[dict]:
    """Find metadata matching a spreadsheet row by URL, rectified_link, original_link, or post identifier."""
    link = (nrow.get("link") or "").strip().rstrip("/")
    rect_link = (nrow.get("rectified_link") or "").strip().rstrip("/")
    platform = (nrow.get("platform") or "instagram").lower().strip()

    # 1. Exact match on URL fields
    for m in metadata_list:
        m_url = (m.get("url") or "").strip().rstrip("/")
        m_orig = (m.get("original_link") or "").strip().rstrip("/")
        m_rect = (m.get("rectified_link") or "").strip().rstrip("/")
        if link and link in (m_url, m_orig, m_rect):
            return m
        if rect_link and rect_link in (m_url, m_orig, m_rect):
            return m

    # 2. Extract identifier from link / rect_link
    post_id = None
    if platform == "instagram":
        m = re.search(r"/(?:p|reel|tv)/([^/?#&]+)", link) or (re.search(r"/(?:p|reel|tv)/([^/?#&]+)", rect_link) if rect_link else None)
        if m:
            post_id = m.group(1)
    elif platform == "threads":
        m = re.search(r"/post/([^/?#&]+)", link) or (re.search(r"/post/([^/?#&]+)", rect_link) if rect_link else None)
        if m:
            post_id = m.group(1)
        elif "/share/" in link or (rect_link and "/share/" in rect_link):
            try:
                target = rect_link if (rect_link and "/share/" in rect_link) else link
                resolved = ThreadsDownloader().resolve_share_url(target)
                m2 = re.search(r"/post/([^/?#&]+)", resolved)
                if m2:
                    post_id = m2.group(1)
            except Exception:
                pass

    if post_id:
        for m in metadata_list:
            m_id = m.get("shortcode") or m.get("post_id")
            if m_id and m_id == post_id:
                return m

    return None


def _build_post_item(row: dict, metadata_list: list) -> dict:
    """Build a SpreadsheetPostItem dict from a row and metadata list."""
    nrow = normalize_row_keys(row)
    url = nrow.get("link", "")
    platform = nrow.get("platform", "instagram").lower().strip()
    meta = _find_metadata_for_row(nrow, metadata_list)

    identifier = ""
    if meta:
        identifier = meta.get("shortcode") or meta.get("post_id", "")

    s3_prefix = _build_s3_prefix(platform, identifier) if identifier else None

    # Build thumbnail URL from local or S3 media
    thumbnail_url = None
    media_files = None
    if meta and meta.get("media_files"):
        media_files = meta["media_files"]
        if identifier:
            local_dir = os.path.join("downloads", platform, identifier)
            first_file = media_files[0]
            local_path = os.path.join(local_dir, first_file)
            if os.path.exists(local_path):
                thumbnail_url = f"/downloads/{platform}/{identifier}/{first_file}"
            elif s3_prefix:
                try:
                    s3_key = f"{s3_prefix}/{first_file}"
                    thumbnail_url = get_s3_media_url(s3_key)
                except Exception:
                    pass

    status = nrow.get("status", "PENDING").upper().strip()
    if status not in ("PENDING", "S3", "RENAMED", "DOWNLOADED"):
        status = "PENDING"

    # Username: use sheet username, or fallback to meta owner_username
    username = nrow.get("username", "").strip()
    if not username and meta:
        username = meta.get("owner_username", "").strip()
    if not username and platform == "instagram":
        username = "instagram_user"

    profile_bio = meta.get("profile_bio", "") if meta else None
    caption = meta.get("caption", "") if meta else None
    profile_usernames = meta.get("profile_usernames") if meta else None
    if not profile_usernames and username:
        profile_usernames = [username]

    return {
        "datetime": nrow.get("datetime", ""),
        "link": url,
        "rectified_link": nrow.get("rectified_link") or (meta.get("rectified_link") if meta else url),
        "username": username,
        "platform": platform,
        "status": status,
        "comment": nrow.get("comment"),
        "metadata": meta,
        "profile_bio": profile_bio,
        "profile_usernames": profile_usernames,
        "caption": caption,
        "media_files": media_files,
        "thumbnail_url": thumbnail_url,
        "s3_prefix": s3_prefix,
    }


@router.post("/sync")
async def api_sync_spreadsheet(request: Request):
    """Sync data from the Google Spreadsheet.

    For PENDING rows: scrape media, upload to S3, and update status to S3.
    Returns all rows with enriched metadata.
    """
    try:
        rows = read_sheet_data()
    except Exception as e:
        logger.error(f"Failed to read spreadsheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    metadata_list = load_all_spreadsheet_metadata()

    # Process PENDING rows
    for row in rows:
        nrow = normalize_row_keys(row)
        if nrow.get("status", "").upper().strip() != "PENDING":
            continue

        url = nrow.get("link", "")
        platform = nrow.get("platform", "").lower().strip()
        rectified_link = nrow.get("rectified_link") or url

        if not url:
            continue

        try:
            downloader = _get_downloader_for_platform(platform)
        except ValueError as ve:
            logger.warning(f"Unsupported platform '{platform}' for url={url}: {ve}")
            continue

        try:
            # Resolve share URL for threads if needed
            target_download_url = rectified_link
            if platform == "threads" and hasattr(downloader, "resolve_share_url"):
                resolved = downloader.resolve_share_url(target_download_url)
                if resolved != target_download_url:
                    target_download_url = resolved

            metadata = await downloader.download_post(post_url=target_download_url, suffix=None)
            metadata["original_link"] = url
            metadata["rectified_link"] = target_download_url

            identifier = metadata.get("shortcode") or metadata.get("post_id", "unknown")
            s3_prefix = _build_s3_prefix(platform, identifier)

            download_dir = downloader.get_downloads_dir()
            post_dir = os.path.join(download_dir, identifier)

            if os.path.exists(post_dir):
                logger.info(f"Uploading {post_dir} to S3 prefix {s3_prefix}")
                upload_directory_to_s3(post_dir, s3_prefix)

            save_spreadsheet_metadata(metadata)

            try:
                update_row_fields(
                    url,
                    status="S3",
                    username=metadata.get("owner_username"),
                    rectified_link=target_download_url,
                )
            except Exception as sheet_err:
                logger.warning(f"Failed to update sheet fields for {url}: {sheet_err}")
        except Exception as e:
            logger.error(f"Failed to process pending post {url}: {e}")

    # Re-read sheet for updated statuses
    try:
        rows = read_sheet_data()
    except Exception as e:
        logger.error(f"Failed to re-read spreadsheet: {e}")

    metadata_list = load_all_spreadsheet_metadata()

    posts = []
    counts = {"PENDING": 0, "S3": 0, "RENAMED": 0, "DOWNLOADED": 0}
    for row in rows:
        post_dict = _build_post_item(row, metadata_list)
        status = post_dict["status"]
        if status in counts:
            counts[status] += 1
        posts.append(post_dict)

    return SpreadsheetSyncResponse(
        success=True,
        posts=[SpreadsheetPostItem(**p) for p in posts],
        pending_count=counts["PENDING"],
        s3_count=counts["S3"],
        renamed_count=counts["RENAMED"],
        downloaded_count=counts["DOWNLOADED"],
    )


@router.post("/download-pending")
async def api_download_pending(request: Request):
    """Download all PENDING posts to S3 and update their status to S3.

    Legacy endpoint — the /sync endpoint now handles this automatically.
    """
    try:
        rows = read_sheet_data()
        pending_rows = [r for r in rows if normalize_row_keys(r).get("status", "").upper().strip() == "PENDING"]
    except Exception as e:
        logger.error(f"Failed to read spreadsheet for pending download: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    results = []
    succeeded = 0
    failed = 0

    for row in pending_rows:
        nrow = normalize_row_keys(row)
        url = nrow.get("link", "")
        platform = nrow.get("platform", "").lower().strip()
        rectified_link = nrow.get("rectified_link") or url

        logger.info(f"Processing pending row: platform={platform}, url={url}, rectified={rectified_link}")

        if not url:
            logger.warning("Skipping row with empty URL.")
            results.append({"url": url, "success": False, "error": "Empty URL"})
            failed += 1
            continue

        try:
            downloader = _get_downloader_for_platform(platform)
        except ValueError as ve:
            logger.warning(f"Unsupported platform '{platform}' for url={url}: {ve}")
            results.append({"url": url, "success": False, "error": str(ve)})
            failed += 1
            continue

        try:
            metadata = await downloader.download_post(post_url=rectified_link, suffix=None)
            identifier = metadata.get("shortcode") or metadata.get("post_id", "unknown")
            s3_prefix = _build_s3_prefix(platform, identifier)
            download_dir = downloader.get_downloads_dir()
            post_dir = os.path.join(download_dir, identifier)
            logger.info(f"Post {identifier} downloaded to {post_dir}")

            if os.path.exists(post_dir):
                logger.info(f"Uploading {post_dir} to S3 prefix {s3_prefix}")
                upload_directory_to_s3(post_dir, s3_prefix)

            save_spreadsheet_metadata(metadata)

            try:
                update_row_status(url, "S3")
            except Exception as sheet_err:
                logger.warning(f"Failed to update sheet status for {url}: {sheet_err}")

            results.append({"url": url, "success": True, "data": metadata})
            succeeded += 1
        except Exception as e:
            logger.error(f"Failed to download pending post {url}: {e}")
            results.append({"url": url, "success": False, "error": str(e)})
            failed += 1

    return SpreadsheetDownloadPendingResponse(
        success=failed == 0,
        total_pending=len(pending_rows),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


@router.post("/rename")
async def api_rename_post(request: Request, req: SpreadsheetRenameRequest):
    """Rename media files in S3 by applying a suffix, and update status to RENAMED."""
    url = req.url.strip()
    suffix = req.suffix.strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")
    if not suffix:
        raise HTTPException(status_code=400, detail="Suffix is required.")

    try:
        rows = read_sheet_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    metadata_list = load_all_spreadsheet_metadata()

    target_row = None
    for row in rows:
        nrow = normalize_row_keys(row)
        if nrow.get("link") == url or nrow.get("rectified_link") == url:
            target_row = nrow
            break

    if not target_row:
        target_row = {"link": url, "platform": "instagram"}

    platform = target_row.get("platform", "instagram").lower().strip()
    meta = _find_metadata_for_row(target_row, metadata_list)
    if not meta:
        raise HTTPException(status_code=404, detail="Post metadata not found. Sync first.")

    identifier = meta.get("shortcode") or meta.get("post_id", "")
    if not identifier:
        raise HTTPException(status_code=404, detail="Post identifier not found in metadata.")

    s3_prefix = _build_s3_prefix(platform, identifier)

    try:
        new_keys = rename_s3_media_files(s3_prefix, suffix)
    except Exception as e:
        logger.error(f"Failed to rename S3 files for {url}: {e}")
        raise HTTPException(status_code=500, detail=f"S3 rename failed: {e}")

    try:
        update_row_status(url, "RENAMED")
    except Exception as sheet_err:
        logger.warning(f"Failed to update sheet status for {url}: {sheet_err}")

    return {"success": True, "new_keys": new_keys, "message": f"Renamed files with suffix '{suffix}'"}


@router.post("/download")
async def api_download_post_locally(request: Request, req: SpreadsheetLocalDownloadRequest):
    """Download media files from S3 to local disk and update status to DOWNLOADED."""
    url = req.url.strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    try:
        rows = read_sheet_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    metadata_list = load_all_spreadsheet_metadata()

    target_row = None
    for row in rows:
        nrow = normalize_row_keys(row)
        if nrow.get("link") == url or nrow.get("rectified_link") == url:
            target_row = nrow
            break

    if not target_row:
        target_row = {"link": url, "platform": "instagram"}

    platform = target_row.get("platform", "instagram").lower().strip()
    meta = _find_metadata_for_row(target_row, metadata_list)
    if not meta:
        raise HTTPException(status_code=404, detail="Post metadata not found. Sync first.")

    identifier = meta.get("shortcode") or meta.get("post_id", "")
    if not identifier:
        raise HTTPException(status_code=404, detail="Post identifier not found in metadata.")

    s3_prefix = _build_s3_prefix(platform, identifier)
    local_target_dir = os.path.join("downloads", platform, identifier)

    try:
        downloaded_files = download_post_from_s3(s3_prefix, local_target_dir)
    except Exception as e:
        logger.error(f"Failed to download from S3 for {url}: {e}")
        raise HTTPException(status_code=500, detail=f"S3 download failed: {e}")

    try:
        update_row_status(url, "DOWNLOADED")
    except Exception as sheet_err:
        logger.warning(f"Failed to update sheet status for {url}: {sheet_err}")

    return {
        "success": True,
        "downloaded_files": [os.path.basename(f) for f in downloaded_files],
        "local_dir": local_target_dir,
        "message": f"Downloaded {len(downloaded_files)} files to {local_target_dir}",
    }


@router.get("/posts")
async def api_get_spreadsheet_posts(request: Request):
    """Return all posts from the spreadsheet enriched with local metadata when available."""
    try:
        rows = read_sheet_data()
    except Exception as e:
        logger.error(f"Failed to read spreadsheet posts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    metadata_list = load_all_spreadsheet_metadata()

    posts = []
    for row in rows:
        post_dict = _build_post_item(row, metadata_list)
        posts.append(post_dict)

    return {"success": True, "posts": posts}


@router.post("/download-post")
async def api_download_spreadsheet_post(request: Request, req: SpreadsheetDownloadPostRequest):
    """Download a single post locally with an optional suffix."""
    url = req.url.strip()
    suffix = req.suffix
    rectified_link = req.rectified_link or url

    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    platform = "instagram"
    for row in read_sheet_data():
        nrow = normalize_row_keys(row)
        if nrow.get("link") == url:
            platform = nrow.get("platform", "instagram").lower().strip()
            break

    try:
        downloader = _get_downloader_for_platform(platform)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        metadata = await downloader.download_post(post_url=rectified_link, suffix=suffix)
        save_spreadsheet_metadata(metadata)
        return {"success": True, "data": metadata}
    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open-folder")
async def api_open_spreadsheet_folder(request: Request):
    """Open the folder containing a downloaded spreadsheet post."""
    body = await request.json()
    identifier = body.get("identifier")

    download_dirs = [
        os.path.join("downloads", "instagram"),
        os.path.join("downloads", "threads"),
    ]

    target_dir = None
    for d in download_dirs:
        if identifier and os.path.exists(os.path.join(d, identifier)):
            target_dir = os.path.join(d, identifier)
            break

    if not target_dir:
        target_dir = os.path.abspath("downloads")

    try:
        subprocess.Popen(["open", target_dir])
        return {"success": True, "opened_path": target_dir}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")
