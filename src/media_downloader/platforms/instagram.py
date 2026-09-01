import os
import re
import json
import logging
import asyncio
import time
from datetime import datetime
import instaloader
import urllib.parse
from playwright.async_api import async_playwright

from media_downloader.core.config import settings
from media_downloader.core.session import is_authenticated, logout_session, save_state_atomic
from media_downloader.core.downloader import download_file, extract_url_digits, build_filename, write_metadata
from media_downloader.platforms.base import BasePlatformDownloader

logger = logging.getLogger(__name__)

class InstagramDownloader(BasePlatformDownloader):
    platform_name = "instagram"
    url_pattern = re.compile(
        r"(?:(?:https?://)?(?:www\.)?instagram\.com)?/?(?:[^/]+/)?(?:p|reel|tv)/([^/?#&]+)"
    )
    login_url = "https://www.instagram.com/accounts/login/"

    def get_session_file(self) -> str:
        return settings.instagram_session_file

    def get_downloads_dir(self) -> str:
        return settings.instagram_downloads_dir

    def extract_post_id(self, url: str, raise_error: bool = True) -> str:
        match = self.url_pattern.search(url)
        if not match:
            if raise_error:
                raise ValueError("Invalid Instagram URL pattern. Must be a /p/, /reel/, or /tv/ URL.")
            return ""
        return match.group(1)

    def __init__(self):
        self._login_lock = asyncio.Lock()
        self._login_in_progress = False

    def is_authenticated(self) -> bool:
        return is_authenticated(
            self.get_session_file(),
            cookie_names={"sessionid", "ds_user_id"},
            domains={"instagram.com"}
        )

    def logout_session(self) -> bool:
        return logout_session(self.get_session_file())

    async def start_login_flow(self) -> bool:
        if self._login_in_progress:
            logger.info("Instagram login already in progress.")
            return False

        async with self._login_lock:
            self._login_in_progress = True
            try:
                return await self._login_flow_impl()
            finally:
                self._login_in_progress = False

    async def _login_flow_impl(self) -> bool:
        os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
        logger.info("Starting interactive headed login flow for Instagram...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            async def inject_banner(pg):
                try:
                    await pg.evaluate("""() => {
                        if (document.getElementById('ig-login-banner')) return;
                        const b = document.createElement('div');
                        b.id = 'ig-login-banner';
                        b.style.cssText = [
                            'position:fixed','top:0','left:0','right:0','z-index:2147483647',
                            'background:#e1306c','color:#fff','padding:10px 20px',
                            'text-align:center','font:600 14px/1.4 system-ui,sans-serif',
                            'box-shadow:0 2px 8px rgba(0,0,0,.25)'
                        ].join(';');
                        b.textContent = 'InstaDrop — Log in to Instagram below. Once logged in, session will save automatically.';
                        document.body.prepend(b);
                    }""")
                except Exception:
                    pass

            page.on("load", lambda _: asyncio.ensure_future(inject_banner(page)))
            await page.goto(self.login_url)
            await inject_banner(page)

            logged_in = False
            timeout_seconds = 240
            start_time = time.time()

            logger.info("Please log in manually on the browser window.")

            while time.time() - start_time < timeout_seconds:
                if page.is_closed():
                    logger.warning("Browser window was closed by the user.")
                    break

                try:
                    cookies = await context.cookies()
                    if any(c['name'] == 'sessionid' for c in cookies):
                        logged_in = True
                        break
                except Exception as e:
                    logger.warning(f"Error checking cookies: {e}")

                await asyncio.sleep(2)

            if logged_in:
                logger.info("Login detected. Waiting 3 seconds for session cookies and storage to settle...")
                try:
                    await page.wait_for_timeout(3000)
                except Exception:
                    pass

                try:
                    state = await context.storage_state()
                    save_state_atomic(state, self.get_session_file())
                    logger.info(f"Authentication state saved to {self.get_session_file()}")
                    success = True
                except Exception as e:
                    logger.error(f"Error saving storage state: {e}")
                    success = False
            else:
                # If window was closed, still try to save if session cookies exist
                try:
                    cookies = await context.cookies()
                    if any(c['name'] == 'sessionid' for c in cookies):
                        state = await context.storage_state()
                        save_state_atomic(state, self.get_session_file())
                        logger.info(f"Session saved from closed window: {self.get_session_file()}")
                        success = True
                    else:
                        logger.warning("No sessionid cookie found.")
                        success = False
                except Exception:
                    success = False

            try:
                await browser.close()
            except Exception:
                pass

            return success

    def _get_post_media_filenames_anonymous(self, shortcode: str) -> list:
        logger.info("Attempting to fetch post metadata anonymously using Instaloader...")
        try:
            L = instaloader.Instaloader()
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
            valid_digits = []
            
            if post.typename == 'GraphSidecar':
                for node in post.get_sidecar_nodes():
                    if node.display_url:
                        digits = extract_url_digits(node.display_url)
                        if digits and digits not in valid_digits:
                            valid_digits.append(digits)
                    if node.is_video and node.video_url:
                        digits = extract_url_digits(node.video_url)
                        if digits and digits not in valid_digits:
                            valid_digits.append(digits)
            else:
                if post.url:
                    digits = extract_url_digits(post.url)
                    if digits and digits not in valid_digits:
                        valid_digits.append(digits)
                if post.is_video and post.video_url:
                    digits = extract_url_digits(post.video_url)
                    if digits and digits not in valid_digits:
                        valid_digits.append(digits)
                        
            logger.info(f"Instaloader anonymous check succeeded. Valid media base digits: {valid_digits}")
            return valid_digits
        except Exception as e:
            logger.warning(f"Instaloader anonymous metadata fetch failed: {e}. Scraper will proceed without filename filtering.")
            return None

    async def download_post(self, post_url: str, suffix: str = None) -> dict:
        if not self.is_authenticated():
            logger.error("Instagram account not connected. Please log in first.")
            raise RuntimeError("Instagram account not connected. Please log in first.")
            
        shortcode = self.extract_post_id(post_url)
        logger.info(f"Downloading Instagram post {shortcode} from {post_url}...")

        valid_digits = self._get_post_media_filenames_anonymous(shortcode)
        logger.debug(f"Valid media digits for {shortcode}: {valid_digits}")
        intercepted_videos = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=self.get_session_file())
            page = await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            
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
            
            logger.info(f"Navigating to Instagram post: {post_url}")
            await page.goto(post_url, wait_until="load")
            logger.info(f"Page loaded. Current URL: {page.url}")
            
            try:
                await page.wait_for_selector(
                    "article img, video, input[name='username'], text='This Account is Private', text='This account is private', text='Sorry, this page'", 
                    timeout=15000
                )
                logger.info("Key post elements selector matched.")
            except Exception:
                logger.warning("Timeout waiting for key post elements to load.")
                
            await page.wait_for_timeout(1500)
            
            login_form_visible = False
            try:
                username_input = page.locator("input[name='username']").first
                if await username_input.is_visible():
                    login_form_visible = True
            except Exception:
                pass

            if "accounts/login" in page.url or login_form_visible:
                await browser.close()
                self.logout_session()
                logger.error("Instagram session invalid or expired for post %s", shortcode)
                raise RuntimeError("Your Instagram session is invalid or has expired. Please disconnect and reconnect your account.")

            private_visible = False
            try:
                private_loc = page.locator("text='This Account is Private', text='This account is private'").first
                if await private_loc.is_visible():
                    private_visible = True
            except Exception:
                pass

            if private_visible:
                await browser.close()
                logger.error("Instagram account is private for post %s", shortcode)
                raise RuntimeError("This account is private. You must follow this account on your connected Instagram profile to download its media.")

            main_article = page.locator("article").first
            if not await main_article.is_visible():
                logger.warning("Main <article> container not visible. Using page body/main fallbacks.")
                main_loc = page.locator("main").first
                if await main_loc.is_visible():
                    main_article = main_loc
                else:
                    main_article = page.locator("body")

            # Extract meta tags for username, caption, and title
            meta_info = await page.evaluate("""() => {
                const res = {};
                document.querySelectorAll('meta').forEach(m => {
                    const k = m.getAttribute('property') || m.getAttribute('name');
                    const v = m.getAttribute('content');
                    if (k && v) res[k] = v;
                });
                return res;
            }""")

            og_desc = meta_info.get("og:description") or meta_info.get("description") or ""
            og_title = meta_info.get("og:title") or ""
            page_title = await page.title()

            owner_username = "instagram_user"
            caption = ""

            # 1. Try regex from og_desc: '... - username on date: "caption"'
            m = re.search(r'-\s+([a-zA-Z0-9._]+)\s+on\s+[^:]+:\s*\"(.*?)\"', og_desc, re.DOTALL)
            if m:
                owner_username = m.group(1)
                caption = m.group(2)
            else:
                m_user = re.search(r'-\s+([a-zA-Z0-9._]+)\s+on', og_desc)
                if m_user:
                    owner_username = m_user.group(1)

            if owner_username == "instagram_user":
                m_title = re.search(r'@([a-zA-Z0-9._]+)', page_title)
                if m_title:
                    owner_username = m_title.group(1)

            if owner_username == "instagram_user":
                try:
                    username_loc = main_article.locator("header a[href^='/']").first
                    if await username_loc.is_visible():
                        owner_username = (await username_loc.text_content()).strip()
                except Exception as e:
                    logger.warning(f"Could not find username link: {e}")

            if not caption:
                m_cap = re.search(r':\s*\"(.*?)\"', og_title, re.DOTALL)
                if m_cap:
                    caption = m_cap.group(1)
                else:
                    try:
                        h1_loc = main_article.locator("h1").first
                        if await h1_loc.is_visible():
                            caption = (await h1_loc.text_content()).strip()
                    except Exception as e:
                        logger.warning(f"Could not find caption: {e}")

            profile_bio = ""
            profile_usernames = [owner_username]
            if owner_username and owner_username != "instagram_user":
                try:
                    profile_page = await context.new_page()
                    await profile_page.goto(f"https://www.instagram.com/{owner_username}/", wait_until="load", timeout=15000)
                    await profile_page.wait_for_timeout(1000)
                    p_meta = await profile_page.evaluate("""() => {
                        const res = {};
                        document.querySelectorAll('meta').forEach(m => {
                            const k = m.getAttribute('property') || m.getAttribute('name');
                            const v = m.getAttribute('content');
                            if (k && v) res[k] = v;
                        });
                        return res;
                    }""")
                    p_desc = p_meta.get("description") or p_meta.get("og:description") or ""
                    m_bio = re.search(r':\s*\"(.*?)\"$', p_desc, re.DOTALL)
                    if m_bio:
                        profile_bio = m_bio.group(1).strip()
                    elif p_desc:
                        profile_bio = p_desc.strip()
                    await profile_page.close()
                except Exception as e:
                    logger.warning(f"Could not fetch profile bio for @{owner_username}: {e}")

            media_urls = []
            is_video = False
            
            for slide_idx in range(12):
                images = await main_article.locator("img").all()
                for img in images:
                    try:
                        alt = (await img.get_attribute("alt") or "").lower()
                        if "profile picture" in alt or "avatar" in alt:
                            continue
                            
                        box = await img.bounding_box()
                        if box and (box['width'] < 250 or box['height'] < 250):
                            continue
                            
                        src = await img.get_attribute("src")
                        if src and "scontent" in src and src not in media_urls:
                            ancestor_href = await img.evaluate("el => { let parent = el.closest('a'); return parent ? parent.getAttribute('href') : null; }")
                            if ancestor_href:
                                ancestor_shortcode = self.extract_post_id(ancestor_href, raise_error=False)
                                if ancestor_shortcode and ancestor_shortcode != shortcode:
                                    logger.info(f"Skipping suggested post image: {src[:80]}... (shortcode: {ancestor_shortcode})")
                                    continue

                            logger.info(f"Found image URL: {src[:80]}...")
                            media_urls.append(src)
                    except Exception:
                        pass

                videos = await main_article.locator("video").all()
                for vid in videos:
                    try:
                        is_video = True
                        src = await vid.get_attribute("src")
                        if src and src.startswith("http") and src not in media_urls:
                            ancestor_href = await vid.evaluate("el => { let parent = el.closest('a'); return parent ? parent.getAttribute('href') : null; }")
                            if ancestor_href:
                                ancestor_shortcode = self.extract_post_id(ancestor_href, raise_error=False)
                                if ancestor_shortcode and ancestor_shortcode != shortcode:
                                    logger.info(f"Skipping suggested post video: {src[:80]}... (shortcode: {ancestor_shortcode})")
                                    continue

                            logger.info(f"Found video URL: {src[:80]}...")
                            media_urls.append(src)
                    except Exception:
                        pass
                
                next_btn = main_article.locator("button[aria-label='Next'], button:has(div > svg[aria-label='Next'])").first
                if await next_btn.is_visible():
                    try:
                        await next_btn.evaluate("el => el.click()")
                        await page.wait_for_timeout(1000)
                    except Exception:
                        break
                else:
                    break
                    
            if is_video or len(intercepted_videos) > 0:
                is_video = True
                if not any("scontent" in url for url in media_urls):
                    if intercepted_videos:
                        media_urls.append(intercepted_videos[0])

            media_urls = [url for url in media_urls if not url.startswith("blob:")]

            if valid_digits is not None:
                filtered_urls = []
                for url in media_urls:
                    url_digits = extract_url_digits(url)
                    if url_digits in valid_digits:
                        filtered_urls.append(url)
                    else:
                        logger.info(f"Skipping suggested/unrelated media URL: {url[:80]}...")
                
                if filtered_urls:
                    media_urls = filtered_urls
                else:
                    logger.warning("No media URLs matched the Instaloader anonymous filter. Falling back to all scraped page elements.")

            logger.info(f"Collected {len(media_urls)} media URLs for {shortcode} after filtering.")
            if not media_urls:
                await browser.close()
                raise RuntimeError("Could not locate any media files on this post. Instagram might be blocking access.")

            download_dir = os.path.abspath(os.path.join(self.get_downloads_dir(), shortcode))
            os.makedirs(download_dir, exist_ok=True)
            logger.info(f"Download directory for {shortcode}: {download_dir}")
            
            logger.info(f"Found {len(media_urls)} media URLs. Starting download...")
            
            downloaded_files = []
            for idx, url in enumerate(media_urls):
                filename = build_filename(url, shortcode, idx, suffix, is_video=(is_video and len(media_urls) == 1))
                filepath = os.path.join(download_dir, filename)
                
                try:
                    download_file(url, filepath)
                    downloaded_files.append(filename)
                except Exception as e:
                    logger.error(f"Failed to download asset {idx} for {shortcode}: {e}")

            logger.info(f"Downloaded {len(downloaded_files)}/{len(media_urls)} assets for {shortcode}.")
            if not downloaded_files:
                await browser.close()
                raise RuntimeError("Failed to download any of the retrieved media URLs.")

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
                "media_files": downloaded_files,
                "profile_bio": profile_bio,
                "profile_usernames": profile_usernames,
            }

            metadata_file = write_metadata(download_dir, post_metadata)
            logger.info(f"Download complete! Saved metadata to {metadata_file}")
            await browser.close()
            return post_metadata
