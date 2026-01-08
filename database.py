from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class Container(Base):
    __tablename__ = "containers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    miners = relationship("Miner", back_populates="container")


class Miner(Base):
    __tablename__ = "miners"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    ip_address = Column(String, nullable=False)
    port = Column(Integer, default=4028)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    
    container = relationship("Container", back_populates="miners")
    stats = relationship("MinerStats", back_populates="miner")


class MinerStats(Base):
    __tablename__ = "miner_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    miner_id = Column(Integer, ForeignKey("miners.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Summary stats
    hash_rate = Column(Float, nullable=True)
    accepted_shares = Column(Integer, nullable=True)
    rejected_shares = Column(Integer, nullable=True)
    pool_switches = Column(Integer, nullable=True)
    
    # Temperature and power
    temperature = Column(Float, nullable=True)
    fan_speed = Column(Integer, nullable=True)
    power_consumption = Column(Float, nullable=True)
    
    # Detailed stats (stored as JSON)
    summary_data = Column(Text, nullable=True)  # JSON
    stats_data = Column(Text, nullable=True)  # JSON
    
    miner = relationship("Miner", back_populates="stats")
    
    def set_summary_data(self, data: dict):
        self.summary_data = json.dumps(data)
    
    def get_summary_data(self) -> dict:
        return json.loads(self.summary_data) if self.summary_data else {}
    
    def set_stats_data(self, data: dict):
        self.stats_data = json.dumps(data)
    
    def get_stats_data(self) -> dict:
        return json.loads(self.stats_data) if self.stats_data else {}


# Database initialization
def init_db(database_url: str = "sqlite:///./miners_monitoring.db"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})
    Base.metadata.create_all(bind=engine)
    return engine


def get_session_maker(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
