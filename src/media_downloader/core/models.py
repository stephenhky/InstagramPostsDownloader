from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, field_validator

class DownloadRequest(BaseModel):
    url: str
    suffix: Optional[str] = None

class BatchDownloadItem(BaseModel):
    url: str
    suffix: Optional[str] = None

class BatchDownloadRequest(BaseModel):
    items: List[BatchDownloadItem]

    @field_validator("items")
    @classmethod
    def validate_items_count(cls, v):
        if len(v) == 0:
            raise ValueError("At least one post URL is required.")
        if len(v) > 9:
            raise ValueError("Maximum of 9 posts can be downloaded at once.")
        return v

class OpenFolderRequest(BaseModel):
    identifier: Optional[str] = None

class ResolveUrlRequest(BaseModel):
    url: str

class SpreadsheetDownloadPostRequest(BaseModel):
    url: str
    suffix: Optional[str] = None
    rectified_link: Optional[str] = None

class SpreadsheetPostItem(BaseModel):
    datetime: str
    link: str
    rectified_link: Optional[str] = None
    username: str
    platform: Literal["instagram", "threads"]
    status: Literal["PENDING", "RENAMED", "DOWNLOADED"]
    comment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SpreadsheetSyncResponse(BaseModel):
    success: bool
    posts: List[SpreadsheetPostItem]
    pending_count: int
    downloaded_count: int
    message: Optional[str] = None

class SpreadsheetDownloadPendingResponse(BaseModel):
    success: bool
    total_pending: int
    succeeded: int
    failed: int
    results: List[Dict[str, Any]]
