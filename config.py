from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./miners_monitoring.db"
    
    # TCP Settings
    default_miner_port: int = 4028
    connection_timeout: float = 5.0
    read_timeout: float = 10.0
    
    # Polling Settings
    polling_interval: int = 60  # seconds
    max_workers: int = 50  # concurrent connections
    
    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    class Config:
        env_file = ".env"


settings = Settings()
