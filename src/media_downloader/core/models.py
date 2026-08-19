from typing import Optional, List
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
