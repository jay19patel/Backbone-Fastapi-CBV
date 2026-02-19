from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from ..utils import TokenManager
from ..schemas import UserOut
from .models import User, Session
from typing import Optional
from beanie import PydanticObjectId

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

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
    try:
        session = await Session.find_one({"_id": PydanticObjectId(sid), "is_active": True})
        if not session:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception:
        # If ID is invalid or other error
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch User
    from ..core.repository import BeanieRepository
    user_repo = BeanieRepository()
    user_repo.initialize(User)
    
    try:
        # Repository get_one expects a filter. Beanie uses _id for primary key.
        user = await user_repo.get_one({"_id": PydanticObjectId(user_id)})
    except Exception:
        user = None

    if isinstance(user, dict):
        if not user.get("is_active"):
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
        return UserOut(**user)
        
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found or inactive"
        )
    
    return UserOut(**user.model_dump(by_alias=True))

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
