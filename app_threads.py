import os
import subprocess
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from threads_downloader import (
    download_threads_post,
    is_authenticated,
    start_login_flow,
    logout_session,
    DOWNLOADS_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Threads Downloader API")

# Ensure required directories exist
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(".sessions", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Request models
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
    post_id: Optional[str] = None

# Mount static assets (shared with Instagram app) and Threads downloads
app.mount(f"/{DOWNLOADS_DIR}", StaticFiles(directory=DOWNLOADS_DIR), name="downloads_threads")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_root():
    path = "templates/threads_index.html"
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>Threads frontend template not found.</h1>", status_code=404)


@app.get("/batch")
async def read_batch():
    path = "templates/threads_batch.html"
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>Threads batch template not found.</h1>", status_code=404)


@app.get("/api/auth/status")
async def api_auth_status():
    """Returns whether a Threads session is saved (login is optional)."""
    return {"authenticated": is_authenticated()}


@app.post("/api/auth/login")
async def api_auth_login():
    """
    Starts the Threads login browser in a background thread and returns
    immediately. The frontend polls /api/auth/status to detect completion.
    """
    logger.info("Starting Threads login flow in background thread.")
    started = start_login_flow()
    return {"success": started, "authenticated": is_authenticated()}


@app.post("/api/auth/logout")
async def api_auth_logout():
    """Clears the saved Threads session."""
    success = logout_session()
    return {"success": success}


@app.post("/api/download")
async def api_download(req: DownloadRequest):
    """Downloads a single Threads post. Login is optional for public posts."""
    logger.info(f"Download request: {req.url}")
    try:
        metadata = await download_threads_post(post_url=req.url, suffix=req.suffix)
        return {"success": True, "data": metadata}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch-download")
async def api_batch_download(req: BatchDownloadRequest):
    """Downloads up to 9 Threads posts sequentially."""
    logger.info(f"Batch download: {len(req.items)} post(s).")
    results = []
    for idx, item in enumerate(req.items):
        logger.info(f"Batch item {idx + 1}/{len(req.items)}: {item.url}")
        try:
            metadata = await download_threads_post(post_url=item.url, suffix=item.suffix)
            results.append({"index": idx, "success": True, "data": metadata, "url": item.url})
        except ValueError as ve:
            results.append({"index": idx, "success": False, "error": str(ve), "url": item.url})
        except Exception as e:
            logger.error(f"Batch item {idx + 1} failed: {e}")
            results.append({"index": idx, "success": False, "error": str(e), "url": item.url})

    succeeded = sum(1 for r in results if r["success"])
    return {
        "success": succeeded == len(results),
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@app.get("/api/history")
async def api_history():
    """Returns list of previously downloaded Threads posts from the downloads folder."""
    import json
    history = []

    if not os.path.exists(DOWNLOADS_DIR):
        return {"success": True, "history": []}

    try:
        for folder_name in os.listdir(DOWNLOADS_DIR):
            folder_path = os.path.join(DOWNLOADS_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
            metadata_file = os.path.join(folder_path, "metadata.json")
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        history.append(json.load(f))
                except Exception as ex:
                    logger.warning(f"Failed to read metadata in {folder_name}: {ex}")

        history.sort(key=lambda x: x.get("downloaded_at", ""), reverse=True)
        return {"success": True, "history": history}
    except Exception as e:
        logger.error(f"History fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/open-folder")
async def api_open_folder(req: OpenFolderRequest):
    """Opens the Threads downloads folder (or a specific post subfolder) in Finder."""
    base_dir = os.path.abspath(DOWNLOADS_DIR)
    target_dir = base_dir

    if req.post_id:
        folder_path = os.path.abspath(os.path.join(base_dir, req.post_id))
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            target_dir = folder_path

    logger.info(f"Opening folder: {target_dir}")
    try:
        subprocess.Popen(["open", target_dir])
        return {"success": True, "opened_path": target_dir}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_threads:app", host="127.0.0.1", port=8001, reload=True)
