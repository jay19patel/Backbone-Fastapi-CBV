from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from ..utils import PasswordManager, TokenManager
from ..schemas import UserOut, TokenResponse, LoginSchema, RegisterSchema
from ..core.models import User, Session
from ..core.dependencies import get_current_user, oauth2_scheme
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from beanie import PydanticObjectId
from ..core.repository import UserRepository

class AuthRouter:
    def __init__(self, db_instance: Any = None, prefix: str = "/auth", tags: list = ["Auth"]):
        self.router = APIRouter(prefix=prefix, tags=tags)
        self.user_repository = UserRepository(db_instance)
        self.user_repository.initialize(User)
        
        # Register Routes associated with this router
        self._register_routes()
    
    def _register_routes(self):

        @self.router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
        async def register(user_data: RegisterSchema):
            existing_user = await self.user_repository.get_by_email(user_data.email)
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
            
            hashed_pw = PasswordManager.hash_password(user_data.password)
            
            # Helper to create dict for creation
            user_dict = user_data.model_dump()
            user_dict["hashed_password"] = hashed_pw
            del user_dict["password"]
            user_dict["is_active"] = True
            user_dict["is_staff"] = False
            
            new_user = await self.user_repository.create(user_dict)
            return UserOut(**new_user.model_dump(by_alias=True))

        from fastapi.security import OAuth2PasswordRequestForm

        @self.router.post("/login")
        async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None, response: Response = None):
            # OAuth2PasswordRequestForm has username and password
            email = form_data.username
            password = form_data.password
            
            user = await self.user_repository.get_by_email(email)
            if not user or not PasswordManager.verify_password(password, user.hashed_password):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            user_id = str(user.id)
            
            # 1. Create Session
            session = Session(
                user_id=user_id,
                refresh_token="pending",
                expires_at=datetime.utcnow() + timedelta(days=7),
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
                is_active=True
            )
            await session.insert()
            sid = str(session.id)
            
            # 2. Generate Tokens
            refresh_token = TokenManager.create_refresh_token({"sub": user_id}, sid=sid)
            access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
            
            # 3. Update Session with real refresh token
            session.refresh_token = refresh_token
            await session.save()
            
            # 4. Set Cookie
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=True, 
                samesite="lax",
                max_age=7 * 24 * 60 * 60,
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
            
            # Find Session
            try:
                session = await Session.find_one({
                    "_id": PydanticObjectId(sid),
                    "refresh_token": refresh_token,
                    "is_active": True
                })
            except:
                session = None

            if not session or session.expires_at < datetime.utcnow():
                if session:
                    session.is_active = False
                    await session.save()
                raise HTTPException(status_code=401, detail="Session expired or revoked")
            
            new_access_token = TokenManager.create_access_token({"sub": session.user_id}, sid=sid)
            return {
                "access_token": new_access_token,
                "token_type": "bearer"
            }

        @self.router.post("/logout")
        async def logout(response: Response, user: UserOut = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
            payload = TokenManager.decode_token(token)
            if payload and payload.get("sid"):
                sid = payload.get("sid")
                try:
                    session = await Session.get(PydanticObjectId(sid))
                    if session:
                        session.is_active = False
                        await session.save()
                except:
                    pass
            
            response.delete_cookie("refresh_token")
            return {"detail": "Logged out successfully"}

        @self.router.get("/me", response_model=UserOut)
        async def me(user: UserOut = Depends(get_current_user)):
            return user
