#!/bin/sh
# Скрипт ожидания готовности базы данных

set -e

host="$1"
shift
cmd="$@"

# Используем переменные из окружения Docker Compose
POSTGRES_USER=${POSTGRES_USER:-miners_user}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-miners_password}
POSTGRES_DB=${POSTGRES_DB:-miners_monitoring}

>&2 echo "Waiting for PostgreSQL at $host to be ready..."

until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$host" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done

>&2 echo "PostgreSQL is up - executing command"
exec $cmd
