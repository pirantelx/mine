import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor

from app.database import Miner, MinerStats, Container, init_db, get_session_maker
from app.services.miner_client import WhatsminerClient, parse_summary_data, parse_stats_data
from app.config import settings

logger = logging.getLogger(__name__)


class MonitoringService:
    """Сервис мониторинга майнеров"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers)
        self.is_running = False
        self._task = None
        self.engine = None
        self.session_maker = None
    
    def _get_db_session(self):
        """Создает новую сессию БД"""
        if not self.engine:
            self.engine = init_db(settings.database_url)
            self.session_maker = get_session_maker(self.engine)
        return self.session_maker()
    
    async def poll_miner(self, miner: Miner) -> bool:
        """Опрос одного майнера"""
        db = None
        try:
            client = WhatsminerClient(
                host=miner.ip_address,
                port=miner.port,
                timeout=settings.connection_timeout
            )
            
            # Получаем данные
            all_data = await client.get_all_data()
            
            if not all_data:
                logger.warning(f"Failed to get data from miner {miner.name} ({miner.ip_address})")
                return False
            
            # Парсим данные
            summary = all_data.get("summary", {})
            stats = all_data.get("stats", {})
            
            summary_parsed = parse_summary_data(summary)
            stats_parsed = parse_stats_data(stats)
            
            # Создаем новую сессию для записи в БД
            db = self._get_db_session()
            
            try:
                # Перечитываем майнера из БД
                db_miner = db.query(Miner).filter(Miner.id == miner.id).first()
                if not db_miner:
                    logger.error(f"Miner {miner.id} not found in database")
                    return False
                
                # Создаем запись в базе данных
                miner_stats = MinerStats(
                    miner_id=db_miner.id,
                    timestamp=datetime.utcnow(),
                    hash_rate=summary_parsed.get("hash_rate"),
                    accepted_shares=summary_parsed.get("accepted_shares"),
                    rejected_shares=summary_parsed.get("rejected_shares"),
                    pool_switches=summary_parsed.get("pool_switches"),
                    temperature=stats_parsed.get("temperature"),
                    fan_speed=stats_parsed.get("fan_speed"),
                    power_consumption=stats_parsed.get("power_consumption")
                )
                
                miner_stats.set_summary_data(summary_parsed.get("raw_data", {}))
                miner_stats.set_stats_data(stats_parsed.get("raw_data", {}))
                
                # Обновляем last_seen
                db_miner.last_seen = datetime.utcnow()
                
                db.add(miner_stats)
                db.commit()
                
                logger.info(f"Successfully polled miner {miner.name} ({miner.ip_address})")
                return True
            except Exception as e:
                db.rollback()
                raise e
            finally:
                if db:
                    db.close()
            
        except Exception as e:
            logger.error(f"Error polling miner {miner.name} ({miner.ip_address}): {e}")
            return False
    
    async def poll_all_miners(self):
        """Опрос всех активных майнеров"""
        db = self._get_db_session()
        try:
            miners = db.query(Miner).filter(Miner.is_active == True).all()
            
            if not miners:
                logger.info("No active miners to poll")
                return
            
            logger.info(f"Polling {len(miners)} miners...")
            
            # Создаем задачи для всех майнеров
            tasks = [self.poll_miner(miner) for miner in miners]
            
            # Выполняем параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if r is True)
            failed = len(results) - successful
            
            logger.info(f"Polling completed: {successful} successful, {failed} failed")
        finally:
            db.close()
    
    async def _polling_loop(self):
        """Основной цикл опроса"""
        while self.is_running:
            try:
                await self.poll_all_miners()
                await asyncio.sleep(settings.polling_interval)
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(settings.polling_interval)
    
    def start(self):
        """Запуск службы мониторинга"""
        if self.is_running:
            logger.warning("Monitoring service is already running")
            return
        
        self.is_running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._polling_loop())
        logger.info("Monitoring service started")
    
    def stop(self):
        """Остановка службы мониторинга"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self._task:
            self._task.cancel()
        logger.info("Monitoring service stopped")
