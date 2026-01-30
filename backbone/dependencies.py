from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .utils import JWTUtils
from .db import db
from .schemas import UserOut
from bson import ObjectId
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserOut:
    """
    Dependency to fetch the current authenticated user as a Pydantic model.
    """
    payload = JWTUtils.decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    # Fetch user data
    user_data = await db["users"].find_one(
        {"_id": ObjectId(user_id), "is_active": True}
    )
    
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found or inactive"
        )
    
    # Convert MongoDB dict to Pydantic UserOut for type safety and validation
    # user_data["id"] = str(user_data["_id"]) # Done by UserOut/PyObjectId configuration if needed, 
    # but UserOut expects id field as str(alias='_id')
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
