import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import Request

from backbone.core.models import User, Session
from backbone.utils import PasswordManager, TokenManager
from backbone.core.repository import BeanieRepository

class AuthService:
    def __init__(self, request: Request = None, db_instance: Any = None):
        """
        Initialize AuthService with request context to access app state and DB.
        """
        self.request = request
        self.db = db_instance
        
        # Resolve DB from request if not provided explicitly
        if not self.db and request:
            self.db = request.app.state.backbone_config.database

        self.user_repo = BeanieRepository(self.db)
        self.user_repo.initialize(User)
        
        self.session_repo = BeanieRepository(self.db)
        self.session_repo.initialize(Session)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Verify user credentials.
        """
        user = await self.user_repo.get_one({"email": email})
        if not user:
            return None
            
        # Handle both dict and object return types
        hashed_password = user.get("hashed_password") if isinstance(user, dict) else getattr(user, "hashed_password", None)
        
        if not PasswordManager.verify_password(password, hashed_password):
            return None
        return user

    async def create_session(self, user: User, user_agent: str = None, ip_address: str = None) -> Dict[str, str]:
        """
        Create a new session and Generate tokens.
        """
        # Handle both dict and object
        user_id = str(user.get("_id") or user.get("id")) if isinstance(user, dict) else str(user.id)
        
        import uuid
        
        # 1. Create Session Record
        session_data = {
            "user_id": user_id,
            "refresh_token": str(uuid.uuid4()), # Temp unique to avoid index collision
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "user_agent": user_agent,
            "ip_address": ip_address,
            "is_active": True
        }
        session = await self.session_repo.create(session_data)
        sid = str(session.id)
        
        # 2. Generate Tokens with SID
        refresh_token = TokenManager.create_refresh_token({"sub": user_id}, sid=sid)
        access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
        
        # 3. Update Session with Refresh Token
        await self.session_repo.update({"id": session.id}, {"refresh_token": refresh_token})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "sid": sid,
            "token_type": "bearer"
        }

    async def logout(self, sid: str) -> bool:
        """
        Invalidate a session.
        """
        if not sid:
            return False
        await self.session_repo.update({"id": sid}, {"is_active": False})
        return True
