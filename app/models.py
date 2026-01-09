from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SiteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None


class SiteResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location: Optional[str]
    created_at: datetime
    container_count: int = 0
    
    class Config:
        from_attributes = True


class ContainerCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    site_id: Optional[int] = None


class ContainerResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location: Optional[str]
    site_id: Optional[int] = None
    created_at: datetime
    miner_count: int = 0
    site_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class PoolCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PoolResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    miner_count: int = 0
    
    class Config:
        from_attributes = True


class MinerCreate(BaseModel):
    name: str
    ip_address: str
    port: int = 4028
    manufacturer: Optional[str] = None  # AntMiner, Avalon, Elhapex, Whatsminer
    model: Optional[str] = None
    container_id: Optional[int] = None
    pool_id: Optional[int] = None
    is_active: bool = True


class MinerUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None  # Только для администраторов
    port: Optional[int] = None  # Только для администраторов
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    container_id: Optional[int] = None
    pool_id: Optional[int] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class MinerResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    port: int
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    container_id: Optional[int]
    pool_id: Optional[int] = None
    tags: Optional[List[str]] = None
    is_active: bool
    is_auto_discovered: bool = False
    created_at: datetime
    last_seen: Optional[datetime]
    container_name: Optional[str] = None
    pool_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class NetworkScanRequest(BaseModel):
    network: str  # Например: "192.168.1.0/24"
    port: int = 4028
    timeout: float = 2.0


class DiscoveredMiner(BaseModel):
    ip_address: str
    port: int
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    is_accessible: bool
    error: Optional[str] = None


class MinerStatsResponse(BaseModel):
    id: int
    miner_id: int
    timestamp: datetime
    hash_rate: Optional[float]
    accepted_shares: Optional[int]
    rejected_shares: Optional[int]
    pool_switches: Optional[int]
    temperature: Optional[float]
    fan_speed: Optional[int]
    power_consumption: Optional[float]
    
    class Config:
        from_attributes = True


class MinerStatsWithMiner(BaseModel):
    id: int
    miner_id: int
    miner_name: str
    timestamp: datetime
    hash_rate: Optional[float]
    accepted_shares: Optional[int]
    rejected_shares: Optional[int]
    temperature: Optional[float]
    fan_speed: Optional[int]
    power_consumption: Optional[float]


class ContainerStats(BaseModel):
    container_id: int
    container_name: str
    total_miners: int
    active_miners: int
    total_hash_rate: Optional[float]
    avg_temperature: Optional[float]
    avg_power_consumption: Optional[float]


class PoolStats(BaseModel):
    pool_id: int
    pool_name: str
    total_miners: int
    active_miners: int
    total_hash_rate: Optional[float]
    avg_temperature: Optional[float]
    avg_power_consumption: Optional[float]


class SiteStats(BaseModel):
    site_id: int
    site_name: str
    total_containers: int
    total_miners: int
    active_miners: int
    total_hash_rate: Optional[float]
    avg_temperature: Optional[float]
    avg_power_consumption: Optional[float]


class TagListResponse(BaseModel):
    tags: List[str]


# ============ AGENT MODELS ============

class AgentRegisterRequest(BaseModel):
    """Запрос на регистрацию агента"""
    name: str
    description: Optional[str] = None
    site_id: Optional[int] = None


class AgentRegisterResponse(BaseModel):
    """Ответ при регистрации агента"""
    id: int
    name: str
    api_key: str
    site_id: Optional[int] = None
    message: str


class AgentMinerData(BaseModel):
    """Данные о майнере от агента"""
    ip_address: str
    port: int = 4028
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    name: Optional[str] = None
    container_id: Optional[int] = None
    pool_id: Optional[int] = None
    tags: Optional[List[str]] = None


class AgentMinerStats(BaseModel):
    """Статистика майнера от агента"""
    ip_address: str
    port: int = 4028
    timestamp: datetime
    hash_rate: Optional[float] = None
    accepted_shares: Optional[int] = None
    rejected_shares: Optional[int] = None
    pool_switches: Optional[int] = None
    temperature: Optional[float] = None
    fan_speed: Optional[int] = None
    power_consumption: Optional[float] = None
    summary_data: Optional[dict] = None
    stats_data: Optional[dict] = None


class AgentSyncRequest(BaseModel):
    """Запрос на синхронизацию данных от агента"""
    discovered_miners: List[AgentMinerData] = []
    miner_stats: List[AgentMinerStats] = []


class AgentSyncResponse(BaseModel):
    """Ответ на синхронизацию данных"""
    miners_added: int = 0
    miners_updated: int = 0
    stats_added: int = 0
    errors: List[str] = []
