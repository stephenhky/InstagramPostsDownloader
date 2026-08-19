# Media Downloader

A self-hosted tool for downloading Instagram and Threads posts (images, videos, carousels) via a local web UI. Built with FastAPI + Playwright.

## Features

- **Instagram & Threads** — single unified app with platform toggle
- **Single & batch downloads** — up to 9 posts at once
- **Carousel support** — automatically navigates and downloads all slides
- **Custom filename suffixes** — add tags to downloaded files
- **Download history** — browse previously downloaded posts
- **Session management** — Playwright-based login flow with persistent cookies

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/stephenhky/InstagramPostsDownloader.git
cd InstagramPostsDownloader

# 2. Create environment and install
conda activate instadownload   # or use your preferred env
pip install -e .
playwright install chromium

# 3. Run
media-downloader
```

The web UI opens at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Project Structure

```
src/media_downloader/
├── core/           # Shared config, session, download utilities
├── platforms/      # Instagram & Threads scrapers
├── api/            # Unified FastAPI app + routes
└── cli.py          # Launcher
frontend/           # HTML templates, CSS, JS
```

## Configuration

Copy `.env.example` to `.env` to customize:

```bash
SERVER_HOST=127.0.0.1
SERVER_PORT=8000
DOWNLOADS_BASE_DIR=downloads
SESSIONS_DIR=sessions
```
