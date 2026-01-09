#!/usr/bin/env python3
"""
Агент для мониторинга майнеров на площадке.
Сканирует локальную сеть, находит майнеры и отправляет данные на центральный сервер.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
import ipaddress
import socket

# Добавляем путь к модулям приложения для использования общих классов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.miner_client import WhatsminerClient
from app.services.network_scanner import scan_network as scan_network_sync

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonitoringAgent:
    """Агент для мониторинга майнеров на площадке"""
    
    def __init__(self, server_url: str, api_key: str, network_cidr: str, 
                 scan_interval: int = 300, poll_interval: int = 60):
        """
        Инициализация агента
        
        Args:
            server_url: URL центрального сервера (например, "http://192.168.1.100:8000")
            api_key: API ключ агента для аутентификации
            network_cidr: CIDR сети для сканирования (например, "192.168.1.0/24")
            scan_interval: Интервал полного сканирования сети в секундах (по умолчанию 5 минут)
            poll_interval: Интервал опроса майнеров в секундах (по умолчанию 1 минута)
        """
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.network_cidr = network_cidr
        self.scan_interval = scan_interval
        self.poll_interval = poll_interval
        self.discovered_miners: Dict[str, Dict] = {}  # IP -> miner data
        self.running = False
        
    async def scan_network(self) -> List[Dict]:
        """Сканирование сети для поиска майнеров"""
        logger.info(f"Начато сканирование сети: {self.network_cidr}")
        
        try:
            # Запускаем синхронное сканирование в executor
            loop = asyncio.get_event_loop()
            discovered = await loop.run_in_executor(
                None, 
                scan_network_sync, 
                self.network_cidr, 
                4028, 
                2.0
            )
        except Exception as e:
            logger.error(f"Ошибка при сканировании сети: {e}")
            return []
        
        # Обновляем список обнаруженных майнеров
        for miner in discovered:
            if miner.get("is_accessible"):
                ip = miner["ip_address"]
                self.discovered_miners[ip] = {
                    "ip_address": ip,
                    "port": miner.get("port", 4028),
                    "manufacturer": miner.get("manufacturer"),
                    "model": miner.get("model"),
                    "name": f"{miner.get('manufacturer', 'Unknown')}-{ip}",
                    "last_seen": datetime.utcnow()
                }
        
        logger.info(f"Сканирование завершено. Найдено {len(discovered)} устройств, из них {len(self.discovered_miners)} майнеров")
        return list(self.discovered_miners.values())
    
    async def poll_miner(self, ip_address: str, port: int = 4028) -> Optional[Dict]:
        """Опрос майнера для получения статистики"""
        try:
            # Запускаем синхронные операции в executor
            loop = asyncio.get_event_loop()
            client = WhatsminerClient(ip_address, port, timeout=5.0)
            
            # Получаем summary
            summary = await loop.run_in_executor(None, client.get_summary)
            if not summary:
                return None
            
            # Получаем stats
            stats = await loop.run_in_executor(None, client.get_stats)
            
            # Извлекаем данные (структура может отличаться в зависимости от модели майнера)
            summary_data = {}
            stats_data = {}
            
            if isinstance(summary, dict):
                if "SUMMARY" in summary and summary["SUMMARY"]:
                    summary_data = summary["SUMMARY"][0] if isinstance(summary["SUMMARY"], list) else summary["SUMMARY"]
                else:
                    summary_data = summary
            
            if isinstance(stats, dict):
                if "STATS" in stats and stats["STATS"]:
                    stats_data = stats["STATS"][0] if isinstance(stats["STATS"], list) else stats["STATS"]
                else:
                    stats_data = stats
            
            # Парсим статистику
            hash_rate = None
            if "GHS 5s" in summary_data:
                try:
                    hash_rate = float(summary_data["GHS 5s"]) / 1000.0  # Конвертируем в TH/s
                except (ValueError, TypeError):
                    pass
            
            accepted_shares = summary_data.get("Accepted")
            rejected_shares = summary_data.get("Rejected")
            pool_switches = summary_data.get("Pool Rejected%")
            
            # Температура и вентиляторы
            temperature = None
            fan_speed = None
            if isinstance(stats_data, dict):
                if "temp" in stats_data:
                    try:
                        temp_str = str(stats_data["temp"])
                        temps = [int(t) for t in temp_str.split() if t.isdigit()]
                        if temps:
                            temperature = max(temps)
                    except (ValueError, TypeError):
                        pass
                
                if "fan" in stats_data:
                    try:
                        fan_str = str(stats_data["fan"])
                        fans = [int(f) for f in fan_str.split() if f.isdigit()]
                        if fans:
                            fan_speed = max(fans)
                    except (ValueError, TypeError):
                        pass
            
            return {
                "ip_address": ip_address,
                "port": port,
                "timestamp": datetime.utcnow(),
                "hash_rate": hash_rate,
                "accepted_shares": accepted_shares,
                "rejected_shares": rejected_shares,
                "pool_switches": pool_switches,
                "temperature": temperature,
                "fan_speed": fan_speed,
                "power_consumption": None,  # Можно добавить, если доступно
                "summary_data": summary_data,
                "stats_data": stats_data
            }
        except Exception as e:
            logger.debug(f"Ошибка при опросе майнера {ip_address}:{port}: {e}")
            return None
    
    async def poll_all_miners(self) -> List[Dict]:
        """Опрос всех обнаруженных майнеров"""
        if not self.discovered_miners:
            return []
        
        logger.info(f"Начато опрос {len(self.discovered_miners)} майнеров")
        tasks = []
        for ip, miner_data in self.discovered_miners.items():
            tasks.append(self.poll_miner(ip, miner_data["port"]))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        stats = [r for r in results if r is not None and not isinstance(r, Exception)]
        
        logger.info(f"Опрос завершен. Получено статистики: {len(stats)}")
        return stats
    
    async def send_data_to_server(self, discovered_miners: List[Dict], miner_stats: List[Dict]) -> bool:
        """Отправка данных на центральный сервер"""
        try:
            url = f"{self.server_url}/api/agent/sync"
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": self.api_key
            }
            
            # Преобразуем discovered_miners, убирая last_seen
            discovered_miners_clean = []
            for miner in discovered_miners:
                miner_clean = {k: v for k, v in miner.items() if k != "last_seen"}
                discovered_miners_clean.append(miner_clean)
            
            # Преобразуем miner_stats, сериализуя datetime
            miner_stats_clean = []
            for stats in miner_stats:
                stats_clean = {}
                for k, v in stats.items():
                    if isinstance(v, datetime):
                        stats_clean[k] = v.isoformat()
                    else:
                        stats_clean[k] = v
                miner_stats_clean.append(stats_clean)
            
            payload = {
                "discovered_miners": discovered_miners_clean,
                "miner_stats": miner_stats_clean
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Данные отправлены на сервер: "
                                  f"майнеров добавлено={result.get('miners_added', 0)}, "
                                  f"обновлено={result.get('miners_updated', 0)}, "
                                  f"статистики добавлено={result.get('stats_added', 0)}")
                        if result.get("errors"):
                            for error in result["errors"]:
                                logger.warning(f"Ошибка сервера: {error}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка отправки данных на сервер: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Ошибка при отправке данных на сервер: {e}")
            return False
    
    async def run_scan_loop(self):
        """Цикл сканирования сети"""
        while self.running:
            try:
                discovered = await self.scan_network()
                # Отправляем список обнаруженных майнеров на сервер
                if discovered:
                    await self.send_data_to_server(discovered, [])
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле сканирования: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повтором
    
    async def run_poll_loop(self):
        """Цикл опроса майнеров"""
        while self.running:
            try:
                stats = await self.poll_all_miners()
                # Отправляем статистику на сервер
                if stats:
                    await self.send_data_to_server([], stats)
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Ошибка в цикле опроса: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повтором
    
    async def start(self):
        """Запуск агента"""
        logger.info(f"Запуск агента. Сервер: {self.server_url}, Сеть: {self.network_cidr}")
        self.running = True
        
        # Запускаем оба цикла параллельно
        await asyncio.gather(
            self.run_scan_loop(),
            self.run_poll_loop()
        )
    
    def stop(self):
        """Остановка агента"""
        logger.info("Остановка агента")
        self.running = False


async def main():
    """Главная функция"""
    # Загружаем конфигурацию из переменных окружения или config.json
    config_file = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        # Используем переменные окружения
        config = {
            "server_url": os.getenv("AGENT_SERVER_URL", "http://localhost:8000"),
            "api_key": os.getenv("AGENT_API_KEY", ""),
            "network_cidr": os.getenv("AGENT_NETWORK", "192.168.1.0/24"),
            "scan_interval": int(os.getenv("AGENT_SCAN_INTERVAL", "300")),
            "poll_interval": int(os.getenv("AGENT_POLL_INTERVAL", "60"))
        }
    
    if not config.get("api_key"):
        logger.error("API ключ не указан! Укажите AGENT_API_KEY в переменных окружения или в config.json")
        sys.exit(1)
    
    agent = MonitoringAgent(
        server_url=config["server_url"],
        api_key=config["api_key"],
        network_cidr=config["network_cidr"],
        scan_interval=config.get("scan_interval", 300),
        poll_interval=config.get("poll_interval", 60)
    )
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
