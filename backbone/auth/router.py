from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from ..utils import PasswordManager, TokenManager
from ..schemas import UserOut, TokenResponse, LoginSchema, RegisterSchema
from ..core.models import User, Session
from ..core.dependencies import get_current_user, oauth2_scheme
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from ..core.repository import BeanieRepository

class AuthRouter:
    def __init__(self, config: Any, db_instance: Any = None, prefix: str = "/auth", tags: list = ["Auth"]):
        self.router = APIRouter(prefix=prefix, tags=tags)
        self.config = config
        
        self.user_repository = BeanieRepository(db_instance)
        self.user_repository.initialize(User)
        
        self.session_repository = BeanieRepository(db_instance)
        self.session_repository.initialize(Session)
        
        self._register_routes()
    
    async def _resolve_repos(self, request: Request):
        config = request.app.state.backbone_config
        if self.user_repository.db is None:
            self.user_repository.db = config.database
        if self.session_repository.db is None:
            self.session_repository.db = config.database

    def _register_routes(self):
        @self.router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
        async def register(request: Request, user_data: RegisterSchema):
            await self._resolve_repos(request)
            existing_user = await self.user_repository.get_one({"email": user_data.email})
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
        
            hashed_pw = PasswordManager.hash_password(user_data.password)
            user_dict = user_data.model_dump()
            user_dict["hashed_password"] = hashed_pw
            del user_dict["password"]
            user_dict["is_active"] = True
            user_dict["is_staff"] = False
        
            new_user = await self.user_repository.create(user_dict)
            return UserOut(**new_user.model_dump(by_alias=True))

        @self.router.post("/login", response_model=TokenResponse)
        async def login(request: Request, response: Response, login_data: LoginSchema):
            await self._resolve_repos(request)
            user = await self.user_repository.get_one({"email": login_data.email})
            
            if not user or not PasswordManager.verify_password(login_data.password, user.hashed_password):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            # Create Session
            user_id = str(user.id)
            session_data = {
                "user_id": user_id,
                "refresh_token": "", # Placeholder
                "expires_at": datetime.utcnow() + timedelta(days=7),
                "user_agent": request.headers.get("user-agent"),
                "ip_address": request.client.host if request.client else None,
                "is_active": True
            }
            session = await self.session_repository.create(session_data)
            sid = str(session.id)
            
            refresh_token = TokenManager.create_refresh_token({"sub": user_id}, sid=sid)
            access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
            
            await self.session_repository.update({"id": session.id}, {"refresh_token": refresh_token})
            
            # Use environment-aware cookie settings from BackboneConfig
            backbone_config = request.app.state.backbone_config
            cookie_opts = backbone_config.cookie_settings
            
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                max_age=7 * 24 * 60 * 60,
                **cookie_opts
            )
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            }

        @self.router.post("/refresh")
        async def refresh(request: Request, response: Response):
            await self._resolve_repos(request)
            refresh_token = request.cookies.get("refresh_token")
            if not refresh_token:
                raise HTTPException(status_code=401, detail="No refresh token")
            
            payload = TokenManager.verify_token(refresh_token)
            if not payload:
                raise HTTPException(status_code=401, detail="Invalid refresh token")
            
            sid = payload.get("sid")
            session = await self.session_repository.get_one({"id": sid, "is_active": True})
            if not session or session.refresh_token != refresh_token:
                raise HTTPException(status_code=401, detail="Session expired or invalid")
            
            user_id = payload.get("sub")
            new_access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
            
            return {"access_token": new_access_token, "token_type": "bearer"}

        @self.router.get("/me", response_model=UserOut)
        async def get_me(user: User = Depends(get_current_user)):
            return UserOut(**user.model_dump(by_alias=True))
