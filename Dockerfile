FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Копирование скрипта ожидания БД
COPY wait-for-db.sh /app/wait-for-db.sh
RUN chmod +x /app/wait-for-db.sh

# Создание директории для базы данных (если используется SQLite)
RUN mkdir -p /app/data

# Открытие порта
EXPOSE 8000

# Команда запуска с ожиданием БД и инициализацией
CMD ["sh", "-c", "./wait-for-db.sh db python scripts/init_db.py && python run.py"]
