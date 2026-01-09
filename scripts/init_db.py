"""
Скрипт инициализации базы данных для Docker
Создает все необходимые таблицы и выполняет миграции
"""
import sys
import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

# Добавляем корневую директорию проекта в путь
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.database import Base, Container, Miner, MinerStats, User, UserRole, UserContainerAccess, Pool, Site, Agent
from app.config import settings
from app.auth import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_table_exists(engine, table_name):
    """Проверяет существование таблицы"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def init_database(max_retries=5, retry_delay=5):
    """Инициализирует базу данных с повторными попытками"""
    import time
    
    db_url_display = settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url
    logger.info(f"Подключение к базе данных: {db_url_display}")
    
    for attempt in range(1, max_retries + 1):
        try:
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            
            # Проверяем подключение
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✓ Подключение к базе данных успешно")
            break
        except OperationalError as e:
            if attempt < max_retries:
                logger.warning(f"Попытка {attempt}/{max_retries} не удалась. Повтор через {retry_delay} секунд...")
                logger.debug(f"Ошибка: {e}")
                time.sleep(retry_delay)
            else:
                logger.error(f"Ошибка подключения к базе данных после {max_retries} попыток: {e}")
                logger.error("Убедитесь, что база данных запущена и доступна")
                return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при подключении: {e}")
            return False
    
    # Создаем все таблицы
    try:
        logger.info("Создание таблиц...")
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Таблицы созданы или уже существуют")
        
        # Создаем сессию для работы с данными
        from app.database import get_session_maker
        session_maker = get_session_maker(engine)
        db = session_maker()
        
        # Проверяем наличие таблиц
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        logger.info(f"✓ Найдено таблиц: {len(tables)}")
        for table in tables:
            logger.info(f"  - {table}")
        
        # Выполняем миграцию для добавления полей manufacturer и model, если их нет
        if "miners" in tables:
            logger.info("Проверка миграций для таблицы miners...")
            columns = [col['name'] for col in inspector.get_columns('miners')]
            
            if "manufacturer" not in columns:
                logger.info("Добавление колонки manufacturer...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE miners ADD COLUMN manufacturer VARCHAR"))
                    logger.info("✓ Колонка manufacturer добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку manufacturer: {e}")
            else:
                logger.info("✓ Колонка manufacturer уже существует")
            
            if "model" not in columns:
                logger.info("Добавление колонки model...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE miners ADD COLUMN model VARCHAR"))
                    logger.info("✓ Колонка model добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку model: {e}")
            else:
                logger.info("✓ Колонка model уже существует")
            
            # Проверяем наличие колонки pool_id
            if "pool_id" not in columns:
                logger.info("Добавление колонки pool_id...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE miners ADD COLUMN pool_id INTEGER"))
                    logger.info("✓ Колонка pool_id добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку pool_id: {e}")
            else:
                logger.info("✓ Колонка pool_id уже существует")
            
            # Проверяем наличие колонки is_auto_discovered
            if "is_auto_discovered" not in columns:
                logger.info("Добавление колонки is_auto_discovered...")
                try:
                    with engine.begin() as conn:
                        if "sqlite" in settings.database_url.lower():
                            conn.execute(text("ALTER TABLE miners ADD COLUMN is_auto_discovered BOOLEAN DEFAULT 0"))
                        else:
                            conn.execute(text("ALTER TABLE miners ADD COLUMN is_auto_discovered BOOLEAN DEFAULT FALSE"))
                    logger.info("✓ Колонка is_auto_discovered добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку is_auto_discovered: {e}")
            else:
                logger.info("✓ Колонка is_auto_discovered уже существует")
            
            # Проверяем наличие колонки tags
            if "tags" not in columns:
                logger.info("Добавление колонки tags...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE miners ADD COLUMN tags TEXT"))
                    logger.info("✓ Колонка tags добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку tags: {e}")
            else:
                logger.info("✓ Колонка tags уже существует")
        
        # Проверяем миграции для таблицы containers
        if "containers" in tables:
            logger.info("Проверка миграций для таблицы containers...")
            columns = [col['name'] for col in inspector.get_columns('containers')]
            
            # Проверяем наличие колонки site_id
            if "site_id" not in columns:
                logger.info("Добавление колонки site_id...")
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE containers ADD COLUMN site_id INTEGER"))
                    logger.info("✓ Колонка site_id добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку site_id: {e}")
            else:
                logger.info("✓ Колонка site_id уже существует")
        
        # Создаем администратора по умолчанию, если его нет
        try:
            admin_user = db.query(User).filter(User.username == "admin").first()
            if not admin_user:
                logger.info("Создание администратора по умолчанию...")
                # Создаем хеш пароля
                password = "admin123"
                hashed_pwd = get_password_hash(password)
                
                admin_user = User(
                    username="admin",
                    email="admin@example.com",
                    hashed_password=hashed_pwd,
                    role=UserRole.ADMIN,
                    is_active=True
                )
                db.add(admin_user)
                db.commit()
                logger.info("✓ Администратор создан: username=admin, password=admin123")
                logger.warning("⚠️ ВАЖНО: Смените пароль администратора после первого входа!")
            else:
                logger.info("✓ Администратор уже существует")
        except Exception as e:
            logger.warning(f"Не удалось создать администратора: {e}")
        finally:
            db.close()
        
        logger.info("\n✓ Инициализация базы данных завершена успешно!")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
