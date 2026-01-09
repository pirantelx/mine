# Miners Monitoring

Система мониторинга майнеров по TCP протоколу с возможностью сбора показаний с сотен устройств, создания графиков и логического разделения по морским контейнерам. Поддерживает майнеры Whatsminer, AntMiner, Avalon и Elhapex.

## Возможности

- ✅ Мониторинг майнеров по TCP (порт 4028 по умолчанию)
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

### Вариант 1: Docker (Рекомендуется)

Быстрый старт:
```bash
# 1. Запустите через Docker Compose
docker-compose up -d

# 2. Откройте в браузере
# http://localhost:8000

# По умолчанию создается администратор:
# username: admin
# password: admin123
# ⚠️ Смените пароль после первого входа!
```

### Вариант 2: Локальная установка

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
SECRET_KEY=your-secret-key-here-change-in-production
```

4. Инициализируйте базу данных:
```bash
python init_db.py
```

База данных будет автоматически создана со всеми необходимыми таблицами и миграциями.

## Запуск

### Docker
```bash
docker-compose up -d
```

### Локально
```bash
python run.py
```

или через uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
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
- Укажите название, выберите производителя и модель, IP адрес, порт (по умолчанию 4028) и выберите контейнер

Через API:
```bash
curl -X POST "http://localhost:8000/api/miners" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Miner-001",
    "ip_address": "192.168.1.100",
    "port": 4028,
    "manufacturer": "Whatsminer",
    "model": "M50",
    "container_id": 1,
    "is_active": true
  }'
```

**Доступные производители и модели:**
- **Whatsminer**: M10, M20, M21, M30, M31, M50, M53, M56, M60, M63
- **AntMiner**: S9, S11, S15, S17, S19, S21, T9, T15, T17, T19, T21, L3+, L7, E9 Pro и другие
- **Avalon**: Miner 721, 741, 761, 821, 841, 851, 921, 1026, 1047, 1066, 1126 Pro, 1166 Pro, 1246, 1266
- **Elhapex**: E10, E11, E12, E20, E21, E30, E50

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
- `GET /api/miners/manufacturers` - Список производителей
- `GET /api/miners/models/{manufacturer}` - Список моделей для производителя

### Статистика

- `GET /api/stats/miners/{id}` - Статистика майнера (параметры: `hours`, `limit`)
- `GET /api/stats/containers/{id}` - Статистика контейнера (параметры: `hours`)
- `GET /api/stats/overview` - Общая статистика по всем контейнерам

## Структура проекта

```
.
├── app/                    # Основной код приложения
│   ├── __init__.py
│   ├── main.py            # FastAPI приложение и API endpoints
│   ├── config.py          # Конфигурация приложения
│   ├── database.py         # Модели базы данных (SQLAlchemy)
│   ├── auth.py             # Авторизация и аутентификация
│   ├── models.py           # Pydantic модели для API
│   ├── miner_models.py     # Модели майнеров (производители и модели)
│   └── services/           # Сервисы
│       ├── __init__.py
│       ├── monitoring.py   # Сервис мониторинга майнеров
│       └── miner_client.py # TCP клиент для связи с майнерами
├── scripts/                # Скрипты
│   ├── __init__.py
│   └── init_db.py          # Инициализация базы данных
├── templates/              # HTML шаблоны
├── static/                 # Статические файлы (CSS, JS)
├── data/                   # Данные (SQLite база данных)
├── run.py                  # Точка входа для запуска
├── requirements.txt        # Python зависимости
├── Dockerfile              # Docker образ
├── docker-compose.yml      # Docker Compose конфигурация
└── README.md               # Документация
```

## Структура базы данных

- **containers** - Контейнеры
  - id, name, description, location, created_at

- **miners** - Майнеры
  - id, name, ip_address, port, manufacturer, model, container_id, is_active, created_at, last_seen

- **miner_stats** - Статистика майнеров
  - id, miner_id, timestamp
  - hash_rate, accepted_shares, rejected_shares, pool_switches
  - temperature, fan_speed, power_consumption
  - summary_data (JSON), stats_data (JSON)

## Протокол мониторинга

Система использует JSON-RPC протокол через TCP (порт 4028 по умолчанию для Whatsminer):

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

✅ **Система включает полноценную систему авторизации** с тремя уровнями доступа:
- **Администратор** - полный доступ ко всем функциям
- **Бухгалтер** - доступ к статистике и отчетам
- **Клиент** - доступ только к назначенным контейнерам

### Создание администраторской учетной записи

#### Способ 1: Автоматическое создание (при первом запуске)

При первом запуске системы автоматически создается администратор по умолчанию:
- **Username**: `admin`
- **Password**: `admin123`
- **Email**: `admin@example.com`

⚠️ **ВАЖНО**: Смените пароль администратора после первого входа!

#### Способ 2: Создание через API (только для существующих администраторов)

Существующие администраторы могут создавать новых администраторов через API:

```bash
# 1. Войдите как администратор и получите токен
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 2. Используйте токен для создания нового администратора
curl -X POST "http://localhost:8000/api/auth/admin/create" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "username": "new_admin",
    "email": "new_admin@example.com",
    "password": "secure_password_123"
  }'
```

**Примечание**: Обычная регистрация (`/api/auth/register`) не позволяет создавать администраторов - только роли `CLIENT` и `ACCOUNTANT`.

Для использования в production рекомендуется:
- Изменить пароль администратора по умолчанию
- Использовать HTTPS для безопасного соединения
- Настроить переменную окружения `SECRET_KEY` для JWT токенов

Подробнее см. [AUTH_GUIDE.md](AUTH_GUIDE.md)

## Разработка

Для разработки используйте виртуальное окружение:

```bash
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Лицензия

Этот проект создан для мониторинга майнеров различных производителей.
