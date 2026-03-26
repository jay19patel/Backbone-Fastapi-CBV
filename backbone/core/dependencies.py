from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from ..common.utils import TokenManager
from ..schemas import UserOut
from .models import User, Session
from typing import Optional
from beanie import PydanticObjectId

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Dependency to fetch the current authenticated User Beanie document.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    try:
        session = await Session.find_one({"_id": PydanticObjectId(sid), "is_active": True})
        if not session:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch User Document
    user = await User.get(PydanticObjectId(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found or inactive"
        )
    
    return user

async def get_optional_user(token: str = Depends(oauth2_scheme)) -> Optional[UserOut]:
    """
    Optional user dependency that doesn't raise if token is missing.
    """
    try:
        if not token:
            return None
        user = await get_current_user(token)
        return UserOut(**user.model_dump(by_alias=True))
    except Exception:
        return None
