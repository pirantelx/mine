"""
Скрипт миграции базы данных для добавления полей manufacturer и model в таблицу miners
"""
from sqlalchemy import create_engine, text
from config import settings

def migrate_database():
    """Добавляет колонки manufacturer и model в таблицу miners, если их еще нет"""
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {})
    
    with engine.connect() as conn:
        # Проверяем существование колонок (для SQLite)
        if "sqlite" in settings.database_url:
            cursor = conn.execute(text("PRAGMA table_info(miners)"))
            columns = [row[1] for row in cursor.fetchall()]
            
            if "manufacturer" not in columns:
                print("Добавление колонки manufacturer...")
                conn.execute(text("ALTER TABLE miners ADD COLUMN manufacturer VARCHAR"))
                conn.commit()
                print("[OK] Колонка manufacturer добавлена")
            else:
                print("[OK] Колонка manufacturer уже существует")
            
            if "model" not in columns:
                print("Добавление колонки model...")
                conn.execute(text("ALTER TABLE miners ADD COLUMN model VARCHAR"))
                conn.commit()
                print("[OK] Колонка model добавлена")
            else:
                print("[OK] Колонка model уже существует")
        else:
            # Для PostgreSQL и других СУБД
            try:
                conn.execute(text("ALTER TABLE miners ADD COLUMN manufacturer VARCHAR"))
                conn.commit()
                print("[OK] Колонка manufacturer добавлена")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("[OK] Колонка manufacturer уже существует")
                else:
                    raise
            
            try:
                conn.execute(text("ALTER TABLE miners ADD COLUMN model VARCHAR"))
                conn.commit()
                print("[OK] Колонка model добавлена")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("[OK] Колонка model уже существует")
                else:
                    raise
        
        print("\n[OK] Миграция базы данных завершена успешно!")

if __name__ == "__main__":
    migrate_database()
