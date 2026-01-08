from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ContainerCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None


class ContainerResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location: Optional[str]
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
    is_active: bool = True


class MinerUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    container_id: Optional[int] = None
    is_active: Optional[bool] = None


class MinerResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    port: int
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    container_id: Optional[int]
    is_active: bool
    created_at: datetime
    last_seen: Optional[datetime]
    container_name: Optional[str] = None
    
    class Config:
        from_attributes = True


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
