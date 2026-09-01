import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass
class Settings:
    """Centralized configuration loaded from environment variables."""
    DOWNLOADS_BASE_DIR: str = os.getenv("DOWNLOADS_BASE_DIR", "downloads")
    SESSIONS_DIR: str = os.getenv("SESSIONS_DIR", ".sessions")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    GOOGLE_SHEETS_ID: str = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "")
    AWS_DEFAULT_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

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
