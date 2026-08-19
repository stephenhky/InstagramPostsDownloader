from fastapi import APIRouter, Request, HTTPException
import logging
from media_downloader.core.models import DownloadRequest, BatchDownloadRequest, ResolveUrlRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/resolve-url")
async def api_resolve_url(request: Request, req: ResolveUrlRequest):
    """Resolves a share/redirect URL to its canonical form (Threads only)."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    url = req.url.strip()

    if hasattr(downloader, "resolve_share_url"):
        if "/share/" not in url:
            return {"success": True, "resolved_url": url}
        try:
            resolved = downloader.resolve_share_url(url)
            return {"success": True, "resolved_url": resolved}
        except Exception as e:
            logger.error(f"Failed to resolve URL: {e}")
            return {"success": False, "resolved_url": url, "error": str(e)}

    return {"success": True, "resolved_url": url}


@router.post("/download")
async def api_download(request: Request, req: DownloadRequest):
    """Triggers a single post download."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    logger.info(f"Download request for URL: {req.url} with suffix: {req.suffix}")

    if request.state.platform == "instagram" and not downloader.is_authenticated():
        raise HTTPException(
            status_code=400,
            detail="Instagram account is not connected. Please click 'Connect Instagram Account' first.",
        )

    try:
        metadata = await downloader.download_post(post_url=req.url, suffix=req.suffix)
        return {"success": True, "data": metadata}
    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-download")
async def api_batch_download(request: Request, req: BatchDownloadRequest):
    """Downloads up to 9 posts sequentially."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    logger.info(f"Batch download request for {len(req.items)} post(s).")

    if request.state.platform == "instagram" and not downloader.is_authenticated():
        raise HTTPException(
            status_code=400,
            detail="Instagram account is not connected. Please click 'Connect Instagram Account' first.",
        )

    results = []
    for idx, item in enumerate(req.items):
        logger.info(f"Batch item {idx + 1}/{len(req.items)}: {item.url}")
        try:
            metadata = await downloader.download_post(post_url=item.url, suffix=item.suffix)
            results.append({"index": idx, "success": True, "data": metadata, "url": item.url})
        except ValueError as ve:
            logger.warning(f"Batch item {idx + 1} validation error: {ve}")
            results.append({"index": idx, "success": False, "error": str(ve), "url": item.url})
        except Exception as e:
            logger.error(f"Batch item {idx + 1} download failed: {e}")
            results.append({"index": idx, "success": False, "error": str(e), "url": item.url})

    succeeded = sum(1 for r in results if r["success"])
    failed = len(results) - succeeded
    return {
        "success": failed == 0,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
