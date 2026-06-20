import os
import re
import json
import logging
import asyncio
import threading
import time
from datetime import datetime
from urllib.parse import urlparse
import urllib.parse
import requests
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SESSION_DIR = ".sessions"
SESSION_FILE = os.path.join(SESSION_DIR, "threads_auth.json")
DOWNLOADS_DIR = "downloads_threads"

THREADS_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?threads\.(?:net|com)/@([^/?#&]+)/post/([^/?#&]+)"
)


def extract_post_info(url: str, raise_error: bool = True) -> tuple:
    """Returns (username, post_id) extracted from a Threads post URL."""
    match = THREADS_URL_PATTERN.search(url)
    if not match:
        if raise_error:
            raise ValueError(
                "Invalid Threads URL. Expected: https://www.threads.net/@username/post/POST_ID"
            )
        return "", ""
    return match.group(1), match.group(2)


def is_authenticated() -> bool:
    """Returns True only when the saved session contains real Threads/Instagram auth cookies."""
    return _verify_saved_session()


def logout_session() -> bool:
    """Removes the saved Threads session file."""
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
            logger.info("Threads session cleared.")
            return True
        except Exception as e:
            logger.error(f"Error removing Threads session file: {e}")
    return False


def _verify_saved_session() -> bool:
    """
    Reads the saved Playwright storage-state and checks for real auth cookies.
    sessionid and ds_user_id are the definitive indicators on instagram.com
    or threads.net (Threads delegates login to Instagram).
    """
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        definitive = {"sessionid", "ds_user_id"}
        for c in cookies:
            domain = c.get("domain", "").lstrip(".")
            if c.get("name") in definitive and (
                "instagram.com" in domain or "threads.net" in domain
            ):
                return True
        return False
    except Exception as e:
        logger.warning(f"Could not verify saved session: {e}")
        return False


def _save_state_atomic(state: dict) -> None:
    """Write storage state to a temp file then atomically rename to SESSION_FILE."""
    tmp = SESSION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, SESSION_FILE)


# Tracks whether a login flow is already running.
_login_lock = threading.Lock()
_login_in_progress = False


def start_login_flow() -> bool:
    """
    Launches the Playwright login browser in a background thread and returns
    immediately. The frontend polls /api/auth/status; once a real session is
    saved, is_authenticated() returns True and the UI updates.

    Returns False if a login is already in progress.
    """
    global _login_in_progress
    with _login_lock:
        if _login_in_progress:
            logger.info("Login already in progress.")
            return False
        _login_in_progress = True

    def _run():
        global _login_in_progress
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_login_flow_impl())
        except Exception as e:
            logger.error(f"Login flow error: {e}")
        finally:
            _login_in_progress = False
            loop.close()

    threading.Thread(target=_run, daemon=True).start()
    return True


async def _login_flow_impl() -> None:
    """
    Async Playwright login flow that runs in its own thread event loop.
    Saves storage state every 3 seconds so the file is always current —
    the browser process may terminate before we can save after closure.
    """
    os.makedirs(SESSION_DIR, exist_ok=True)
    logger.info("Login browser starting...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        async def inject_banner(pg):
            try:
                await pg.evaluate("""() => {
                    if (document.getElementById('td-login-banner')) return;
                    const b = document.createElement('div');
                    b.id = 'td-login-banner';
                    b.style.cssText = [
                        'position:fixed','top:0','left:0','right:0','z-index:2147483647',
                        'background:#00c6a7','color:#000','padding:10px 20px',
                        'text-align:center','font:600 14px/1.4 system-ui,sans-serif',
                        'box-shadow:0 2px 8px rgba(0,0,0,.25)'
                    ].join(';');
                    b.textContent = \
'ThreadDrop — Log in to Threads below, then CLOSE THIS WINDOW when done.';
                    document.body.prepend(b);
                }""")
            except Exception:
                pass

        page.on("load", lambda _: asyncio.ensure_future(inject_banner(page)))
        await page.goto("https://www.threads.net/login")
        await inject_banner(page)

        logger.info("Browser open — waiting for user to log in and close the window.")

        timeout_seconds = 300
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if page.is_closed():
                logger.info("Browser window closed by user.")
                break
            try:
                state = await context.storage_state()
                _save_state_atomic(state)
            except Exception:
                pass
            await asyncio.sleep(3)

        # Final save attempt (succeeds if browser is still alive at timeout)
        try:
            state = await context.storage_state()
            _save_state_atomic(state)
        except Exception:
            pass

        try:
            await browser.close()
        except Exception:
            pass

        if _verify_saved_session():
            logger.info("Threads session verified — user is logged in.")
        else:
            logger.warning("Session saved but no auth cookies found — login incomplete.")


def download_file(url: str, filepath: str):
    """Downloads a media file from a CDN URL using requests."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.threads.net/",
    }
    logger.info(f"Downloading: {url[:80]}...")
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def _is_cdn_media_url(url: str) -> bool:
    """Returns True if the URL points to a Meta CDN media asset.
    Threads may serve images from fbcdn.net as well as cdninstagram.com."""
    return bool(url) and any(d in url for d in (
        "scontent", "cdninstagram", "fbcdn.net", "fbsbx.com",
    ))


async def download_threads_post(post_url: str, suffix: str = None) -> dict:
    """
    Downloads images and videos from a Threads post using Playwright.
    Login is optional for public posts. When a session is saved it is used
    automatically so private (followed) accounts work too.
    """
    # Normalise URL (threads.com and threads.net are equivalent)
    normalized_url = re.sub(r"threads\.com", "threads.net", post_url)
    if not normalized_url.startswith("http"):
        normalized_url = "https://www." + normalized_url.lstrip("/")

    username, post_id = extract_post_info(normalized_url)
    logger.info(f"Downloading Threads post '{post_id}' by @{username}...")

    intercepted_images: list[str] = []
    intercepted_videos: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        if is_authenticated():
            context = await browser.new_context(storage_state=SESSION_FILE)
            logger.info("Using authenticated Threads session.")
        else:
            context = await browser.new_context()
            logger.info("Anonymous mode — no Threads session loaded.")

        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 900})

        # Intercept CDN responses for both images and videos.
        # Profile-picture paths use t51.2885-19; post media uses t51.2885-15 or similar.
        def handle_response(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "").lower()
                if not _is_cdn_media_url(url):
                    return
                if ".mp4" in url or "video" in content_type:
                    if url not in intercepted_videos:
                        logger.info(f"Intercepted video: {url[:80]}...")
                        intercepted_videos.append(url)
                elif "image" in content_type or any(
                    ext in url for ext in (".jpg", ".jpeg", ".png", ".webp")
                ):
                    # Exclude profile-picture CDN paths
                    if "t51.2885-19" not in url and "t51.29350-19" not in url:
                        if url not in intercepted_images:
                            logger.info(f"Intercepted image: {url[:80]}...")
                            intercepted_images.append(url)
            except Exception:
                pass

        page.on("response", handle_response)

        # networkidle ensures dynamic content has finished loading
        await page.goto(normalized_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # ── Access-wall detection ──────────────────────────────────

        # Hard redirect to login page
        current_url = page.url
        if "login" in current_url or "/accounts/" in current_url:
            await browser.close()
            raise RuntimeError(
                "This Threads post requires a login to view. "
                "Click 'Login to Threads (Optional)' to connect your account and try again."
            )

        # Private account or follow-required wall (text on page)
        page_text = (await page.evaluate("document.body.innerText") or "").lower()
        if any(phrase in page_text for phrase in (
            "this account is private",
            "follow this account",
            "follow to see their",
            "account is private",
        )):
            await browser.close()
            raise RuntimeError(
                "This account is private. You must be following @"
                + username
                + " on the Threads account you logged in with to download their posts."
            )

        # ── Scroll to trigger lazy loading ────────────────────────
        await page.evaluate("window.scrollBy(0, 600)")
        await page.wait_for_timeout(1200)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(800)

        # ── Metadata ──────────────────────────────────────────────
        owner_username = username
        try:
            user_link = page.locator("a[href^='/@']").first
            if await user_link.is_visible():
                href = await user_link.get_attribute("href") or ""
                extracted = href.lstrip("/@").split("/")[0].split("?")[0]
                if extracted:
                    owner_username = extracted
        except Exception:
            pass

        caption = ""
        try:
            for loc in await page.locator("span[dir='auto'], p[dir='auto']").all():
                text = (await loc.text_content() or "").strip()
                if len(text) > 15:
                    caption = text
                    break
        except Exception:
            pass

        # ── Collect media URLs ─────────────────────────────────────
        media_urls: list[str] = []
        is_video = False

        # Carousel loop — up to 12 slides.
        for _slide in range(12):
            # Images: filter only by alt text (avatars) and clearly tiny elements.
            # Do NOT filter by CDN path pattern or intrinsic size — those filters
            # proved unreliable and excluded real Threads post images.
            for img in await page.locator("img").all():
                try:
                    src = await img.get_attribute("src") or ""
                    if not _is_cdn_media_url(src):
                        continue
                    alt = (await img.get_attribute("alt") or "").lower()
                    if "profile" in alt or "avatar" in alt:
                        continue
                    # Only skip elements with a rendered size that is definitely
                    # icon-sized (both dimensions < 100 px). Hidden carousel slides
                    # return None for bounding_box, so they always pass this check.
                    box = await img.bounding_box()
                    if box and box["width"] < 100 and box["height"] < 100:
                        continue
                    if src not in media_urls:
                        logger.info(f"Found image: {src[:80]}...")
                        media_urls.append(src)
                except Exception:
                    pass

            # Videos
            for vid in await page.locator("video").all():
                try:
                    is_video = True
                    src = await vid.get_attribute("src") or ""
                    if src.startswith("http") and src not in media_urls:
                        logger.info(f"Found video: {src[:80]}...")
                        media_urls.append(src)
                except Exception:
                    pass

            # Advance carousel
            next_btn = page.locator(
                "button[aria-label='Next'], button[aria-label='next'], "
                "button:has(svg[aria-label='Next'])"
            ).first
            try:
                if await next_btn.is_visible(timeout=800):
                    await next_btn.evaluate("el => el.click()")
                    await page.wait_for_timeout(900)
                else:
                    break
            except Exception:
                break

        # ── Network-interception fallback ─────────────────────────
        # Use intercepted images only when DOM scraping found nothing at all.
        # Merging both sources duplicates every image (same content, different
        # CDN auth tokens = different URL strings).
        if not media_urls:
            media_urls.extend(intercepted_images)
            logger.info(f"DOM found nothing; using {len(media_urls)} intercepted image(s).")

        # Videos: fall back to interception when no direct src found in DOM
        if is_video or intercepted_videos:
            is_video = True
            if not any(".mp4" in u.lower() for u in media_urls) and intercepted_videos:
                media_urls.append(intercepted_videos[0])

        # Drop blob: URLs
        media_urls = [u for u in media_urls if not u.startswith("blob:")]

        # ── Deduplicate by CDN path ────────────────────────────────
        # The same image can be present under different query-string tokens
        # (e.g. re-rendered carousel positions). Keep first occurrence per path.
        seen_paths: set[str] = set()
        deduped: list[str] = []
        for url in media_urls:
            path = urllib.parse.urlparse(url).path
            if path not in seen_paths:
                seen_paths.add(path)
                deduped.append(url)
            else:
                logger.info(f"Deduplicated: {url[:80]}...")
        media_urls = deduped

        if not media_urls:
            await browser.close()
            raise RuntimeError(
                "No media files found in this Threads post. "
                "The post may be private, deleted, or the account may require you to follow it."
            )

        # --- Download files ---
        download_dir = os.path.abspath(os.path.join(DOWNLOADS_DIR, post_id))
        os.makedirs(download_dir, exist_ok=True)
        logger.info(f"Saving {len(media_urls)} file(s) to {download_dir}")

        downloaded_files = []
        for idx, url in enumerate(media_urls):
            parsed = urllib.parse.urlparse(url)
            original_name = os.path.basename(parsed.path)
            base, ext = os.path.splitext(original_name)

            if not ext:
                ext = ".mp4" if (".mp4" in url.lower() or is_video) else ".jpg"

            digits = re.findall(r"\d+", base)
            base = "_".join(digits) if digits else f"{post_id}_{idx}"

            if suffix:
                clean_suffix = re.sub(r'[\\/*?:"<>|]', "", suffix)
                base = f"{base}{clean_suffix}"

            filename = f"{base}{ext}"
            filepath = os.path.join(download_dir, filename)

            try:
                download_file(url, filepath)
                downloaded_files.append(filename)
            except Exception as e:
                logger.error(f"Failed to download asset {idx}: {e}")

        if not downloaded_files:
            await browser.close()
            raise RuntimeError("Failed to download any of the media files found on this post.")

        # --- Write metadata ---
        post_metadata = {
            "post_id": post_id,
            "url": f"https://www.threads.net/@{owner_username}/post/{post_id}",
            "owner_username": owner_username,
            "caption": caption,
            "is_video": is_video,
            "date_utc": datetime.utcnow().isoformat(),
            "downloaded_at": datetime.utcnow().isoformat(),
            "media_files": downloaded_files,
        }

        metadata_file = os.path.join(download_dir, "metadata.json")
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(post_metadata, f, indent=4, ensure_ascii=False)

        logger.info(f"Download complete. Metadata written to {metadata_file}")
        await browser.close()
        return post_metadata