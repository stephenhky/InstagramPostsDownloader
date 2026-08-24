import logging
import asyncio
import inspect
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
async def api_auth_status(request: Request):
    """Returns whether the platform session is authenticated."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    return {"authenticated": downloader.is_authenticated()}


@router.post("/login")
async def api_auth_login(request: Request):
    """Triggers the interactive login flow for the platform."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    logger.info(f"Login request received for platform: {request.state.platform}")

    if inspect.iscoroutinefunction(downloader.start_login_flow):
        asyncio.create_task(downloader.start_login_flow())
        success = True
    else:
        success = downloader.start_login_flow()

    return {"success": success, "authenticated": downloader.is_authenticated()}


@router.post("/logout")
async def api_auth_logout(request: Request):
    """Clears the saved session cookies."""
    downloader = request.app.state.platform_downloaders[request.state.platform]
    success = downloader.logout_session()
    return {"success": success}
