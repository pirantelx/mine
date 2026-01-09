from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List
import json
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    """Роли пользователей"""
    ADMIN = "admin"  # Администратор - полный доступ
    ACCOUNTANT = "accountant"  # Бухгалтер - просмотр статистики и отчетов
    CLIENT = "client"  # Клиент - просмотр своих данных


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.CLIENT, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Связь с контейнерами (какие контейнеры доступны пользователю)
    accessible_containers = relationship("UserContainerAccess", back_populates="user")


class UserContainerAccess(Base):
    __tablename__ = "user_container_access"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="accessible_containers")
    container = relationship("Container", back_populates="accessible_users")


class Site(Base):
    __tablename__ = "sites"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    containers = relationship("Container", back_populates="site")


class Container(Base):
    __tablename__ = "containers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    site = relationship("Site", back_populates="containers")
    miners = relationship("Miner", back_populates="container")
    accessible_users = relationship("UserContainerAccess", back_populates="container")


class Pool(Base):
    __tablename__ = "pools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    miners = relationship("Miner", back_populates="pool")


class Miner(Base):
    __tablename__ = "miners"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    ip_address = Column(String, nullable=False)
    port = Column(Integer, default=4028)
    manufacturer = Column(String, nullable=True, index=True)  # AntMiner, Avalon, Elhapex, Whatsminer
    model = Column(String, nullable=True, index=True)  # Модель майнера
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=True, index=True)
    tags = Column(Text, nullable=True)  # JSON массив тегов
    is_active = Column(Boolean, default=True)
    is_auto_discovered = Column(Boolean, default=False)  # Автоматически обнаружен
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    
    container = relationship("Container", back_populates="miners")
    pool = relationship("Pool", back_populates="miners")
    stats = relationship("MinerStats", back_populates="miner")
    
    def get_tags(self) -> List[str]:
        """Получение списка тегов майнера"""
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []
    
    def set_tags(self, tags: List[str]):
        """Установка тегов майнера"""
        self.tags = json.dumps(tags) if tags else None


class Agent(Base):
    """Агент - клиентское приложение, работающее на площадке"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)  # Уникальное имя агента
    api_key = Column(String, unique=True, index=True, nullable=False)  # API ключ для аутентификации
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True, index=True)  # Привязка к площадке
    description = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)  # IP адрес агента
    last_seen = Column(DateTime, nullable=True)  # Последний раз когда агент отправлял данные
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    site = relationship("Site", backref="agents")


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
