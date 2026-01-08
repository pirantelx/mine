# Whatsminer M50 Monitoring System

Система мониторинга майнеров Whatsminer M50 по TCP протоколу с возможностью сбора показаний с сотен устройств, создания графиков и логического разделения по морским контейнерам.

## Возможности

- ✅ Мониторинг майнеров Whatsminer M50 по TCP (порт 4028)
- ✅ Сбор статистики с множества устройств (поддержка сотен майнеров)
- ✅ Логическое разделение майнеров по контейнерам
- ✅ Веб-интерфейс с графиками и статистикой
- ✅ REST API для управления устройствами и контейнерами
- ✅ Автоматический опрос майнеров с настраиваемым интервалом
- ✅ История показаний с возможностью построения графиков

## Технологии

- **Backend**: FastAPI (Python)
- **Database**: SQLite (можно легко заменить на PostgreSQL)
- **Frontend**: HTML, CSS, JavaScript, Chart.js
- **Protocol**: TCP/JSON-RPC для связи с майнерами

## Установка

1. Клонируйте репозиторий или скопируйте файлы проекта

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` (опционально) для настройки:
```
DATABASE_URL=sqlite:///./miners_monitoring.db
DEFAULT_MINER_PORT=4028
CONNECTION_TIMEOUT=5.0
POLLING_INTERVAL=60
MAX_WORKERS=50
API_HOST=0.0.0.0
API_PORT=8000
```

## Запуск

```bash
python main.py
```

или через uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

После запуска откройте в браузере: http://localhost:8000

## Использование

### 1. Создание контейнеров

Через веб-интерфейс:
- Нажмите "Добавить контейнер"
- Укажите название, описание и местоположение

Через API:
```bash
curl -X POST "http://localhost:8000/api/containers" \
  -H "Content-Type: application/json" \
  -d '{"name": "Контейнер 1", "description": "Морской контейнер", "location": "Порт А"}'
```

### 2. Добавление майнеров

Через веб-интерфейс:
- Нажмите "Добавить майнер"
- Укажите название, IP адрес, порт (по умолчанию 4028) и выберите контейнер

Через API:
```bash
curl -X POST "http://localhost:8000/api/miners" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Miner-001",
    "ip_address": "192.168.1.100",
    "port": 4028,
    "container_id": 1,
    "is_active": true
  }'
```

### 3. Мониторинг

Система автоматически опрашивает все активные майнеры с интервалом, указанным в `POLLING_INTERVAL` (по умолчанию 60 секунд).

Для ручного опроса майнера используйте кнопку "Опрос" в веб-интерфейсе или API:
```bash
curl -X POST "http://localhost:8000/api/miners/1/poll"
```

### 4. Просмотр графиков

В веб-интерфейсе:
- Выберите майнер из списка
- Выберите метрику (хешрейт, температура, и т.д.)
- Укажите период (количество часов)
- График автоматически обновится

## API Endpoints

### Контейнеры

- `GET /api/containers` - Список всех контейнеров
- `GET /api/containers/{id}` - Информация о контейнере
- `POST /api/containers` - Создание контейнера
- `DELETE /api/containers/{id}` - Удаление контейнера

### Майнеры

- `GET /api/miners` - Список майнеров (параметры: `container_id`, `is_active`)
- `GET /api/miners/{id}` - Информация о майнере
- `POST /api/miners` - Создание майнера
- `PUT /api/miners/{id}` - Обновление майнера
- `DELETE /api/miners/{id}` - Удаление майнера
- `POST /api/miners/{id}/poll` - Ручной опрос майнера

### Статистика

- `GET /api/stats/miners/{id}` - Статистика майнера (параметры: `hours`, `limit`)
- `GET /api/stats/containers/{id}` - Статистика контейнера (параметры: `hours`)
- `GET /api/stats/overview` - Общая статистика по всем контейнерам

## Структура базы данных

- **containers** - Контейнеры
  - id, name, description, location, created_at

- **miners** - Майнеры
  - id, name, ip_address, port, container_id, is_active, created_at, last_seen

- **miner_stats** - Статистика майнеров
  - id, miner_id, timestamp
  - hash_rate, accepted_shares, rejected_shares, pool_switches
  - temperature, fan_speed, power_consumption
  - summary_data (JSON), stats_data (JSON)

## Протокол Whatsminer M50

Система использует JSON-RPC протокол через TCP (порт 4028 по умолчанию):

- `{"command": "summary"}` - Общая статистика
- `{"command": "stats"}` - Детальная статистика
- `{"command": "pools"}` - Информация о пулах
- `{"command": "devs"}` - Информация об устройствах (чипах)

## Конфигурация

Настройки находятся в файле `config.py` или могут быть переопределены через переменные окружения:

- `DATABASE_URL` - URL базы данных (по умолчанию SQLite)
- `DEFAULT_MINER_PORT` - Порт майнера (по умолчанию 4028)
- `CONNECTION_TIMEOUT` - Таймаут соединения в секундах
- `POLLING_INTERVAL` - Интервал опроса в секундах
- `MAX_WORKERS` - Максимальное количество одновременных соединений
- `API_HOST` - Хост для API (по умолчанию 0.0.0.0)
- `API_PORT` - Порт для API (по умолчанию 8000)

## Производительность

Система оптимизирована для работы с большим количеством майнеров:
- Асинхронный опрос майнеров
- Параллельное выполнение запросов (до `MAX_WORKERS` одновременно)
- Индексирование базы данных для быстрого поиска
- Настраиваемый интервал опроса

## Безопасность

⚠️ **Важно**: Система не включает аутентификацию по умолчанию. Для использования в production рекомендуется добавить:
- Аутентификацию пользователей
- HTTPS для безопасного соединения
- Ограничение доступа к API

## Разработка

Для разработки используйте виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Лицензия

Этот проект создан для мониторинга майнеров Whatsminer M50.
