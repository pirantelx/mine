from fastapi import FastAPI, Depends, HTTPException, Query, status, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import os

from app.database import init_db, get_session_maker, Miner, MinerStats, Container, User, UserRole, UserContainerAccess, Pool, Site, Agent
from app.models import (
    ContainerCreate, ContainerResponse, MinerCreate, MinerUpdate,
    MinerResponse, MinerStatsResponse, MinerStatsWithMiner, ContainerStats,
    PoolCreate, PoolResponse, PoolStats, NetworkScanRequest, DiscoveredMiner,
    SiteCreate, SiteResponse, AgentRegisterRequest, AgentRegisterResponse,
    AgentSyncRequest, AgentSyncResponse, AgentMinerData, AgentMinerStats
)
from app.services.monitoring import MonitoringService
from app.services.network_scanner import scan_network
from app.config import settings
from app.miner_models import get_manufacturers, get_models_by_manufacturer, is_valid_manufacturer, is_valid_model
from app.auth import (
    UserCreate, UserLogin, UserResponse, Token, get_password_hash, authenticate_user,
    create_access_token, get_user_by_username, get_user_by_email, get_current_user,
    require_role, can_access_container, can_access_miner, UserRole as AuthUserRole
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
engine = init_db(settings.database_url)
SessionLocal = get_session_maker(engine)

# Глобальный сервис мониторинга
monitoring_service: Optional[MonitoringService] = None

app = FastAPI(title="Miners Monitoring System")

# OAuth2 схема (должна быть определена до использования)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Статические файлы и шаблоны
# Определяем корневую директорию проекта (на уровень выше app/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dependency для получения токена из cookie или заголовка
def get_token_from_request(request: Request) -> Optional[str]:
    """Получение токена из cookie или заголовка Authorization"""
    # Сначала проверяем cookie
    token = request.cookies.get("access_token")
    if token:
        return token
    
    # Если нет в cookie, проверяем заголовок Authorization
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    
    return None


# Dependency для получения текущего пользователя с сессией БД
def get_current_user_with_db(
    request: Request,
    db: Session = Depends(get_db)
):
    """Получение текущего пользователя с передачей сессии БД"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Получаем токен из cookie или заголовка
    token = get_token_from_request(request)
    if not token:
        raise credentials_exception
    
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    from app.auth import get_user_by_username
    user = get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
    return user


# Startup/Shutdown события
@app.on_event("startup")
async def startup_event():
    global monitoring_service
    try:
        # Инициализация базы данных при старте
        from scripts.init_db import init_database
        logger.info("Initializing database...")
        if not init_database():
            logger.warning("Database initialization failed, but continuing...")
        
        monitoring_service = MonitoringService()
        monitoring_service.start()
        logger.info("Application started")
    except Exception as e:
        logger.error(f"Error starting monitoring service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    global monitoring_service
    if monitoring_service:
        monitoring_service.stop()
    logger.info("Application stopped")


# ============ SITES API ============

@app.post("/api/sites", response_model=SiteResponse)
def create_site(
    site: SiteCreate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Создание новой площадки (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create sites"
        )
    
    # Проверяем, нет ли площадки с таким именем
    existing = db.query(Site).filter(Site.name == site.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Site with this name already exists")
    
    db_site = Site(
        name=site.name,
        description=site.description,
        location=site.location
    )
    db.add(db_site)
    db.commit()
    db.refresh(db_site)
    
    container_count = db.query(func.count(Container.id)).filter(Container.site_id == db_site.id).scalar()
    response = SiteResponse.from_orm(db_site)
    response.container_count = container_count
    return response


@app.get("/api/sites", response_model=List[SiteResponse])
def get_sites(
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка всех площадок"""
    sites = db.query(Site).all()
    result = []
    for site in sites:
        container_count = db.query(func.count(Container.id)).filter(Container.site_id == site.id).scalar()
        response = SiteResponse.from_orm(site)
        response.container_count = container_count
        result.append(response)
    return result


@app.get("/api/sites/{site_id}", response_model=SiteResponse)
def get_site(
    site_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение информации о площадке"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    container_count = db.query(func.count(Container.id)).filter(Container.site_id == site_id).scalar()
    response = SiteResponse.from_orm(site)
    response.container_count = container_count
    return response


@app.delete("/api/sites/{site_id}")
def delete_site(
    site_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Удаление площадки (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete sites"
        )
    
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Проверяем, есть ли контейнеры в площадке
    containers_count = db.query(func.count(Container.id)).filter(Container.site_id == site_id).scalar()
    if containers_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete site with containers. Remove containers first.")
    
    db.delete(site)
    db.commit()
    return {"message": "Site deleted"}


# ============ CONTAINERS API ============

@app.post("/api/containers", response_model=ContainerResponse)
def create_container(
    container: ContainerCreate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Создание нового контейнера (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create containers"
        )
    
    if container.site_id is not None:
        site = db.query(Site).filter(Site.id == container.site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
    
    db_container = Container(
        name=container.name,
        description=container.description,
        location=container.location,
        site_id=container.site_id
    )
    db.add(db_container)
    db.commit()
    db.refresh(db_container)
    
    # Получаем количество майнеров
    miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == db_container.id).scalar()
    
    response = ContainerResponse.from_orm(db_container)
    response.miner_count = miner_count
    if db_container.site:
        response.site_name = db_container.site.name
    return response


@app.get("/api/containers", response_model=List[ContainerResponse])
def get_containers(
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка контейнеров (с учетом прав доступа)"""
    # Администратор видит все контейнеры
    if current_user.role == UserRole.ADMIN:
        containers = db.query(Container).all()
    else:
        # Остальные видят только доступные им контейнеры
        container_ids = [
            access.container_id 
            for access in db.query(UserContainerAccess).filter(
                UserContainerAccess.user_id == current_user.id
            ).all()
        ]
        if not container_ids:
            return []
        containers = db.query(Container).filter(Container.id.in_(container_ids)).all()
    
    result = []
    for container in containers:
        miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == container.id).scalar()
        response = ContainerResponse.from_orm(container)
        response.miner_count = miner_count
        if container.site:
            response.site_name = container.site.name
        result.append(response)
    return result


@app.get("/api/containers/{container_id}", response_model=ContainerResponse)
def get_container(
    container_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение информации о контейнере (с проверкой прав доступа)"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    # Проверяем доступ
    if not can_access_container(current_user, container_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this container"
        )
    
    miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == container_id).scalar()
    response = ContainerResponse.from_orm(container)
    response.miner_count = miner_count
    return response


@app.delete("/api/containers/{container_id}")
def delete_container(
    container_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Удаление контейнера (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete containers"
        )
    
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    # Проверяем, есть ли майнеры в контейнере
    miners_count = db.query(func.count(Miner.id)).filter(Miner.container_id == container_id).scalar()
    if miners_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete container with miners. Remove miners first.")
    
    db.delete(container)
    db.commit()
    return {"message": "Container deleted"}


# ============ MINERS API ============

@app.post("/api/miners", response_model=MinerResponse)
def create_miner(
    miner: MinerCreate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Создание нового майнера (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create miners"
        )
    
    # Проверяем, существует ли контейнер
    if miner.container_id:
        container = db.query(Container).filter(Container.id == miner.container_id).first()
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
    
    if miner.pool_id:
        pool = db.query(Pool).filter(Pool.id == miner.pool_id).first()
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")
    
    db_miner = Miner(
        name=miner.name,
        ip_address=miner.ip_address,
        port=miner.port,
        manufacturer=miner.manufacturer,
        model=miner.model,
        container_id=miner.container_id,
        pool_id=miner.pool_id,
        is_active=miner.is_active
    )
    if miner.tags:
        db_miner.set_tags(miner.tags)
    db.add(db_miner)
    db.commit()
    db.refresh(db_miner)
    
    response = MinerResponse.from_orm(db_miner)
    response.tags = db_miner.get_tags()
    if db_miner.container:
        response.container_name = db_miner.container.name
    if db_miner.pool:
        response.pool_name = db_miner.pool.name
    return response


@app.get("/api/miners", response_model=List[MinerResponse])
def get_miners(
    container_id: Optional[int] = Query(None, description="Filter by container ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка майнеров (с учетом прав доступа)"""
    query = db.query(Miner)
    
    # Администратор видит все майнеры
    if current_user.role != UserRole.ADMIN:
        # Остальные видят только майнеры из доступных контейнеров
        container_ids = [
            access.container_id 
            for access in db.query(UserContainerAccess).filter(
                UserContainerAccess.user_id == current_user.id
            ).all()
        ]
        if not container_ids:
            return []
        query = query.filter(Miner.container_id.in_(container_ids))
    
    if container_id is not None:
        # Проверяем доступ к контейнеру
        if current_user.role != UserRole.ADMIN:
            if not can_access_container(current_user, container_id, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this container"
                )
        query = query.filter(Miner.container_id == container_id)
    
    if pool_id is not None:
        query = query.filter(Miner.pool_id == pool_id)
    
    if site_id is not None:
        # Фильтруем по площадке через контейнеры
        query = query.join(Container).filter(Container.site_id == site_id)
    
    if tag is not None:
        # Фильтруем по тегу (теги хранятся как JSON)
        import json
        query = query.filter(Miner.tags.contains(f'"{tag}"'))
    
    if is_active is not None:
        query = query.filter(Miner.is_active == is_active)
    
    miners = query.all()
    result = []
    for miner in miners:
        response = MinerResponse.from_orm(miner)
        response.tags = miner.get_tags()
        if miner.container:
            response.container_name = miner.container.name
        if miner.pool:
            response.pool_name = miner.pool.name
        result.append(response)
    return result


# ============ MINER MODELS API (должны быть перед /api/miners/{miner_id}) ============

@app.get("/api/miners/tags")
def get_all_tags(
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка всех уникальных тегов"""
    import json
    all_tags = set()
    miners = db.query(Miner).all()
    for miner in miners:
        tags = miner.get_tags()
        all_tags.update(tags)
    return {"tags": sorted(list(all_tags))}


@app.get("/api/miners/manufacturers")
def get_manufacturers_list(current_user: User = Depends(get_current_user_with_db)):
    """Получение списка производителей (требует авторизации)"""
    return {"manufacturers": get_manufacturers()}


@app.get("/api/miners/models/{manufacturer}")
def get_models_list(
    manufacturer: str,
    current_user: User = Depends(get_current_user_with_db)
):
    """Получение списка моделей для указанного производителя (требует авторизации)"""
    if not is_valid_manufacturer(manufacturer):
        raise HTTPException(status_code=404, detail=f"Manufacturer '{manufacturer}' not found")
    return {"manufacturer": manufacturer, "models": get_models_by_manufacturer(manufacturer)}


@app.get("/api/miners/{miner_id}", response_model=MinerResponse)
def get_miner(
    miner_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение информации о майнере (с проверкой прав доступа)"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Проверяем доступ
    if not can_access_miner(current_user, miner_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this miner"
        )
    
    response = MinerResponse.from_orm(miner)
    if miner.container:
        response.container_name = miner.container.name
    return response


@app.put("/api/miners/{miner_id}", response_model=MinerResponse)
def update_miner(
    miner_id: int,
    miner_update: MinerUpdate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Обновление майнера (IP и порт могут изменять только администраторы)"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Проверяем доступ
    if not can_access_miner(current_user, miner_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this miner"
        )
    
    # Проверяем права на изменение IP и порта
    if (miner_update.ip_address is not None or miner_update.port is not None):
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can modify IP address and port"
            )
    
    if miner_update.container_id is not None:
        container = db.query(Container).filter(Container.id == miner_update.container_id).first()
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
    
    if miner_update.pool_id is not None:
        pool = db.query(Pool).filter(Pool.id == miner_update.pool_id).first()
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")
    
    update_data = miner_update.dict(exclude_unset=True)
    
    # Обрабатываем теги отдельно
    if 'tags' in update_data:
        miner.set_tags(update_data.pop('tags'))
    
    for key, value in update_data.items():
        setattr(miner, key, value)
    
    db.commit()
    db.refresh(miner)
    
    response = MinerResponse.from_orm(miner)
    response.tags = miner.get_tags()
    if miner.container:
        response.container_name = miner.container.name
    if miner.pool:
        response.pool_name = miner.pool.name
    return response


@app.delete("/api/miners/{miner_id}")
def delete_miner(
    miner_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Удаление майнера (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete miners"
        )
    
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    db.delete(miner)
    db.commit()
    return {"message": "Miner deleted"}


@app.post("/api/miners/{miner_id}/poll")
async def poll_miner(
    miner_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Ручной опрос майнера (с проверкой прав доступа)"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Проверяем доступ
    if not can_access_miner(current_user, miner_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this miner"
        )
    
    if monitoring_service:
        success = await monitoring_service.poll_miner(miner)
    else:
        service = MonitoringService()
        success = await service.poll_miner(miner)
    
    if success:
        return {"message": "Miner polled successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to poll miner")


# ============ STATS API ============

@app.get("/api/stats/miners/{miner_id}", response_model=List[MinerStatsResponse])
def get_miner_stats(
    miner_id: int,
    hours: int = Query(24, description="Number of hours to retrieve"),
    limit: int = Query(100, description="Maximum number of records"),
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение статистики майнера (с проверкой прав доступа)"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Проверяем доступ
    if not can_access_miner(current_user, miner_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this miner"
        )
    
    since = datetime.utcnow() - timedelta(hours=hours)
    stats = db.query(MinerStats).filter(
        and_(
            MinerStats.miner_id == miner_id,
            MinerStats.timestamp >= since
        )
    ).order_by(MinerStats.timestamp.desc()).limit(limit).all()
    
    return [MinerStatsResponse.from_orm(s) for s in stats]


@app.get("/api/stats/containers/{container_id}")
def get_container_stats(
    container_id: int,
    hours: int = Query(24, description="Number of hours to retrieve"),
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение статистики контейнера (с проверкой прав доступа)"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    # Проверяем доступ
    if not can_access_container(current_user, container_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this container"
        )
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Получаем последние статистики для каждого майнера в контейнере
    miners = db.query(Miner).filter(Miner.container_id == container_id).all()
    
    result = []
    total_hash_rate = 0.0
    total_temp = 0.0
    total_power = 0.0
    temp_count = 0
    power_count = 0
    
    for miner in miners:
        latest_stats = db.query(MinerStats).filter(
            and_(
                MinerStats.miner_id == miner.id,
                MinerStats.timestamp >= since
            )
        ).order_by(MinerStats.timestamp.desc()).first()
        
        if latest_stats:
            stats_data = MinerStatsWithMiner(
                id=latest_stats.id,
                miner_id=miner.id,
                miner_name=miner.name,
                timestamp=latest_stats.timestamp,
                hash_rate=latest_stats.hash_rate,
                accepted_shares=latest_stats.accepted_shares,
                rejected_shares=latest_stats.rejected_shares,
                temperature=latest_stats.temperature,
                fan_speed=latest_stats.fan_speed,
                power_consumption=latest_stats.power_consumption
            )
            result.append(stats_data)
            
            if latest_stats.hash_rate:
                total_hash_rate += latest_stats.hash_rate
            if latest_stats.temperature:
                total_temp += latest_stats.temperature
                temp_count += 1
            if latest_stats.power_consumption:
                total_power += latest_stats.power_consumption
                power_count += 1
    
    container_stats = ContainerStats(
        container_id=container.id,
        container_name=container.name,
        total_miners=len(miners),
        active_miners=len([m for m in miners if m.is_active]),
        total_hash_rate=total_hash_rate if total_hash_rate > 0 else None,
        avg_temperature=total_temp / temp_count if temp_count > 0 else None,
        avg_power_consumption=total_power / power_count if power_count > 0 else None
    )
    
    return {
        "container_stats": container_stats,
        "miner_stats": result
    }


@app.get("/api/stats/overview")
def get_overview_stats(db: Session = Depends(get_db)):
    """Получение общей статистики по всем контейнерам"""
    containers = db.query(Container).all()
    
    result = []
    for container in containers:
        miners = db.query(Miner).filter(Miner.container_id == container.id).all()
        active_miners = [m for m in miners if m.is_active]
        
        # Получаем последние статистики
        since = datetime.utcnow() - timedelta(hours=1)
        total_hash_rate = 0.0
        total_temp = 0.0
        total_power = 0.0
        temp_count = 0
        power_count = 0
        
        for miner in active_miners:
            latest_stats = db.query(MinerStats).filter(
                and_(
                    MinerStats.miner_id == miner.id,
                    MinerStats.timestamp >= since
                )
            ).order_by(MinerStats.timestamp.desc()).first()
            
            if latest_stats:
                if latest_stats.hash_rate:
                    total_hash_rate += latest_stats.hash_rate
                if latest_stats.temperature:
                    total_temp += latest_stats.temperature
                    temp_count += 1
                if latest_stats.power_consumption:
                    total_power += latest_stats.power_consumption
                    power_count += 1
        
        container_stats = ContainerStats(
            container_id=container.id,
            container_name=container.name,
            total_miners=len(miners),
            active_miners=len(active_miners),
            total_hash_rate=total_hash_rate if total_hash_rate > 0 else None,
            avg_temperature=total_temp / temp_count if temp_count > 0 else None,
            avg_power_consumption=total_power / power_count if power_count > 0 else None
        )
        result.append(container_stats)
    
    return result


# ============ POOLS API ============

@app.post("/api/pools", response_model=PoolResponse)
def create_pool(
    pool: PoolCreate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Создание нового пула (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create pools"
        )
    
    # Проверяем, нет ли пула с таким именем
    existing = db.query(Pool).filter(Pool.name == pool.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Pool with this name already exists")
    
    db_pool = Pool(name=pool.name, description=pool.description)
    db.add(db_pool)
    db.commit()
    db.refresh(db_pool)
    
    response = PoolResponse.from_orm(db_pool)
    response.miner_count = 0
    return response


@app.get("/api/pools", response_model=List[PoolResponse])
def get_pools(
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка всех пулов"""
    pools = db.query(Pool).all()
    result = []
    for pool in pools:
        response = PoolResponse.from_orm(pool)
        response.miner_count = db.query(func.count(Miner.id)).filter(Miner.pool_id == pool.id).scalar()
        result.append(response)
    return result


@app.get("/api/pools/{pool_id}", response_model=PoolResponse)
def get_pool(
    pool_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение информации о пуле"""
    pool = db.query(Pool).filter(Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    response = PoolResponse.from_orm(pool)
    response.miner_count = db.query(func.count(Miner.id)).filter(Miner.pool_id == pool_id).scalar()
    return response


@app.delete("/api/pools/{pool_id}")
def delete_pool(
    pool_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Удаление пула (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete pools"
        )
    
    pool = db.query(Pool).filter(Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    # Удаляем связь с майнерами (устанавливаем pool_id в None)
    db.query(Miner).filter(Miner.pool_id == pool_id).update({"pool_id": None})
    
    db.delete(pool)
    db.commit()
    return {"message": "Pool deleted"}


@app.get("/api/stats/pools/{pool_id}", response_model=PoolStats)
def get_pool_stats(
    pool_id: int,
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Статистика по пулу"""
    pool = db.query(Pool).filter(Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    miners = db.query(Miner).filter(Miner.pool_id == pool_id).all()
    active_miners = [m for m in miners if m.is_active]
    
    # Вычисляем статистику
    total_hash_rate = 0.0
    total_temp = 0.0
    temp_count = 0
    total_power = 0.0
    power_count = 0
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    for miner in active_miners:
        latest_stats = db.query(MinerStats).filter(
            MinerStats.miner_id == miner.id,
            MinerStats.timestamp >= cutoff_time
        ).order_by(MinerStats.timestamp.desc()).first()
        
        if latest_stats:
            if latest_stats.hash_rate:
                total_hash_rate += latest_stats.hash_rate
            if latest_stats.temperature:
                total_temp += latest_stats.temperature
                temp_count += 1
            if latest_stats.power_consumption:
                total_power += latest_stats.power_consumption
                power_count += 1
    
    return PoolStats(
        pool_id=pool.id,
        pool_name=pool.name,
        total_miners=len(miners),
        active_miners=len(active_miners),
        total_hash_rate=total_hash_rate if total_hash_rate > 0 else None,
        avg_temperature=total_temp / temp_count if temp_count > 0 else None,
        avg_power_consumption=total_power / power_count if power_count > 0 else None
    )


# ============ NETWORK SCANNING API ============

@app.post("/api/network/scan")
def scan_network_endpoint(
    scan_request: NetworkScanRequest,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Сканирование сети для поиска майнеров (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can scan network"
        )
    
    try:
        discovered = scan_network(
            scan_request.network,
            scan_request.port,
            scan_request.timeout,
            max_workers=50
        )
        return {"discovered_miners": discovered}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scanning network: {e}")
        raise HTTPException(status_code=500, detail=f"Error scanning network: {str(e)}")


@app.post("/api/network/discovered/add")
def add_discovered_miners(
    miners: List[DiscoveredMiner],
    pool_id: Optional[int] = Query(None),
    container_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Добавление найденных майнеров в базу данных (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can add discovered miners"
        )
    
    if pool_id is not None:
        pool = db.query(Pool).filter(Pool.id == pool_id).first()
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")
    
    if container_id is not None:
        container = db.query(Container).filter(Container.id == container_id).first()
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
    
    added = []
    skipped = []
    
    for miner_data in miners:
        if not miner_data.is_accessible:
            skipped.append({"ip": miner_data.ip_address, "reason": miner_data.error or "Not accessible"})
            continue
        
        # Проверяем, нет ли уже такого майнера
        existing = db.query(Miner).filter(
            Miner.ip_address == miner_data.ip_address,
            Miner.port == miner_data.port
        ).first()
        
        if existing:
            skipped.append({"ip": miner_data.ip_address, "reason": "Already exists"})
            continue
        
        # Создаем майнера
        miner = Miner(
            name=f"{miner_data.manufacturer or 'Unknown'}-{miner_data.ip_address}",
            ip_address=miner_data.ip_address,
            port=miner_data.port,
            manufacturer=miner_data.manufacturer,
            model=miner_data.model,
            pool_id=pool_id,
            container_id=container_id,
            is_active=True,
            is_auto_discovered=True
        )
        db.add(miner)
        added.append(miner_data.ip_address)
    
    db.commit()
    
    return {
        "added": len(added),
        "skipped": len(skipped),
        "added_ips": added,
        "skipped_details": skipped
    }


# ============ WEB INTERFACE ============

# ============ AUTH API ============

@app.post("/api/auth/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Регистрация нового пользователя (только для ролей CLIENT и ACCOUNTANT)"""
    # Обычные пользователи не могут регистрироваться как администраторы
    if user_data.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot register as administrator. Only existing administrators can create admin accounts."
        )
    
    # Проверяем, существует ли пользователь
    if get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    if get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Если роль не указана, устанавливаем CLIENT по умолчанию
    if user_data.role is None:
        user_data.role = UserRole.CLIENT
    
    # Создаем пользователя
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        role=db_user.role.value,
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )


@app.post("/api/auth/admin/create", response_model=UserResponse)
def create_admin_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Создание администраторской учетной записи (только для существующих администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create admin accounts"
        )
    
    # Проверяем, существует ли пользователь
    if get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    if get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Устанавливаем роль администратора (даже если в запросе указана другая)
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        role=db_user.role.value,
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )


@app.post("/api/auth/login", response_model=Token)
def login(user_credentials: UserLogin, db: Session = Depends(get_db), response: JSONResponse = None):
    """Вход пользователя"""
    user = authenticate_user(db, user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Обновляем время последнего входа
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Создаем токен
    access_token_expires = timedelta(minutes=30 * 24 * 60)  # 30 дней
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    # Создаем ответ с токеном
    token_response = JSONResponse(
        content={"access_token": access_token, "token_type": "bearer"}
    )
    
    # Устанавливаем cookie с токеном (30 дней)
    token_response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=30 * 24 * 60 * 60,  # 30 дней в секундах
        httponly=True,  # Защита от XSS
        samesite="lax",  # Защита от CSRF
        secure=False  # Для разработки, в продакшене должно быть True при HTTPS
    )
    
    return token_response


@app.post("/api/auth/logout")
def logout():
    """Выход пользователя"""
    logout_response = JSONResponse(content={"message": "Logged out successfully"})
    logout_response.delete_cookie("access_token")
    return logout_response


@app.get("/api/auth/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user_with_db)):
    """Получение информации о текущем пользователе"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_active=current_user.is_active,
        created_at=current_user.created_at
    )


# ============ USER MANAGEMENT API (только для администраторов) ============

@app.get("/api/users", response_model=List[UserResponse])
def get_users(
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Получение списка пользователей (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at
        )
        for user in users
    ]


@app.post("/api/users/{user_id}/containers/{container_id}")
def grant_container_access(
    user_id: int,
    container_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Предоставление доступа пользователю к контейнеру (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    # Проверяем, нет ли уже такого доступа
    existing = db.query(UserContainerAccess).filter(
        UserContainerAccess.user_id == user_id,
        UserContainerAccess.container_id == container_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Access already granted")
    
    access = UserContainerAccess(user_id=user_id, container_id=container_id)
    db.add(access)
    db.commit()
    
    return {"message": "Access granted"}


@app.delete("/api/users/{user_id}/containers/{container_id}")
def revoke_container_access(
    user_id: int,
    container_id: int,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """Отзыв доступа пользователя к контейнеру (только для администраторов)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    access = db.query(UserContainerAccess).filter(
        UserContainerAccess.user_id == user_id,
        UserContainerAccess.container_id == container_id
    ).first()
    
    if not access:
        raise HTTPException(status_code=404, detail="Access not found")
    
    db.delete(access)
    db.commit()
    
    return {"message": "Access revoked"}


# ============ AGENT API ============

def verify_agent_api_key(api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)) -> Agent:
    """Проверка API ключа агента"""
    agent = db.query(Agent).filter(Agent.api_key == api_key, Agent.is_active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key"
        )
    # Обновляем время последнего обращения
    agent.last_seen = datetime.utcnow()
    db.commit()
    return agent


@app.post("/api/agent/register", response_model=AgentRegisterResponse)
def register_agent(
    agent_data: AgentRegisterRequest,
    current_user: User = Depends(get_current_user_with_db),
    db: Session = Depends(get_db)
):
    """
    Регистрация нового агента (только для администраторов).
    Агент должен быть зарегистрирован администратором перед использованием.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can register agents"
        )
    
    # Проверяем, нет ли уже агента с таким именем
    existing = db.query(Agent).filter(Agent.name == agent_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent with this name already exists"
        )
    
    # Проверяем площадку, если указана
    if agent_data.site_id:
        site = db.query(Site).filter(Site.id == agent_data.site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
    
    # Генерируем API ключ
    import secrets
    api_key = secrets.token_urlsafe(32)
    
    # Создаем агента
    agent = Agent(
        name=agent_data.name,
        api_key=api_key,
        site_id=agent_data.site_id,
        description=agent_data.description,
        is_active=True
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    return AgentRegisterResponse(
        id=agent.id,
        name=agent.name,
        api_key=agent.api_key,
        site_id=agent.site_id,
        message=f"Agent '{agent.name}' registered successfully. Save this API key - it won't be shown again!"
    )


@app.post("/api/agent/sync", response_model=AgentSyncResponse)
def sync_agent_data(
    sync_data: AgentSyncRequest,
    agent: Agent = Depends(verify_agent_api_key),
    db: Session = Depends(get_db)
):
    """
    Синхронизация данных от агента.
    Агент отправляет список обнаруженных майнеров и их статистику.
    """
    miners_added = 0
    miners_updated = 0
    stats_added = 0
    errors = []
    
    # Обрабатываем обнаруженных майнеров
    for miner_data in sync_data.discovered_miners:
        try:
            # Ищем существующего майнера по IP и порту
            existing_miner = db.query(Miner).filter(
                Miner.ip_address == miner_data.ip_address,
                Miner.port == miner_data.port
            ).first()
            
            if existing_miner:
                # Обновляем существующего майнера
                if miner_data.manufacturer:
                    existing_miner.manufacturer = miner_data.manufacturer
                if miner_data.model:
                    existing_miner.model = miner_data.model
                if miner_data.name:
                    existing_miner.name = miner_data.name
                if miner_data.container_id:
                    existing_miner.container_id = miner_data.container_id
                if miner_data.pool_id:
                    existing_miner.pool_id = miner_data.pool_id
                if miner_data.tags:
                    existing_miner.set_tags(miner_data.tags)
                existing_miner.last_seen = datetime.utcnow()
                existing_miner.is_active = True
                miners_updated += 1
            else:
                # Создаем нового майнера
                miner_name = miner_data.name or f"{miner_data.manufacturer or 'Unknown'}-{miner_data.ip_address}"
                new_miner = Miner(
                    name=miner_name,
                    ip_address=miner_data.ip_address,
                    port=miner_data.port,
                    manufacturer=miner_data.manufacturer,
                    model=miner_data.model,
                    container_id=miner_data.container_id or (agent.site_id and None),  # Можно привязать к контейнеру площадки
                    pool_id=miner_data.pool_id,
                    is_active=True,
                    is_auto_discovered=True,
                    last_seen=datetime.utcnow()
                )
                if miner_data.tags:
                    new_miner.set_tags(miner_data.tags)
                db.add(new_miner)
                miners_added += 1
            
            db.commit()
        except Exception as e:
            errors.append(f"Error processing miner {miner_data.ip_address}: {str(e)}")
            db.rollback()
    
    # Обрабатываем статистику майнеров
    for stats_data in sync_data.miner_stats:
        try:
            # Находим майнера по IP и порту
            miner = db.query(Miner).filter(
                Miner.ip_address == stats_data.ip_address,
                Miner.port == stats_data.port
            ).first()
            
            if not miner:
                errors.append(f"Miner {stats_data.ip_address}:{stats_data.port} not found, skipping stats")
                continue
            
            # Создаем запись статистики
            miner_stat = MinerStats(
                miner_id=miner.id,
                timestamp=stats_data.timestamp,
                hash_rate=stats_data.hash_rate,
                accepted_shares=stats_data.accepted_shares,
                rejected_shares=stats_data.rejected_shares,
                pool_switches=stats_data.pool_switches,
                temperature=stats_data.temperature,
                fan_speed=stats_data.fan_speed,
                power_consumption=stats_data.power_consumption
            )
            
            if stats_data.summary_data:
                miner_stat.set_summary_data(stats_data.summary_data)
            if stats_data.stats_data:
                miner_stat.set_stats_data(stats_data.stats_data)
            
            db.add(miner_stat)
            stats_added += 1
            
            # Обновляем last_seen майнера
            miner.last_seen = stats_data.timestamp
            
            db.commit()
        except Exception as e:
            errors.append(f"Error processing stats for {stats_data.ip_address}:{stats_data.port}: {str(e)}")
            db.rollback()
    
    return AgentSyncResponse(
        miners_added=miners_added,
        miners_updated=miners_updated,
        stats_added=stats_added,
        errors=errors
    )


@app.get("/api/agent/info")
def get_agent_info(agent: Agent = Depends(verify_agent_api_key)):
    """Получение информации об агенте"""
    return {
        "id": agent.id,
        "name": agent.name,
        "site_id": agent.site_id,
        "description": agent.description,
        "last_seen": agent.last_seen,
        "is_active": agent.is_active
    }


# ============ WEB INTERFACE ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    """Главная страница - требует авторизации"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if not token:
        # Если токена нет, перенаправляем на страницу входа
        return RedirectResponse(url="/login", status_code=302)
    
    # Проверяем валидность токена
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            user = get_user_by_username(db, username=username)
            if user and user.is_active:
                # Пользователь авторизован, показываем главную страницу
                return templates.TemplateResponse("index.html", {"request": request})
    except (JWTError, Exception) as e:
        logger.debug(f"Token validation failed: {e}")
        # Токен невалиден, перенаправляем на логин
        pass
    
    # Если дошли сюда, токен невалиден или пользователь не найден
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")  # Удаляем невалидный cookie
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Страница входа - если уже авторизован, перенаправляем на главную"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if token:
        # Проверяем валидность токена
        try:
            from app.auth import SECRET_KEY, ALGORITHM
            from jose import jwt, JWTError
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            
            if username:
                user = get_user_by_username(db, username=username)
                if user and user.is_active:
                    # Пользователь уже авторизован, перенаправляем на главную
                    return RedirectResponse(url="/", status_code=302)
        except (JWTError, Exception):
            # Токен невалиден, показываем страницу входа
            pass
    
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Страница регистрации"""
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/containers", response_class=HTMLResponse)
async def containers_list(request: Request, db: Session = Depends(get_db)):
    """Страница списка контейнеров - требует авторизации"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    
    # Проверяем валидность токена
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            user = get_user_by_username(db, username=username)
            if user and user.is_active:
                # Перенаправляем на главную страницу, где есть список контейнеров
                return RedirectResponse(url="/", status_code=302)
    except (JWTError, Exception):
        pass
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@app.get("/containers/{container_id}", response_class=HTMLResponse)
async def container_detail(request: Request, container_id: int, db: Session = Depends(get_db)):
    """Страница контейнера - требует авторизации"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    
    # Проверяем валидность токена
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            user = get_user_by_username(db, username=username)
            if user and user.is_active:
                return templates.TemplateResponse("container.html", {"request": request, "container_id": container_id})
    except (JWTError, Exception):
        pass
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@app.get("/sites", response_class=HTMLResponse)
async def sites_list(request: Request, db: Session = Depends(get_db)):
    """Страница списка площадок - требует авторизации"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    
    # Проверяем валидность токена
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            user = get_user_by_username(db, username=username)
            if user and user.is_active:
                # Перенаправляем на главную страницу, где есть список площадок
                return RedirectResponse(url="/", status_code=302)
    except (JWTError, Exception):
        pass
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@app.get("/sites/{site_id}", response_class=HTMLResponse)
async def site_detail(request: Request, site_id: int, db: Session = Depends(get_db)):
    """Страница площадки - требует авторизации"""
    # Проверяем наличие токена в cookie
    token = request.cookies.get("access_token")
    
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    
    # Проверяем валидность токена
    try:
        from app.auth import SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        
        if username:
            user = get_user_by_username(db, username=username)
            if user and user.is_active:
                # Проверяем существование площадки
                site = db.query(Site).filter(Site.id == site_id).first()
                if not site:
                    raise HTTPException(status_code=404, detail="Site not found")
                return templates.TemplateResponse("site.html", {"request": request, "site_id": site_id})
    except (JWTError, Exception):
        pass
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
