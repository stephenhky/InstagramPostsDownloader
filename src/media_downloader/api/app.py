import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from media_downloader.core.config import settings
from media_downloader.platforms.instagram import InstagramDownloader
from media_downloader.platforms.threads import ThreadsDownloader
from media_downloader.api.routes import auth, download, history

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── Resolve project root from the installed package location ───────────────────
# src/media_downloader/api/app.py  →  go up 4 levels to reach project root
_THIS_FILE = os.path.abspath(__file__)            # .../src/media_downloader/api/app.py
_API_DIR   = os.path.dirname(_THIS_FILE)          # .../src/media_downloader/api/
_PKG_DIR   = os.path.dirname(_API_DIR)            # .../src/media_downloader/
_SRC_DIR   = os.path.dirname(_PKG_DIR)            # .../src/
PROJECT_ROOT = os.path.dirname(_SRC_DIR)          # project root (contains pyproject.toml)

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

logger.info(f"Project root: {PROJECT_ROOT}")
logger.info(f"Frontend dir: {FRONTEND_DIR}")

# Verify the root looks right
if not os.path.exists(os.path.join(PROJECT_ROOT, "pyproject.toml")):
    logger.warning(f"pyproject.toml not found at {PROJECT_ROOT} — path resolution may be wrong")

# Pin CWD so relative paths (.sessions/, downloads/) work correctly
os.chdir(PROJECT_ROOT)


# ── Platform registry ──────────────────────────────────────────────────────────
platform_downloaders = {
    "instagram": InstagramDownloader(),
    "threads":   ThreadsDownloader(),
}


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    for dl in platform_downloaders.values():
        os.makedirs(dl.get_downloads_dir(), exist_ok=True)
    os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "js"), exist_ok=True)
    os.makedirs(os.path.join(FRONTEND_DIR, "templates"), exist_ok=True)
    logger.info(f"Instagram authenticated: {platform_downloaders['instagram'].is_authenticated()}")
    logger.info(f"Threads authenticated: {platform_downloaders['threads'].is_authenticated()}")
    yield


app = FastAPI(title="Media Downloader API", lifespan=lifespan)
app.state.platform_downloaders = platform_downloaders


# ── Middleware: inject platform from URL ───────────────────────────────────────
@app.middleware("http")
async def inject_platform(request: Request, call_next):
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


# ── API routes ─────────────────────────────────────────────────────────────────
app.include_router(auth.router,     prefix="/api/{platform}/auth", tags=["auth"])
app.include_router(download.router, prefix="/api/{platform}",      tags=["download"])
app.include_router(history.router,  prefix="/api/{platform}",      tags=["history"])


# ── Static mounts — use absolute paths so they never depend on CWD ────────────
for _name, _dl in platform_downloaders.items():
    _dl_dir = os.path.join(PROJECT_ROOT, _dl.get_downloads_dir())
    os.makedirs(_dl_dir, exist_ok=True)
    app.mount(f"/downloads/{_name}", StaticFiles(directory=_dl_dir), name=f"downloads_{_name}")

_css_dir = os.path.join(FRONTEND_DIR, "css")
_js_dir  = os.path.join(FRONTEND_DIR, "js")
os.makedirs(_css_dir, exist_ok=True)
os.makedirs(_js_dir,  exist_ok=True)
app.mount("/static/css", StaticFiles(directory=_css_dir), name="css")
app.mount("/static/js",  StaticFiles(directory=_js_dir),  name="js")


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def read_root():
    index_path = os.path.join(FRONTEND_DIR, "templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse(f"<h1>Template not found: {index_path}</h1>", status_code=404)


@app.get("/batch")
async def read_batch():
    batch_path = os.path.join(FRONTEND_DIR, "templates", "batch.html")
    if os.path.exists(batch_path):
        return FileResponse(batch_path)
    return HTMLResponse(f"<h1>Template not found: {batch_path}</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "media_downloader.api.app:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True,
    )
