from fastapi import APIRouter, Request, HTTPException
import logging
import os
import subprocess
from media_downloader.core.models import (
    SpreadsheetPostItem,
    SpreadsheetSyncResponse,
    SpreadsheetDownloadPostRequest,
    SpreadsheetDownloadPendingResponse,
)
from media_downloader.core.spreadsheet import (
    read_sheet_data,
    update_row_status,
    save_spreadsheet_metadata,
    load_all_spreadsheet_metadata,
    upload_directory_to_s3,
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


@router.post("/sync")
async def api_sync_spreadsheet(request: Request):
    """Sync data from the Google Spreadsheet and return all rows."""
    try:
        rows = read_sheet_data()
        pending_count = sum(1 for r in rows if r.get("Status", "").upper() == "PENDING")
        downloaded_count = sum(1 for r in rows if r.get("Status", "").upper() == "DOWNLOADED")
        posts = [SpreadsheetPostItem(**r) for r in rows]
        return SpreadsheetSyncResponse(
            success=True,
            posts=posts,
            pending_count=pending_count,
            downloaded_count=downloaded_count,
        )
    except Exception as e:
        logger.error(f"Failed to sync spreadsheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-pending")
async def api_download_pending(request: Request):
    """Download all PENDING posts to S3 and update their status to DOWNLOADED."""
    try:
        rows = read_sheet_data()
        pending_rows = [r for r in rows if r.get("Status", "").upper() == "PENDING"]
    except Exception as e:
        logger.error(f"Failed to read spreadsheet for pending download: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    results = []
    succeeded = 0
    failed = 0

    for row in pending_rows:
        url = row.get("Link", "")
        platform = row.get("Platform", "").lower().strip()
        suffix = None
        rectified_link = row.get("Rectified Link") or row.get("Rectified link") or url

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
            metadata = await downloader.download_post(post_url=rectified_link, suffix=suffix)
            s3_prefix = f"spreadsheet/{metadata.get('shortcode') or metadata.get('post_id', 'unknown')}"
            download_dir = downloader.get_downloads_dir()
            identifier = metadata.get("shortcode") or metadata.get("post_id", "unknown")
            post_dir = os.path.join(download_dir, identifier)
            logger.info(f"Post {identifier} downloaded to {post_dir}")

            if os.path.exists(post_dir):
                logger.info(f"Uploading {post_dir} to S3 prefix {s3_prefix}")
                upload_directory_to_s3(post_dir, s3_prefix)
            else:
                logger.warning(f"Local post directory not found, skipping S3 upload: {post_dir}")

            save_spreadsheet_metadata(metadata)

            try:
                update_row_status(url, "DOWNLOADED")
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


@router.get("/posts")
async def api_get_spreadsheet_posts(request: Request):
    """Return all posts from the spreadsheet enriched with local metadata when available."""
    try:
        rows = read_sheet_data()
    except Exception as e:
        logger.error(f"Failed to read spreadsheet posts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read spreadsheet: {e}")

    metadata_map = {m.get("url"): m for m in load_all_spreadsheet_metadata()}

    posts = []
    for row in rows:
        url = row.get("Link", "")
        meta = metadata_map.get(url)
        post_item = SpreadsheetPostItem(
            datetime=row.get("Datetime", ""),
            link=url,
            rectified_link=row.get("Rectified Link") or row.get("Rectified link"),
            username=row.get("Username", ""),
            platform=row.get("Platform", ""),
            status=row.get("Status", ""),
            comment=row.get("Comment"),
            metadata=meta,
        )
        posts.append(post_item)

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
        if row.get("Link") == url:
            platform = row.get("Platform", "instagram").lower().strip()
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
    from fastapi import Body
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
