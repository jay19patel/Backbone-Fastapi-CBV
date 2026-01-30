import jwt
import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional, Any

# Configurations
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

class SecurityUtils:
    """
    Handles password hashing and verification using Argon2.
    """
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

    @staticmethod
    def hash_password(password: str) -> str:
        return SecurityUtils.pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return SecurityUtils.pwd_context.verify(plain_password, hashed_password)

class JWTUtils:
    """
    Handles JWT token creation and decoding.
    """
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def decode_access_token(token: str) -> Optional[dict]:
        try:
            decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Check expiration
            if decoded_token.get("exp") and datetime.utcnow().timestamp() > decoded_token["exp"]:
                return None
            return decoded_token
        except (jwt.PyJWTError, KeyError):
            return None
