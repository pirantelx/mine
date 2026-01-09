"""
Сервис для автоматического сканирования сети и обнаружения майнеров
"""
import socket
import ipaddress
import json
import asyncio
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from app.services.miner_client import WhatsminerClient

logger = logging.getLogger(__name__)


def check_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    """Проверка доступности порта"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"Error checking port {ip}:{port}: {e}")
        return False


def identify_miner(ip: str, port: int, timeout: float = 2.0) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Попытка идентификации майнера по IP и порту
    Возвращает: (manufacturer, model, is_accessible)
    """
    try:
        client = WhatsminerClient(ip, port, timeout)
        # Пытаемся получить summary для идентификации
        summary = client.get_summary()
        
        if summary:
            # Пытаемся определить производителя и модель из данных
            manufacturer = None
            model = None
            
            # Проверяем различные признаки
            if "Type" in summary:
                type_str = str(summary.get("Type", "")).lower()
                if "whatsminer" in type_str or "m" in type_str:
                    manufacturer = "Whatsminer"
                    # Пытаемся извлечь модель
                    if "m50" in type_str or "M50" in str(summary.get("Type", "")):
                        model = "M50"
                    elif "m30" in type_str or "M30" in str(summary.get("Type", "")):
                        model = "M30"
                    elif "m20" in type_str or "M20" in str(summary.get("Type", "")):
                        model = "M20"
            
            # Если не удалось определить, но есть ответ - это майнер
            if not manufacturer:
                manufacturer = "Unknown"
            
            return (manufacturer, model, True)
    except Exception as e:
        logger.debug(f"Error identifying miner at {ip}:{port}: {e}")
        return (None, None, False)
    
    return (None, None, False)


def scan_network(network: str, port: int = 4028, timeout: float = 2.0, max_workers: int = 50) -> List[Dict]:
    """
    Сканирование сети для поиска майнеров
    
    Args:
        network: Сеть в формате CIDR (например, "192.168.1.0/24")
        port: Порт для проверки (по умолчанию 4028)
        timeout: Таймаут для каждого подключения
        max_workers: Максимальное количество одновременных проверок
    
    Returns:
        Список найденных майнеров
    """
    try:
        network_obj = ipaddress.ip_network(network, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid network format: {e}")
    
    logger.info(f"Scanning network {network} on port {port}")
    discovered_miners = []
    
    # Получаем список всех IP адресов в сети
    ip_list = [str(ip) for ip in network_obj.hosts()]
    logger.info(f"Scanning {len(ip_list)} IP addresses")
    
    # Используем ThreadPoolExecutor для параллельного сканирования
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Создаем задачи для проверки портов
        future_to_ip = {
            executor.submit(check_port, ip, port, timeout): ip
            for ip in ip_list
        }
        
        # Обрабатываем результаты
        open_ports = []
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                if future.result():
                    open_ports.append(ip)
                    logger.info(f"Found open port {port} on {ip}")
            except Exception as e:
                logger.debug(f"Error checking {ip}: {e}")
    
    logger.info(f"Found {len(open_ports)} devices with open port {port}")
    
    # Теперь пытаемся идентифицировать майнеры на найденных IP
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {
            executor.submit(identify_miner, ip, port, timeout): ip
            for ip in open_ports
        }
        
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                manufacturer, model, is_accessible = future.result()
                if is_accessible:
                    discovered_miners.append({
                        "ip_address": ip,
                        "port": port,
                        "manufacturer": manufacturer,
                        "model": model,
                        "is_accessible": True,
                        "error": None
                    })
                    logger.info(f"Identified miner at {ip}:{port} - {manufacturer} {model}")
                else:
                    discovered_miners.append({
                        "ip_address": ip,
                        "port": port,
                        "manufacturer": None,
                        "model": None,
                        "is_accessible": False,
                        "error": "Could not identify miner type"
                    })
            except Exception as e:
                logger.debug(f"Error identifying {ip}: {e}")
                discovered_miners.append({
                    "ip_address": ip,
                    "port": port,
                    "manufacturer": None,
                    "model": None,
                    "is_accessible": False,
                    "error": str(e)
                })
    
    logger.info(f"Discovered {len([m for m in discovered_miners if m['is_accessible']])} accessible miners")
    return discovered_miners
