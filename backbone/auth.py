from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from .repositories import MongoRepository
from .db import db
from .utils import PasswordManager, TokenManager
from .schemas import UserSchema, UserOut, TokenResponse, SessionSchema
from .dependencies import get_current_user, oauth2_scheme
from typing import Dict, Any
from datetime import datetime, timedelta

class AuthRouter:
    def __init__(self, db_instance: Any = None, prefix: str = "/auth", tags: list = ["Auth"]):
        self.router = APIRouter(prefix=prefix, tags=tags)
        # Use passed db_instance or fallback to global db (for backward compat or simplicity)
        database = db_instance if db_instance is not None else db
        self.user_repository = MongoRepository(database, "users")
        self.session_repository = MongoRepository(database, "sessions")
        # No automated registration here intentionally; Main registers it.

    async def sync_indexes(self):
        """
        Create indexes for User and Session collections.
        """
        # User Indexes (Email unique)
        # If UserSchema defines Meta.indexes, we could do:
        # self.user_repository.initialize(UserSchema) ... but let's be explicit if needed or rely on schema.
        # Check UserSchema for indexes:
        # Assuming UserSchema has Meta/indexes, let's just initialize it to trigger any internal logic if we added it to MongoRepository.
        # But MongoRepository.initialize just sets collection name.
        # We need to manually create indexes or use a helper.
        # For now, explicit creation as requested by user to be "perfect"
        
        # Users
        await self.user_repository.collection.create_index([("email", 1)], unique=True)
        
        # Sessions
        await self.session_repository.collection.create_index([("user_id", 1)])
        await self.session_repository.collection.create_index([("refresh_token", 1)], unique=True)

    def _register_routes(self):

        @self.router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
        async def register(user: UserSchema):
            existing_user = await self.user_repository.get_one({"email": user.email})
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
            
            user_dict = user.model_dump(by_alias=True)
            user_dict["hashed_password"] = PasswordManager.hash_password(user_dict["hashed_password"])
            
            created_user = await self.user_repository.create(user_dict)
            return created_user

        @self.router.post("/login")
        async def login(credentials: Dict[str, str], request: Request, response: Response):
            email = credentials.get("email")
            password = credentials.get("password")
            
            user_data = await self.user_repository.get_one({"email": email})
            if not user_data or not PasswordManager.verify_password(password, user_data["hashed_password"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            user_id = str(user_data["id"])
            
            # 1. Create a placeholder session to get an ID
            session_data = {
                "user_id": user_id,
                "refresh_token": "pending", # Will update after generation
                "expires_at": datetime.utcnow() + timedelta(days=7),
                "user_agent": request.headers.get("user-agent"),
                "ip_address": request.client.host if request.client else None,
                "is_active": True
            }
            session = await self.session_repository.create(session_data)
            sid = str(session["id"])
            
            # 2. Generate Tokens bound to this Session ID (sid)
            refresh_token = TokenManager.create_refresh_token({"sub": user_id}, sid=sid)
            access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
            
            # 3. Update session with the real refresh token
            await self.session_repository.update({"id": sid}, {"refresh_token": refresh_token})
            
            # 4. Set Refresh Token in Secure HttpOnly Cookie
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=True, # Should be True in production
                samesite="lax",
                max_age=7 * 24 * 60 * 60, # 7 days
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }

        @self.router.post("/refresh")
        async def refresh(request: Request, response: Response):
            refresh_token = request.cookies.get("refresh_token")
            if not refresh_token:
                raise HTTPException(status_code=401, detail="Refresh token missing")
            
            payload = TokenManager.decode_token(refresh_token)
            if not payload or payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid refresh token")
            
            sid = payload.get("sid")
            session = await self.session_repository.get_one({
                "id": sid,
                "refresh_token": refresh_token, 
                "is_active": True
            })
            
            if not session or session["expires_at"].replace(tzinfo=None) < datetime.utcnow():
                if session:
                    await self.session_repository.update({"id": sid}, {"is_active": False})
                raise HTTPException(status_code=401, detail="Session expired or revoked")
            
            # Create new access token (rotate if needed, but here we just issue new access)
            new_access_token = TokenManager.create_access_token({"sub": session["user_id"]}, sid=sid)
            return {
                "access_token": new_access_token,
                "token_type": "bearer"
            }

        @self.router.post("/logout")
        async def logout(response: Response, user: UserOut = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
            # Decode token to get sid
            payload = TokenManager.decode_token(token)
            if payload and payload.get("sid"):
                sid = payload.get("sid")
                await self.session_repository.update({"id": sid}, {"is_active": False})
            
            response.delete_cookie("refresh_token")
            return {"detail": "Logged out successfully"}

        
        @self.router.get("/me", response_model=UserOut)
        async def me(user: UserOut = Depends(get_current_user)):
            return user
