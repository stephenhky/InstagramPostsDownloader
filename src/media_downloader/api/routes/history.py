from fastapi import APIRouter, Request, HTTPException
import os
import json
import subprocess
import logging
from media_downloader.core.models import OpenFolderRequest

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/history")
async def api_history(request: Request):
    downloader = request.app.state.platform_downloaders[request.state.platform]
    downloads_dir = downloader.get_downloads_dir()
    history = []
    
    if not os.path.exists(downloads_dir):
        return {"success": True, "history": []}

    try:
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

        history.sort(key=lambda x: x.get("downloaded_at", ""), reverse=True)
        return {"success": True, "history": history}
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/open-folder")
async def api_open_folder(request: Request, req: OpenFolderRequest):
    downloader = request.app.state.platform_downloaders[request.state.platform]
    base_dir = os.path.abspath(downloader.get_downloads_dir())
    target_dir = base_dir

    if req.identifier:
        folder_path = os.path.abspath(os.path.join(base_dir, req.identifier))
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            target_dir = folder_path

    logger.info(f"Opening folder in Finder: {target_dir}")
    try:
        subprocess.Popen(["open", target_dir])
        return {"success": True, "opened_path": target_dir}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")
