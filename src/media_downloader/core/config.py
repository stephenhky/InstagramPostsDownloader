import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Centralized configuration loaded from environment variables."""
    DOWNLOADS_BASE_DIR: str = os.getenv("DOWNLOADS_BASE_DIR", "downloads")
    SESSIONS_DIR: str = os.getenv("SESSIONS_DIR", "sessions")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

    @property
    def instagram_downloads_dir(self) -> str:
        return os.path.join(self.DOWNLOADS_BASE_DIR, "instagram")

    @property
    def threads_downloads_dir(self) -> str:
        return os.path.join(self.DOWNLOADS_BASE_DIR, "threads")

    @property
    def instagram_session_file(self) -> str:
        return os.path.join(self.SESSIONS_DIR, "playwright_auth.json")

    @property
    def threads_session_file(self) -> str:
        return os.path.join(self.SESSIONS_DIR, "threads_auth.json")


settings = Settings()
