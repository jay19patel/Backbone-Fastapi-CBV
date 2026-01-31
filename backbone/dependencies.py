from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .utils import TokenManager
from .db import db
from .schemas import UserOut
from bson import ObjectId
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

from .repositories import MongoRepository
from .db import db

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserOut:
    """
    Dependency to fetch the current authenticated user as a Pydantic model.
    """
    payload = TokenManager.decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    sid = payload.get("sid")
    
    # Audit & Revoke: Validate session is still active
    session_repo = MongoRepository(db, "sessions")
    session = await session_repo.get_one({"id": sid, "is_active": True})
    if not session:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch User
    user_repo = MongoRepository(db, "users")
    user_data = await user_repo.get_one({"id": user_id, "is_active": True})
    
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found or inactive"
        )
    
    return UserOut(**user_data)

async def get_optional_user(token: str = Depends(oauth2_scheme)) -> Optional[UserOut]:
    """
    Optional user dependency that doesn't raise if token is missing.
    """
    try:
        if not token:
            return None
        return await get_current_user(token)
    except:
        return None
