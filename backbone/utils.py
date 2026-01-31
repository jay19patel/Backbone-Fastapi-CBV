import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional, Dict, List
from .config import settings

class PasswordManager:
    """
    Handles password hashing and verification using Argon2.
    """
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

    @classmethod
    def hash_password(cls, password: str) -> str:
        return cls.pwd_context.hash(password)

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return cls.pwd_context.verify(plain_password, hashed_password)

class TokenManager:
    """
    Handles JWT token creation and decoding using configured settings.
    """
    @staticmethod
    def create_access_token(data: dict, sid: str, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
        to_encode.update({"exp": expire, "type": "access", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_refresh_token(data: dict, sid: str) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh", "sid": sid})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        except (jwt.PyJWTError, KeyError):
            return None

# Backward compatibility (optional, but good if other files import these names directly)
# SecurityUtils = PasswordManager
# JWTUtils = TokenManager

