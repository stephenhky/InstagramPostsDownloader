import os
import subprocess
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from instagram_downloader import (
    download_instagram_post, 
    is_authenticated, 
    start_login_flow, 
    logout_session
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Instagram Downloader API")

# Ensure required directories exist
os.makedirs("downloads", exist_ok=True)
os.makedirs(".sessions", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Request Models
class DownloadRequest(BaseModel):
    url: str
    suffix: Optional[str] = None

class BatchDownloadItem(BaseModel):
    url: str
    suffix: Optional[str] = None

class BatchDownloadRequest(BaseModel):
    items: List[BatchDownloadItem]

    @field_validator("items")
    @classmethod
    def validate_items_count(cls, v):
        if len(v) == 0:
            raise ValueError("At least one post URL is required.")
        if len(v) > 9:
            raise ValueError("Maximum of 9 posts can be downloaded at once.")
        return v

class OpenFolderRequest(BaseModel):
    shortcode: Optional[str] = None

# Mount downloaded files so the browser can serve/display them directly
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    """Serves the main dashboard page."""
    index_path = "templates/index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Frontend template not found.</h1>", status_code=404)

@app.get("/batch")
async def read_batch():
    """Serves the batch download page."""
    batch_path = "templates/batch.html"
    if os.path.exists(batch_path):
        return FileResponse(batch_path)
    return HTMLResponse("<h1>Batch template not found.</h1>", status_code=404)

@app.get("/api/auth/status")
async def api_auth_status():
    """Returns whether the Instagram browser session is authenticated."""
    return {"authenticated": is_authenticated()}

@app.post("/api/auth/login")
async def api_auth_login():
    """
    Triggers the interactive headed login flow.
    Runs asynchronously on the main event loop.
    """
    logger.info("Received request to trigger headed login flow.")
    success = await start_login_flow()
    return {"success": success, "authenticated": is_authenticated()}

@app.post("/api/auth/logout")
async def api_auth_logout():
    """Clears the saved session cookies."""
    success = logout_session()
    return {"success": success}

@app.post("/api/download")
async def api_download(req: DownloadRequest):
    """Triggers the Instagram post download."""
    logger.info(f"Received download request for URL: {req.url} with suffix: {req.suffix}")
    if not is_authenticated():
        raise HTTPException(
            status_code=400, 
            detail="Instagram account is not connected. Please click 'Connect Instagram Account' first."
        )
        
    try:
        # Perform download using the async playwright downloader function
        metadata = await download_instagram_post(post_url=req.url, suffix=req.suffix)
        return {"success": True, "data": metadata}
    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Download processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/batch-download")
async def api_batch_download(req: BatchDownloadRequest):
    """Downloads up to 9 Instagram posts sequentially."""
    logger.info(f"Received batch download request for {len(req.items)} post(s).")
    if not is_authenticated():
        raise HTTPException(
            status_code=400,
            detail="Instagram account is not connected. Please click 'Connect Instagram Account' first."
        )

    results = []
    for idx, item in enumerate(req.items):
        logger.info(f"Batch item {idx + 1}/{len(req.items)}: {item.url}")
        try:
            metadata = await download_instagram_post(post_url=item.url, suffix=item.suffix)
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
        "results": results
    }

@app.get("/api/history")
async def api_history():
    """Scans downloads directory and returns list of downloaded posts metadata."""
    import json
    history = []
    downloads_dir = "downloads"
    
    if not os.path.exists(downloads_dir):
        return {"success": True, "history": []}

    try:
        # Scan folder for metadata.json files
        for folder_name in os.listdir(downloads_dir):
            folder_path = os.path.join(downloads_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue
                
            metadata_file = os.path.join(folder_path, "metadata.json")
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        history.append(meta)
                except Exception as ex:
                    logger.warning(f"Failed to read metadata file in {folder_name}: {ex}")

        # Sort history by download time, descending
        history.sort(key=lambda x: x.get("downloaded_at", ""), reverse=True)
        return {"success": True, "history": history}
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/open-folder")
async def api_open_folder(req: OpenFolderRequest):
    """Opens the local download folder in macOS Finder."""
    base_dir = os.path.abspath("downloads")
    target_dir = base_dir

    if req.shortcode:
        # Check if the specific post download folder exists
        folder_path = os.path.abspath(os.path.join(base_dir, req.shortcode))
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            target_dir = folder_path

    logger.info(f"Opening folder in Finder: {target_dir}")
    try:
        # Run macOS 'open' command
        subprocess.Popen(["open", target_dir])
        return {"success": True, "opened_path": target_dir}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
