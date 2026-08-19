import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from media_downloader.core.config import settings
from media_downloader.platforms.instagram import InstagramDownloader
from media_downloader.platforms.threads import ThreadsDownloader

from media_downloader.api.routes import auth, download, history

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Platform registry — maps platform name to downloader instance
platform_downloaders = {
    "instagram": InstagramDownloader(),
    "threads": ThreadsDownloader(),
}


def _get_project_root() -> str:
    """Walk upward from this file to find the project root (where pyproject.toml lives)."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        if os.path.exists(os.path.join(d, "pyproject.toml")):
            return d
        d = os.path.dirname(d)
    # Fallback: assume cwd
    return os.getcwd()


PROJECT_ROOT = _get_project_root()
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure required directories exist."""
    for dl in platform_downloaders.values():
        os.makedirs(dl.get_downloads_dir(), exist_ok=True)
    os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "js"), exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "templates"), exist_ok=True)
    yield


app = FastAPI(title="Media Downloader API", lifespan=lifespan)
app.state.platform_downloaders = platform_downloaders


# ---------- Middleware: extract {platform} from URL path ----------
@app.middleware("http")
async def inject_platform(request: Request, call_next):
    """Parses /api/{platform}/... and attaches the downloader to request.state."""
    if request.url.path.startswith("/api/"):
        parts = request.url.path.split("/")
        if len(parts) >= 3:
            platform = parts[2]
            if platform in platform_downloaders:
                request.state.platform = platform
            else:
                return HTMLResponse(
                    content=f'{{"detail":"Unknown platform: {platform}"}}',
                    status_code=404,
                    media_type="application/json",
                )
    return await call_next(request)


# ---------- Include API route modules ----------
app.include_router(auth.router, prefix="/api/{platform}/auth", tags=["auth"])
app.include_router(download.router, prefix="/api/{platform}", tags=["download"])
app.include_router(history.router, prefix="/api/{platform}", tags=["history"])

# ---------- Static file mounts ----------
# Serve downloaded files
for name, dl in platform_downloaders.items():
    dl_dir = dl.get_downloads_dir()
    if os.path.isdir(dl_dir):
        app.mount(f"/downloads/{name}", StaticFiles(directory=dl_dir), name=f"downloads_{name}")

# Serve frontend CSS/JS
if os.path.isdir(os.path.join(FRONTEND_DIR, "css")):
    app.mount("/static/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
if os.path.isdir(os.path.join(FRONTEND_DIR, "js")):
    app.mount("/static/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")


# ---------- Frontend page routes ----------
@app.get("/")
async def read_root():
    """Serves the main dashboard page."""
    index_path = os.path.join(FRONTEND_DIR, "templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Frontend template not found.</h1>", status_code=404)


@app.get("/batch")
async def read_batch():
    """Serves the batch download page."""
    batch_path = os.path.join(FRONTEND_DIR, "templates", "batch.html")
    if os.path.exists(batch_path):
        return FileResponse(batch_path)
    return HTMLResponse("<h1>Batch template not found.</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "media_downloader.api.app:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True,
    )
