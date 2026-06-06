import os
import re
import json
import logging
import asyncio
import time
from datetime import datetime
import requests
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SESSION_DIR = ".sessions"
SESSION_FILE = os.path.join(SESSION_DIR, "playwright_auth.json")
INSTAGRAM_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([^/?#&]+)"
)

def extract_shortcode(url: str) -> str:
    """
    Extracts the shortcode from an Instagram URL.
    """
    match = INSTAGRAM_URL_PATTERN.search(url)
    if not match:
        raise ValueError("Invalid Instagram URL pattern. Must be a /p/, /reel/, or /tv/ URL.")
    return match.group(1)

def is_authenticated() -> bool:
    """
    Checks if a saved login session exists and is non-empty.
    """
    return os.path.exists(SESSION_FILE) and os.path.getsize(SESSION_FILE) > 0

def logout_session():
    """
    Clears the saved session file to trigger logout.
    """
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
            logger.info("Session cleared successfully.")
            return True
        except Exception as e:
            logger.error(f"Error removing session file: {e}")
    return False

async def start_login_flow() -> bool:
    """
    Launches a headed Chromium browser window for interactive manual login.
    Waits for the user to authenticate (monitoring cookies for sessionid).
    Saves the session state and returns True if successful, False otherwise.
    """
    os.makedirs(SESSION_DIR, exist_ok=True)
    logger.info("Starting interactive headed login flow...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")
        
        logged_in = False
        timeout_seconds = 180
        start_time = time.time()
        
        logger.info("Please log in manually on the browser window.")
        
        while time.time() - start_time < timeout_seconds:
            try:
                cookies = await context.cookies()
                if any(c['name'] == 'sessionid' for c in cookies):
                    logged_in = True
                    break
            except Exception as e:
                logger.warning(f"Error checking cookies: {e}")
                
            if page.is_closed():
                logger.warning("Browser window was closed by the user.")
                break
                
            await asyncio.sleep(2)
            
        if logged_in:
            logger.info("Login detected. Waiting 4 seconds for session cookies and storage to settle...")
            await page.wait_for_timeout(4000) # Wait for storage updates
            
            # Save storage state (cookies, local storage, etc.)
            await context.storage_state(path=SESSION_FILE)
            logger.info(f"Authentication state saved to {SESSION_FILE}")
            success = True
        else:
            logger.error("Authentication timed out or browser was closed before completion.")
            success = False
            
        try:
            await browser.close()
        except Exception:
            pass
            
        return success

def download_file(url: str, filepath: str):
    """
    Downloads a media file from a CDN URL using requests with a standard browser User-Agent.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.instagram.com/"
    }
    logger.info(f"Downloading file from: {url}")
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

async def download_instagram_post(post_url: str) -> dict:
    """
    Downloads an Instagram post using Playwright headless browser.
    Extracts media sources, handles carousels, downloads CDN assets, and writes metadata.
    """
    if not is_authenticated():
        raise RuntimeError("Instagram account not connected. Please log in first.")
        
    shortcode = extract_shortcode(post_url)
    logger.info(f"Downloading post {shortcode}...")

    # We will intercept network responses to capture direct video stream URLs
    intercepted_videos = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=SESSION_FILE)
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        # Intercept response to catch video URLs
        def handle_response(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "").lower()
                if "scontent" in url and (".mp4" in url or "video" in content_type):
                    if url not in intercepted_videos:
                        logger.info(f"Intercepted video stream: {url}")
                        intercepted_videos.append(url)
            except Exception:
                pass
                
        page.on("response", handle_response)
        
        # Go to post page
        await page.goto(post_url, wait_until="load")
        
        # Wait to let dynamic content render
        await page.wait_for_timeout(4000) 
        
        # 1. Detect if redirect or modal shows a login wall
        login_form_visible = False
        try:
            username_input = page.locator("input[name='username']").first
            if await username_input.is_visible():
                login_form_visible = True
        except Exception:
            pass

        if "accounts/login" in page.url or login_form_visible:
            await browser.close()
            logout_session()
            raise RuntimeError("Your Instagram session is invalid or has expired. Please disconnect and reconnect your account.")

        # 2. Detect if account is private
        private_visible = False
        try:
            # Look for common private account text indicators
            private_loc = page.locator("text='This Account is Private', text='This account is private'").first
            if await private_loc.is_visible():
                private_visible = True
        except Exception:
            pass

        if private_visible:
            await browser.close()
            raise RuntimeError("This account is private. You must follow this account on your connected Instagram profile to download its media.")

        # Scrape Owner Username
        owner_username = "instagram_user"
        try:
            username_loc = page.locator("header a[href^='/']").first
            if await username_loc.is_visible():
                owner_username = (await username_loc.text_content()).strip()
        except Exception as e:
            logger.warning(f"Could not find username link: {e}")

        # Scrape Caption
        caption = ""
        try:
            h1_loc = page.locator("h1").first
            if await h1_loc.is_visible():
                caption = (await h1_loc.text_content()).strip()
        except Exception as e:
            logger.warning(f"Could not find caption: {e}")

        # Scrape media assets list
        media_urls = []
        is_video = False
        
        # Loop to process slides in carousels
        for slide_idx in range(12): # Max 12 slides
            # Capture visible image URLs (broad locator, filter small elements)
            images = await page.locator("img").all()
            for img in images:
                try:
                    alt = (await img.get_attribute("alt") or "").lower()
                    if "profile picture" in alt or "avatar" in alt:
                        continue # Skip avatars
                        
                    # Filter out small graphics/icons
                    box = await img.bounding_box()
                    if box and (box['width'] < 250 or box['height'] < 250):
                        continue
                        
                    src = await img.get_attribute("src")
                    if src and "scontent" in src and src not in media_urls:
                        logger.info(f"Found image URL: {src[:80]}...")
                        media_urls.append(src)
                except Exception:
                    pass

            # Capture visible video URLs
            videos = await page.locator("video").all()
            for vid in videos:
                try:
                    is_video = True
                    src = await vid.get_attribute("src")
                    if src and src.startswith("http") and src not in media_urls:
                        logger.info(f"Found video URL: {src[:80]}...")
                        media_urls.append(src)
                except Exception:
                    pass
            
            # Click "Next" button if present
            next_btn = page.locator("button[aria-label='Next'], button:has(div > svg[aria-label='Next'])").first
            if await next_btn.is_visible():
                try:
                    # Use JS evaluation click to bypass any popups/dialogs blocking clicks
                    await next_btn.evaluate("el => el.click()")
                    await page.wait_for_timeout(1000) # Wait for slide transition
                except Exception:
                    break
            else:
                break # No more slides
                
        # Merge intercepted videos (blob fallbacks)
        if is_video or len(intercepted_videos) > 0:
            is_video = True
            for video_url in intercepted_videos:
                if video_url not in media_urls:
                    media_urls.append(video_url)

        # Remove blob URLs if any crept into media_urls
        media_urls = [url for url in media_urls if not url.startswith("blob:")]

        if not media_urls:
            await browser.close()
            raise RuntimeError("Could not locate any media files on this post. Instagram might be blocking access.")

        # Set up output directory
        download_dir = os.path.abspath(os.path.join("downloads", shortcode))
        os.makedirs(download_dir, exist_ok=True)
        
        logger.info(f"Found {len(media_urls)} media URLs. Starting download...")
        
        downloaded_files = []
        for idx, url in enumerate(media_urls):
            # Determine extension
            ext = ".mp4" if (".mp4" in url or "video" in url.lower() or is_video and len(media_urls) == 1) else ".jpg"
            filename = f"{shortcode}_{idx}{ext}"
            filepath = os.path.join(download_dir, filename)
            
            try:
                download_file(url, filepath)
                downloaded_files.append(filename)
            except Exception as e:
                logger.error(f"Failed to download asset {idx}: {e}")

        if not downloaded_files:
            await browser.close()
            raise RuntimeError("Failed to download any of the retrieved media URLs.")

        # Compile metadata
        post_metadata = {
            "shortcode": shortcode,
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "owner_username": owner_username,
            "owner_id": 0,
            "caption": caption,
            "likes": 0,
            "comments": 0,
            "is_video": is_video,
            "date_utc": datetime.utcnow().isoformat(),
            "downloaded_at": datetime.utcnow().isoformat(),
            "media_files": downloaded_files
        }

        # Write metadata.json
        metadata_file = os.path.join(download_dir, "metadata.json")
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(post_metadata, f, indent=4, ensure_ascii=False)

        logger.info(f"Download complete! Saved metadata to {metadata_file}")
        await browser.close()
        return post_metadata
