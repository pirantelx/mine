from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Database - читается из переменной окружения DATABASE_URL, если не задана - используется SQLite
    database_url: str = "sqlite:///./miners_monitoring.db"
    
    # Security
    secret_key: str = "change-this-secret-key-in-production-please-use-strong-random-key"
    
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
        case_sensitive = False


settings = Settings()
