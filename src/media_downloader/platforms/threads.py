import os
import re
import json
import logging
import asyncio
import threading
import time
from datetime import datetime
from typing import Any, Optional, Tuple, List, Dict
import urllib.parse
import requests
from playwright.async_api import async_playwright

from media_downloader.core.config import settings
from media_downloader.core.session import is_authenticated, logout_session, save_state_atomic
from media_downloader.core.downloader import download_file, is_cdn_media_url, deduplicate_by_cdn_path, build_filename, write_metadata
from media_downloader.platforms.base import BasePlatformDownloader

logger = logging.getLogger(__name__)


def _extract_media_from_post_dict(post_dict: dict) -> dict:
    """Extracts owner, caption, and ordered list of media items from a Threads post dictionary."""
    user = post_dict.get("user") or {}
    owner_username = user.get("username")

    caption_obj = post_dict.get("caption")
    caption = caption_obj.get("text") if isinstance(caption_obj, dict) else ""
    taken_at = post_dict.get("taken_at")

    carousel_media = post_dict.get("carousel_media")
    media_items = []

    def get_best_image_url(image_versions2):
        if not image_versions2 or not isinstance(image_versions2, dict):
            return None
        candidates = image_versions2.get("candidates", [])
        if not candidates:
            return None
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (c.get("width", 0) or 0) * (c.get("height", 0) or 0),
            reverse=True,
        )
        return sorted_candidates[0].get("url")

    def get_best_video_url(video_versions):
        if not video_versions or not isinstance(video_versions, list):
            return None
        sorted_vids = sorted(
            video_versions,
            key=lambda v: (v.get("width", 0) or 0) * (v.get("height", 0) or 0),
            reverse=True,
        )
        return sorted_vids[0].get("url") if sorted_vids else None

    has_video = False

    if carousel_media and isinstance(carousel_media, list):
        for item in carousel_media:
            vid_url = get_best_video_url(item.get("video_versions"))
            if vid_url:
                has_video = True
                media_items.append({"type": "video", "url": vid_url})
            else:
                img_url = get_best_image_url(item.get("image_versions2"))
                if img_url:
                    media_items.append({"type": "image", "url": img_url})
    else:
        vid_url = get_best_video_url(post_dict.get("video_versions"))
        if vid_url:
            has_video = True
            media_items.append({"type": "video", "url": vid_url})
        else:
            img_url = get_best_image_url(post_dict.get("image_versions2"))
            if img_url:
                media_items.append({"type": "image", "url": img_url})

    return {
        "owner_username": owner_username,
        "caption": caption,
        "is_video": has_video,
        "taken_at": taken_at,
        "media_items": media_items,
        "profile_bio": user.get("biography", "") or "",
    }


def _find_target_post(data: Any, post_code: str) -> dict | None:
    """Recursively searches a JSON structure for the post object matching post_code."""
    candidates = []

    def search(obj):
        if isinstance(obj, dict):
            if (obj.get("code") == post_code or obj.get("pk") == post_code or obj.get("id") == post_code) and (
                "user" in obj or "carousel_media" in obj or "image_versions2" in obj or "video_versions" in obj
            ):
                candidates.append(obj)
            for v in obj.values():
                search(v)
        elif isinstance(obj, list):
            for item in obj:
                search(item)

    search(data)
    candidates.sort(
        key=lambda c: (
            1 if (c.get("user") and isinstance(c.get("user"), dict) and c.get("user", {}).get("username")) else 0,
            1 if (c.get("carousel_media") or c.get("image_versions2") or c.get("video_versions")) else 0,
            1 if c.get("caption") else 0,
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


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

    def __init__(self):
        self._login_lock = asyncio.Lock()
        self._login_in_progress = False

    def is_authenticated(self) -> bool:
        return is_authenticated(
            self.get_session_file(),
            cookie_names={"sessionid", "ds_user_id"},
            domains={"instagram.com", "threads.net"},
        )

    def logout_session(self) -> bool:
        return logout_session(self.get_session_file())

    async def start_login_flow(self) -> bool:
        if self._login_in_progress:
            logger.info("Threads login already in progress.")
            return False

        async with self._login_lock:
            self._login_in_progress = True
            try:
                return await self._login_flow_impl()
            finally:
                self._login_in_progress = False

    async def _login_flow_impl(self) -> bool:
        os.makedirs(settings.SESSIONS_DIR, exist_ok=True)
        logger.info("Starting interactive headed login flow for Threads...")

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
                        b.textContent = 'ThreadDrop — Log in to Threads below. Once logged in, session will save automatically.';
                        document.body.prepend(b);
                    }""")
                except Exception:
                    pass

            page.on("load", lambda _: asyncio.ensure_future(inject_banner(page)))
            await page.goto(self.login_url)
            await inject_banner(page)

            logger.info("Browser open — waiting for user to log in.")

            timeout_seconds = 240
            start_time = time.time()
            logged_in = False

            while time.time() - start_time < timeout_seconds:
                if page.is_closed():
                    logger.info("Browser window closed by user.")
                    break

                try:
                    cookies = await context.cookies()
                    if any(c.get('name') in {'sessionid', 'ds_user_id'} for c in cookies):
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
                    logger.info(f"Threads authentication state saved to {self.get_session_file()}")
                    success = True
                except Exception as e:
                    logger.error(f"Error saving storage state: {e}")
                    success = False
            else:
                try:
                    cookies = await context.cookies()
                    if any(c.get('name') in {'sessionid', 'ds_user_id'} for c in cookies):
                        state = await context.storage_state()
                        save_state_atomic(state, self.get_session_file())
                        logger.info(f"Threads session saved from closed window: {self.get_session_file()}")
                        success = True
                    else:
                        logger.warning("No Threads auth cookies found.")
                        success = False
                except Exception:
                    success = False

            try:
                await browser.close()
            except Exception:
                pass

            if self.is_authenticated():
                logger.info("Threads session verified — user is logged in.")
                return True
            else:
                return success

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

        extracted_username, post_id = self.extract_post_info(normalized_url)
        logger.info(f"Downloading Threads post '{post_id}' by @{extracted_username} from {normalized_url}...")

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

            # Capture GraphQL / API response bodies matching post_id
            intercepted_json_bodies = []

            async def handle_response(response):
                try:
                    url = response.url
                    content_type = response.headers.get("content-type", "").lower()
                    if "json" in content_type or "text" in content_type:
                        if "graphql" in url or "api" in url or "threads.net" in url:
                            text = await response.text()
                            if post_id in text:
                                intercepted_json_bodies.append(text)
                except Exception:
                    pass

            page.on("response", handle_response)

            logger.info(f"Navigating to Threads post: {normalized_url}")
            await page.goto(normalized_url, wait_until="networkidle", timeout=30000)
            logger.info(f"Page loaded. Current URL: {page.url}")
            await page.wait_for_timeout(1500)

            current_url = page.url
            if "login" in current_url or "/accounts/" in current_url:
                await browser.close()
                logger.error("Threads post requires login: %s", normalized_url)
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
                logger.error("Threads account is private: @%s post %s", extracted_username, post_id)
                raise RuntimeError(
                    f"This account is private. You must be following @{extracted_username} "
                    f"on the Threads account you logged in with to download their posts."
                )

            # Strategy 1: Extract structured JSON data embedded in <script type="application/json">
            scripts = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('script[type="application/json"]')).map(s => s.textContent);
            }""")

            target_post_dict = None
            for s in scripts:
                try:
                    data = json.loads(s)
                    found = _find_target_post(data, post_id)
                    if found:
                        target_post_dict = found
                        break
                except Exception:
                    pass

            # Strategy 2: Check intercepted JSON responses
            if not target_post_dict:
                for s in intercepted_json_bodies:
                    try:
                        data = json.loads(s)
                        found = _find_target_post(data, post_id)
                        if found:
                            target_post_dict = found
                            break
                    except Exception:
                        pass

            owner_username = extracted_username
            caption = ""
            is_video = False
            media_items = []
            profile_bio = ""
            profile_usernames = [extracted_username]

            if target_post_dict:
                logger.info(f"Successfully located structured post data for {post_id}.")
                extracted = _extract_media_from_post_dict(target_post_dict)
                owner_username = extracted["owner_username"] or extracted_username
                caption = extracted["caption"]
                is_video = extracted["is_video"]
                media_items = extracted["media_items"]
                profile_bio = extracted.get("profile_bio", "")
                profile_usernames = [owner_username]
                logger.info(f"Extracted {len(media_items)} media item(s) from structured data for {post_id}.")
            else:
                logger.warning(f"Structured post data not found in scripts for {post_id}. Attempting metadata/DOM fallback...")
                # Fallback: Extract metadata from OpenGraph / Twitter meta tags
                meta_info = await page.evaluate("""() => {
                    const result = {};
                    document.querySelectorAll('meta').forEach(m => {
                        const prop = m.getAttribute('property') || m.getAttribute('name');
                        const val = m.getAttribute('content');
                        if (prop && val) result[prop] = val;
                    });
                    return result;
                }""")

                caption = meta_info.get("og:description") or meta_info.get("description") or meta_info.get("twitter:description") or ""
                title = meta_info.get("og:title") or meta_info.get("twitter:title") or ""
                # Parse title like "Name (@username) on Threads"
                match_author = re.search(r"@([a-zA-Z0-9._]+)", title)
                if match_author:
                    owner_username = match_author.group(1)

                # Find primary media from OpenGraph
                og_image = meta_info.get("og:image") or meta_info.get("twitter:image")
                og_video = meta_info.get("og:video")

                if og_video and is_cdn_media_url(og_video):
                    is_video = True
                    media_items.append({"type": "video", "url": og_video})
                elif og_image and is_cdn_media_url(og_image):
                    media_items.append({"type": "image", "url": og_image})

                logger.info(f"Fallback extracted {len(media_items)} media item(s) from meta tags for {post_id}.")

            if not profile_bio and owner_username:
                try:
                    profile_page = await context.new_page()
                    await profile_page.goto(f"https://www.threads.net/@{owner_username}", wait_until="networkidle", timeout=15000)
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
                    desc = p_meta.get("description") or p_meta.get("og:description") or ""
                    m_bio = re.search(r'Threads\s*•\s*(.*?)\s*See the latest conversations', desc, re.DOTALL)
                    if m_bio:
                        profile_bio = m_bio.group(1).strip()
                    elif "•" in desc:
                        parts = desc.split("•")
                        if len(parts) >= 3:
                            profile_bio = parts[-1].split("See the latest")[0].strip()
                    elif desc:
                        profile_bio = desc.strip()
                    await profile_page.close()
                except Exception as e:
                    logger.warning(f"Could not fetch Threads profile bio for @{owner_username}: {e}")

            if not media_items:
                await browser.close()
                logger.error("No media files found for Threads post %s", post_id)
                raise RuntimeError(
                    "No media files found in this Threads post. "
                    "The post may be text-only, private, deleted, or the account may require you to follow it."
                )

            download_dir = os.path.abspath(os.path.join(self.get_downloads_dir(), post_id))
            os.makedirs(download_dir, exist_ok=True)
            logger.info(f"Saving {len(media_items)} file(s) to {download_dir}")

            downloaded_files = []
            for idx, item in enumerate(media_items):
                item_url = item["url"]
                is_item_video = (item["type"] == "video")
                filename = build_filename(item_url, post_id, idx, suffix, is_video=is_item_video)
                filepath = os.path.join(download_dir, filename)

                try:
                    download_file(item_url, filepath, referer="https://www.threads.net/")
                    downloaded_files.append(filename)
                except Exception as e:
                    logger.error(f"Failed to download asset {idx} for {post_id} ({item_url[:60]}...): {e}")

            logger.info(f"Downloaded {len(downloaded_files)}/{len(media_items)} assets for Threads post {post_id}.")
            if not downloaded_files:
                await browser.close()
                raise RuntimeError("Failed to download any of the media files found on this post.")

            post_metadata = {
                "post_id": post_id,
                "url": f"https://www.threads.net/@{owner_username}/post/{post_id}",
                "original_link": post_url,
                "rectified_link": normalized_url,
                "owner_username": owner_username,
                "caption": caption,
                "is_video": is_video,
                "date_utc": datetime.utcnow().isoformat(),
                "downloaded_at": datetime.utcnow().isoformat(),
                "media_files": downloaded_files,
                "profile_bio": profile_bio,
                "profile_usernames": profile_usernames,
            }

            metadata_file = write_metadata(download_dir, post_metadata)
            logger.info(f"Download complete. Metadata written to {metadata_file}")
            await browser.close()
            return post_metadata
