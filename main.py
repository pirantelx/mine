from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from database import init_db, get_session_maker, Miner, MinerStats, Container
from models import (
    ContainerCreate, ContainerResponse, MinerCreate, MinerUpdate,
    MinerResponse, MinerStatsResponse, MinerStatsWithMiner, ContainerStats
)
from monitoring_service import MonitoringService
from config import settings
from miner_models import get_manufacturers, get_models_by_manufacturer, is_valid_manufacturer, is_valid_model

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

app = FastAPI(title="Whatsminer M50 Monitoring System")

# Статические файлы и шаблоны
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Startup/Shutdown события
@app.on_event("startup")
async def startup_event():
    global monitoring_service
    try:
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


# ============ CONTAINERS API ============

@app.post("/api/containers", response_model=ContainerResponse)
def create_container(container: ContainerCreate, db: Session = Depends(get_db)):
    """Создание нового контейнера"""
    db_container = Container(
        name=container.name,
        description=container.description,
        location=container.location
    )
    db.add(db_container)
    db.commit()
    db.refresh(db_container)
    
    # Получаем количество майнеров
    miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == db_container.id).scalar()
    
    response = ContainerResponse.from_orm(db_container)
    response.miner_count = miner_count
    return response


@app.get("/api/containers", response_model=List[ContainerResponse])
def get_containers(db: Session = Depends(get_db)):
    """Получение списка всех контейнеров"""
    containers = db.query(Container).all()
    result = []
    for container in containers:
        miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == container.id).scalar()
        response = ContainerResponse.from_orm(container)
        response.miner_count = miner_count
        result.append(response)
    return result


@app.get("/api/containers/{container_id}", response_model=ContainerResponse)
def get_container(container_id: int, db: Session = Depends(get_db)):
    """Получение информации о контейнере"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    miner_count = db.query(func.count(Miner.id)).filter(Miner.container_id == container_id).scalar()
    response = ContainerResponse.from_orm(container)
    response.miner_count = miner_count
    return response


@app.delete("/api/containers/{container_id}")
def delete_container(container_id: int, db: Session = Depends(get_db)):
    """Удаление контейнера"""
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
def create_miner(miner: MinerCreate, db: Session = Depends(get_db)):
    """Создание нового майнера"""
    # Проверяем, существует ли контейнер
    if miner.container_id:
        container = db.query(Container).filter(Container.id == miner.container_id).first()
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
    
    db_miner = Miner(
        name=miner.name,
        ip_address=miner.ip_address,
        port=miner.port,
        manufacturer=miner.manufacturer,
        model=miner.model,
        container_id=miner.container_id,
        is_active=miner.is_active
    )
    db.add(db_miner)
    db.commit()
    db.refresh(db_miner)
    
    response = MinerResponse.from_orm(db_miner)
    if db_miner.container:
        response.container_name = db_miner.container.name
    return response


@app.get("/api/miners", response_model=List[MinerResponse])
def get_miners(
    container_id: Optional[int] = Query(None, description="Filter by container ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """Получение списка майнеров"""
    query = db.query(Miner)
    
    if container_id is not None:
        query = query.filter(Miner.container_id == container_id)
    
    if is_active is not None:
        query = query.filter(Miner.is_active == is_active)
    
    miners = query.all()
    result = []
    for miner in miners:
        response = MinerResponse.from_orm(miner)
        if miner.container:
            response.container_name = miner.container.name
        result.append(response)
    return result


# ============ MINER MODELS API (должны быть перед /api/miners/{miner_id}) ============

@app.get("/api/miners/manufacturers")
def get_manufacturers_list():
    """Получение списка производителей"""
    return {"manufacturers": get_manufacturers()}


@app.get("/api/miners/models/{manufacturer}")
def get_models_list(manufacturer: str):
    """Получение списка моделей для указанного производителя"""
    if not is_valid_manufacturer(manufacturer):
        raise HTTPException(status_code=404, detail=f"Manufacturer '{manufacturer}' not found")
    return {"manufacturer": manufacturer, "models": get_models_by_manufacturer(manufacturer)}


@app.get("/api/miners/{miner_id}", response_model=MinerResponse)
def get_miner(miner_id: int, db: Session = Depends(get_db)):
    """Получение информации о майнере"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    response = MinerResponse.from_orm(miner)
    if miner.container:
        response.container_name = miner.container.name
    return response


@app.put("/api/miners/{miner_id}", response_model=MinerResponse)
def update_miner(miner_id: int, miner_update: MinerUpdate, db: Session = Depends(get_db)):
    """Обновление майнера"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    if miner_update.container_id is not None:
        container = db.query(Container).filter(Container.id == miner_update.container_id).first()
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
    
    update_data = miner_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(miner, key, value)
    
    db.commit()
    db.refresh(miner)
    
    response = MinerResponse.from_orm(miner)
    if miner.container:
        response.container_name = miner.container.name
    return response


@app.delete("/api/miners/{miner_id}")
def delete_miner(miner_id: int, db: Session = Depends(get_db)):
    """Удаление майнера"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    db.delete(miner)
    db.commit()
    return {"message": "Miner deleted"}


@app.post("/api/miners/{miner_id}/poll")
async def poll_miner(miner_id: int, db: Session = Depends(get_db)):
    """Ручной опрос майнера"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
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
    db: Session = Depends(get_db)
):
    """Получение статистики майнера"""
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
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
    db: Session = Depends(get_db)
):
    """Получение статистики контейнера"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
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


# ============ WEB INTERFACE ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/containers/{container_id}", response_class=HTMLResponse)
async def container_detail(request: Request, container_id: int):
    """Страница контейнера"""
    return templates.TemplateResponse("container.html", {"request": request, "container_id": container_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
