import socket
import json
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WhatsminerClient:
    """TCP клиент для связи с Whatsminer M50 по JSON-RPC протоколу"""
    
    def __init__(self, host: str, port: int = 4028, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def _send_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Отправка команды через TCP и получение ответа"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            
            try:
                sock.connect((self.host, self.port))
                
                # Отправка команды
                message = json.dumps(command) + "\n"
                sock.sendall(message.encode('utf-8'))
                
                # Получение ответа
                response = b""
                # Используем таймаут для чтения
                read_timeout = self.timeout * 2  # Даем больше времени на чтение
                sock.settimeout(read_timeout)
                
                # Читаем данные частями
                while True:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        response += chunk
                        # Пытаемся распарсить JSON чтобы понять, что ответ завершен
                        try:
                            data = json.loads(response.decode('utf-8'))
                            return data
                        except json.JSONDecodeError:
                            # Если JSON неполный, продолжаем читать
                            continue
                    except socket.timeout:
                        # Если таймаут, проверяем есть ли что-то в буфере
                        if response:
                            try:
                                return json.loads(response.decode('utf-8'))
                            except json.JSONDecodeError:
                                break
                        break
                
                if response:
                    try:
                        return json.loads(response.decode('utf-8'))
                    except json.JSONDecodeError as e:
                        logger.error(f"Incomplete JSON response from {self.host}:{self.port}: {e}")
                        return None
                return None
                
            finally:
                sock.close()
                
        except socket.timeout:
            logger.error(f"Timeout connecting to {self.host}:{self.port}")
            return None
        except socket.error as e:
            logger.error(f"Socket error connecting to {self.host}:{self.port}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error from {self.host}:{self.port}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error connecting to {self.host}:{self.port}: {e}")
            return None
    
    async def get_summary(self) -> Optional[Dict[str, Any]]:
        """Получение общей статистики майнера"""
        loop = asyncio.get_event_loop()
        command = {"command": "summary"}
        return await loop.run_in_executor(None, self._send_command, command)
    
    async def get_stats(self) -> Optional[Dict[str, Any]]:
        """Получение детальной статистики майнера"""
        loop = asyncio.get_event_loop()
        command = {"command": "stats"}
        return await loop.run_in_executor(None, self._send_command, command)
    
    async def get_pools(self) -> Optional[Dict[str, Any]]:
        """Получение информации о пулах"""
        loop = asyncio.get_event_loop()
        command = {"command": "pools"}
        return await loop.run_in_executor(None, self._send_command, command)
    
    async def get_devs(self) -> Optional[Dict[str, Any]]:
        """Получение информации об устройствах (чипах)"""
        loop = asyncio.get_event_loop()
        command = {"command": "devs"}
        return await loop.run_in_executor(None, self._send_command, command)
    
    async def get_all_data(self) -> Optional[Dict[str, Any]]:
        """Получение всех доступных данных"""
        try:
            summary = await self.get_summary()
            stats = await self.get_stats()
            pools = await self.get_pools()
            devs = await self.get_devs()
            
            return {
                "summary": summary,
                "stats": stats,
                "pools": pools,
                "devs": devs,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting all data from {self.host}:{self.port}: {e}")
            return None


def parse_summary_data(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Парсинг данных summary для извлечения ключевых показателей"""
    if not summary or "SUMMARY" not in summary:
        return {}
    
    summary_data = summary["SUMMARY"][0] if isinstance(summary.get("SUMMARY"), list) else {}
    
    # Извлечение hash rate (может быть в разных форматах)
    hash_rate = 0.0
    if "GHS 5s" in summary_data:
        hash_rate = float(summary_data.get("GHS 5s", 0))
    elif "GHS av" in summary_data:
        hash_rate = float(summary_data.get("GHS av", 0))
    
    return {
        "hash_rate": hash_rate,
        "accepted_shares": int(summary_data.get("Accepted", 0)),
        "rejected_shares": int(summary_data.get("Rejected", 0)),
        "pool_switches": int(summary_data.get("Pool Switches", 0)),
        "raw_data": summary_data
    }


def parse_stats_data(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Парсинг данных stats для извлечения температуры, скорости вентиляторов и т.д."""
    if not stats or "STATS" not in stats:
        return {}
    
    stats_list = stats.get("STATS", [])
    if not stats_list:
        return {}
    
    # Берем последние статистические данные
    latest_stats = stats_list[-1]
    
    # Извлечение температуры
    temperature = None
    if "temperature" in latest_stats:
        temps = latest_stats.get("temperature", [])
        if temps and len(temps) > 0:
            temperature = float(max(temps)) if isinstance(temps, list) else float(temps)
    
    # Извлечение скорости вентиляторов
    fan_speed = None
    if "fan" in latest_stats:
        fans = latest_stats.get("fan", [])
        if fans and len(fans) > 0:
            fan_speed = int(max(fans)) if isinstance(fans, list) else int(fans)
    
    # Потребление энергии (если доступно)
    power_consumption = None
    if "power" in latest_stats:
        power_consumption = float(latest_stats.get("power", 0))
    
    return {
        "temperature": temperature,
        "fan_speed": fan_speed,
        "power_consumption": power_consumption,
        "raw_data": latest_stats
    }
