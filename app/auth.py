"""
Модуль авторизации и аутентификации
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import User, UserRole
from app.config import settings

# Настройки JWT
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 дней

# Настройки для хеширования паролей
# Используем bcrypt напрямую для лучшей совместимости
try:
    import bcrypt
    USE_BCRYPT_DIRECTLY = True
except ImportError:
    USE_BCRYPT_DIRECTLY = False

# Всегда создаем pwd_context для fallback
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 схема
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[UserRole] = UserRole.CLIENT


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    if USE_BCRYPT_DIRECTLY:
        import bcrypt
        try:
            # Bcrypt работает с байтами
            password_bytes = plain_password.encode('utf-8')[:72]
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception:
            # Fallback на passlib если что-то пошло не так
            return pwd_context.verify(plain_password, hashed_password)
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Хеширует пароль. Bcrypt имеет ограничение 72 байта, обрезаем если нужно.
    """
    if not isinstance(password, str):
        password = str(password)
    
    # Кодируем в байты для проверки длины
    password_bytes = password.encode('utf-8')
    
    # Bcrypt имеет ограничение 72 байта
    if len(password_bytes) > 72:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Password length ({len(password_bytes)} bytes) exceeds bcrypt limit (72 bytes), truncating...")
        password_bytes = password_bytes[:72]
    
    # Используем bcrypt напрямую для лучшей совместимости
    if USE_BCRYPT_DIRECTLY:
        try:
            import bcrypt
            # Генерируем соль и хешируем
            salt = bcrypt.gensalt()
            # Bcrypt принимает байты
            hashed = bcrypt.hashpw(password_bytes, salt)
            return hashed.decode('utf-8')
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error hashing password with bcrypt: {e}")
            # Fallback на passlib
            password_str = password_bytes.decode('utf-8', errors='ignore')
            return pwd_context.hash(password_str)
    else:
        # Используем passlib если bcrypt недоступен
        password_str = password_bytes.decode('utf-8', errors='ignore')
        return pwd_context.hash(password_str)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Получение пользователя по имени"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Получение пользователя по email"""
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Получение пользователя по ID"""
    return db.query(User).filter(User.id == user_id).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Аутентификация пользователя"""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = None  # Будет передано через Depends в main.py
) -> User:
    """Получение текущего пользователя из токена"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    if db is None:
        raise credentials_exception
    
    user = get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


def require_role(allowed_roles: list[UserRole]):
    """Декоратор для проверки роли пользователя"""
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker


# Функции для проверки доступа к объектам
def can_access_container(user: User, container_id: int, db: Session) -> bool:
    """Проверка доступа пользователя к контейнеру"""
    # Администратор имеет доступ ко всему
    if user.role == UserRole.ADMIN:
        return True
    
    # Проверяем, есть ли у пользователя доступ к контейнеру
    from app.database import UserContainerAccess
    access = db.query(UserContainerAccess).filter(
        UserContainerAccess.user_id == user.id,
        UserContainerAccess.container_id == container_id
    ).first()
    
    return access is not None


def can_access_miner(user: User, miner_id: int, db: Session) -> bool:
    """Проверка доступа пользователя к майнеру"""
    from app.database import Miner
    # Администратор имеет доступ ко всему
    if user.role == UserRole.ADMIN:
        return True
    
    # Получаем майнер
    miner = db.query(Miner).filter(Miner.id == miner_id).first()
    if not miner:
        return False
    
    # Если майнер не привязан к контейнеру, доступ только у админа
    if not miner.container_id:
        return user.role == UserRole.ADMIN
    
    # Проверяем доступ к контейнеру майнера
    return can_access_container(user, miner.container_id, db)
