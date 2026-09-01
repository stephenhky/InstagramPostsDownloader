from abc import ABC, abstractmethod
import re

class BasePlatformDownloader(ABC):
    platform_name: str
    url_pattern: re.Pattern
    login_url: str
    
    @abstractmethod
    def get_session_file(self) -> str:
        ...
    
    @abstractmethod
    def get_downloads_dir(self) -> str:
        ...
    
    @abstractmethod
    def extract_post_id(self, url: str, raise_error: bool = True) -> str:
        ...
    
    @abstractmethod
    async def download_post(self, post_url: str, suffix: str = None) -> dict:
        ...
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        ...
        
    @abstractmethod
    def logout_session(self) -> bool:
        ...

    @abstractmethod
    async def start_login_flow(self) -> bool:
        ...
