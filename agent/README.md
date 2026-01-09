# Агент мониторинга майнеров

Клиентское приложение для установки на площадках. Сканирует локальную сеть, находит майнеры и отправляет данные на центральный сервер.

## Установка

1. Скопируйте папку `agent` на площадку (сервер с доступом к локальной сети майнеров)

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Настройте конфигурацию:
```bash
cp config.json.example config.json
nano config.json
```

Или используйте переменные окружения:
```bash
export AGENT_SERVER_URL="http://your-server-ip:8000"
export AGENT_API_KEY="your-api-key-here"
export AGENT_NETWORK="192.168.1.0/24"
export AGENT_SCAN_INTERVAL=300
export AGENT_POLL_INTERVAL=60
```

## Регистрация агента

Перед запуском агента его нужно зарегистрировать на центральном сервере:

1. Войдите как администратор на центральный сервер
2. Используйте API для регистрации агента:
```bash
curl -X POST "http://your-server:8000/api/agent/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "name": "site-1-agent",
    "description": "Агент на площадке 1",
    "site_id": 1
  }'
```

3. Сохраните полученный `api_key` - он понадобится для настройки агента

## Запуск

### Ручной запуск:
```bash
python agent.py
```

### Как служба (systemd):
Создайте файл `/etc/systemd/system/miners-agent.service`:
```ini
[Unit]
Description=Miners Monitoring Agent
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/agent
Environment="AGENT_SERVER_URL=http://your-server:8000"
Environment="AGENT_API_KEY=your-api-key"
Environment="AGENT_NETWORK=192.168.1.0/24"
ExecStart=/usr/bin/python3 /path/to/agent/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Затем:
```bash
sudo systemctl enable miners-agent
sudo systemctl start miners-agent
sudo systemctl status miners-agent
```

### В Docker:
```bash
docker run -d \
  --name miners-agent \
  --restart unless-stopped \
  -e AGENT_SERVER_URL=http://your-server:8000 \
  -e AGENT_API_KEY=your-api-key \
  -e AGENT_NETWORK=192.168.1.0/24 \
  -v /path/to/agent:/app \
  python:3.11 \
  python /app/agent.py
```

## Параметры конфигурации

- `server_url` - URL центрального сервера (например, "http://192.168.1.100:8000")
- `api_key` - API ключ агента (получается при регистрации)
- `network_cidr` - CIDR сети для сканирования (например, "192.168.1.0/24")
- `scan_interval` - Интервал полного сканирования сети в секундах (по умолчанию 300 = 5 минут)
- `poll_interval` - Интервал опроса майнеров в секундах (по умолчанию 60 = 1 минута)

## Как это работает

1. **Сканирование сети**: Агент периодически сканирует указанную сеть для поиска новых майнеров
2. **Обнаружение майнеров**: При обнаружении майнера определяется его производитель и модель
3. **Сбор статистики**: Агент периодически опрашивает все обнаруженные майнеры для получения статистики
4. **Отправка данных**: Все данные отправляются на центральный сервер через API

## Логирование

Логи выводятся в консоль. Для сохранения в файл используйте перенаправление:
```bash
python agent.py >> /var/log/miners-agent.log 2>&1
```

Или настройте systemd для автоматического логирования.
