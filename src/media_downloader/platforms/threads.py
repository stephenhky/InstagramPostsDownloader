import os
import re
import json
import logging
import asyncio
import threading
import time
from datetime import datetime
import urllib.parse
import requests
from playwright.async_api import async_playwright

from media_downloader.core.config import settings
from media_downloader.core.session import is_authenticated, logout_session, save_state_atomic
from media_downloader.core.downloader import download_file, is_cdn_media_url, deduplicate_by_cdn_path, build_filename, write_metadata
from media_downloader.platforms.base import BasePlatformDownloader

logger = logging.getLogger(__name__)

# Tracks whether a login flow is already running.
_login_lock = threading.Lock()
_login_in_progress = False

class ThreadsDownloader(BasePlatformDownloader):
    platform_name = "threads"
    url_pattern = re.compile(
        r"(?:https?://)?(?:www\.)?threads\.(?:net|com)/@([^/?#&]+)/post/([^/?#&]+)"
    )
    login_url = "https://www.threads.net/login"

    def get_session_file(self) -> str:
        return settings.threads_session_file

    def get_downloads_dir(self) -> str:
        return settings.threads_downloads_dir

    def extract_post_info(self, url: str, raise_error: bool = True) -> tuple:
        match = self.url_pattern.search(url)
        if not match:
            if raise_error:
                raise ValueError("Invalid Threads URL. Expected: https://www.threads.net/@username/post/POST_ID")
            return "", ""
        return match.group(1), match.group(2)

    def extract_post_id(self, url: str, raise_error: bool = True) -> str:
        _, post_id = self.extract_post_info(url, raise_error)
        return post_id
        
    def extract_username(self, url: str, raise_error: bool = True) -> str:
        username, _ = self.extract_post_info(url, raise_error)
        return username

    def resolve_share_url(self, url: str) -> str:
        if "/share/" not in url:
            return url

        clean_url = url.strip()
        if not clean_url.startswith("http"):
            clean_url = "https://" + clean_url.lstrip("/")

        preferred_domain = "threads.com" if "threads.com" in clean_url else "threads.net"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            session = requests.Session()
            res = session.get(clean_url, headers=headers, allow_redirects=True, timeout=10)

            all_responses = res.history + [res]
            for r in all_responses:
                loc = r.headers.get("Location", "")
                match = re.search(r"/(?P<user>@[^/?#&]+)/post/(?P<postid>[^/?#&]+)", loc)
                if match:
                    resolved = f"https://www.{preferred_domain}/{match.group('user')}/post/{match.group('postid')}"
                    logger.info(f"Resolved share URL from Location header: {url} -> {resolved}")
                    return resolved

                match = re.search(r"/(?P<user>@[^/?#&]+)/post/(?P<postid>[^/?#&]+)", r.url)
                if match:
                    resolved = f"https://www.{preferred_domain}/{match.group('user')}/post/{match.group('postid')}"
                    logger.info(f"Resolved share URL from response URL: {url} -> {resolved}")
                    return resolved
        except Exception as e:
            logger.warning(f"Could not resolve share URL '{url}': {e}")

        return url

    def is_authenticated(self) -> bool:
        return is_authenticated(
            self.get_session_file(), 
            cookie_names={"sessionid", "ds_user_id"}, 
            domains={"instagram.com", "threads.net"}
        )

    def logout_session(self) -> bool:
        return logout_session(self.get_session_file())

    def start_login_flow(self) -> bool:
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
                loop.run_until_complete(self._login_flow_impl())
            except Exception as e:
                logger.error(f"Login flow error: {e}")
            finally:
                _login_in_progress = False
                loop.close()

        threading.Thread(target=_run, daemon=True).start()
        return True

    async def _login_flow_impl(self) -> None:
        os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
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
                        b.textContent = 'ThreadDrop — Log in to Threads below, then CLOSE THIS WINDOW when done.';
                        document.body.prepend(b);
                    }""")
                except Exception:
                    pass

            page.on("load", lambda _: asyncio.ensure_future(inject_banner(page)))
            await page.goto(self.login_url)
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
                    save_state_atomic(state, self.get_session_file())
                except Exception:
                    pass
                await asyncio.sleep(3)

            try:
                state = await context.storage_state()
                save_state_atomic(state, self.get_session_file())
            except Exception:
                pass

            try:
                await browser.close()
            except Exception:
                pass

            if self.is_authenticated():
                logger.info("Threads session verified — user is logged in.")
            else:
                logger.warning("Session saved but no auth cookies found — login incomplete.")

    async def download_post(self, post_url: str, suffix: str = None) -> dict:
        normalized_url = re.sub(r"threads\.com", "threads.net", post_url)
        if not normalized_url.startswith("http"):
            normalized_url = "https://www." + normalized_url.lstrip("/")

        if "/share/" in normalized_url:
            try:
                resolved = self.resolve_share_url(normalized_url)
                resolved = re.sub(r"threads\.com", "threads.net", resolved)
                normalized_url = resolved
            except Exception as e:
                logger.warning(f"Could not resolve share URL, using as-is: {e}")

        username, post_id = self.extract_post_info(normalized_url)
        logger.info(f"Downloading Threads post '{post_id}' by @{username}...")

        intercepted_images: list[str] = []
        intercepted_videos: list[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            if self.is_authenticated():
                context = await browser.new_context(storage_state=self.get_session_file())
                logger.info("Using authenticated Threads session.")
            else:
                context = await browser.new_context()
                logger.info("Anonymous mode — no Threads session loaded.")

            page = await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 900})

            def handle_response(response):
                try:
                    url = response.url
                    content_type = response.headers.get("content-type", "").lower()
                    if not is_cdn_media_url(url):
                        return
                    if ".mp4" in url or "video" in content_type:
                        if url not in intercepted_videos:
                            logger.info(f"Intercepted video: {url[:80]}...")
                            intercepted_videos.append(url)
                    elif "image" in content_type or any(
                        ext in url for ext in (".jpg", ".jpeg", ".png", ".webp")
                    ):
                        if "t51.2885-19" not in url and "t51.29350-19" not in url:
                            if url not in intercepted_images:
                                logger.info(f"Intercepted image: {url[:80]}...")
                                intercepted_images.append(url)
                except Exception:
                    pass

            page.on("response", handle_response)

            await page.goto(normalized_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            current_url = page.url
            if "login" in current_url or "/accounts/" in current_url:
                await browser.close()
                raise RuntimeError(
                    "This Threads post requires a login to view. "
                    "Click 'Login to Threads (Optional)' to connect your account and try again."
                )

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

            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(1200)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(800)

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

            media_urls: list[str] = []
            is_video = False

            for _slide in range(12):
                for img in await page.locator("img").all():
                    try:
                        src = await img.get_attribute("src") or ""
                        if not is_cdn_media_url(src):
                            continue
                        alt = (await img.get_attribute("alt") or "").lower()
                        if "profile" in alt or "avatar" in alt:
                            continue
                        box = await img.bounding_box()
                        if box and box["width"] < 100 and box["height"] < 100:
                            continue
                        if src not in media_urls:
                            logger.info(f"Found image: {src[:80]}...")
                            media_urls.append(src)
                    except Exception:
                        pass

                for vid in await page.locator("video").all():
                    try:
                        is_video = True
                        src = await vid.get_attribute("src") or ""
                        if src.startswith("http") and src not in media_urls:
                            logger.info(f"Found video: {src[:80]}...")
                            media_urls.append(src)
                    except Exception:
                        pass

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

            if not media_urls:
                media_urls.extend(intercepted_images)
                logger.info(f"DOM found nothing; using {len(media_urls)} intercepted image(s).")

            if is_video or intercepted_videos:
                is_video = True
                if not any(".mp4" in u.lower() for u in media_urls) and intercepted_videos:
                    media_urls.append(intercepted_videos[0])

            media_urls = [u for u in media_urls if not u.startswith("blob:")]
            media_urls = deduplicate_by_cdn_path(media_urls)

            if not media_urls:
                await browser.close()
                raise RuntimeError(
                    "No media files found in this Threads post. "
                    "The post may be private, deleted, or the account may require you to follow it."
                )

            download_dir = os.path.abspath(os.path.join(self.get_downloads_dir(), post_id))
            os.makedirs(download_dir, exist_ok=True)
            logger.info(f"Saving {len(media_urls)} file(s) to {download_dir}")

            downloaded_files = []
            for idx, url in enumerate(media_urls):
                filename = build_filename(url, post_id, idx, suffix, is_video=is_video)
                filepath = os.path.join(download_dir, filename)

                try:
                    download_file(url, filepath, referer="https://www.threads.net/")
                    downloaded_files.append(filename)
                except Exception as e:
                    logger.error(f"Failed to download asset {idx}: {e}")

            if not downloaded_files:
                await browser.close()
                raise RuntimeError("Failed to download any of the media files found on this post.")

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

            metadata_file = write_metadata(download_dir, post_metadata)
            logger.info(f"Download complete. Metadata written to {metadata_file}")
            await browser.close()
            return post_metadata
