import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import Request
from beanie import PydanticObjectId
from bson import ObjectId
from bson.dbref import DBRef

from backbone.core.models import PasswordResetToken, Session, User
from backbone.common.utils import PasswordManager, TokenManager
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

        self.password_reset_repo = BeanieRepository(self.db)
        self.password_reset_repo.initialize(PasswordResetToken)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        return await User.find_one(User.email == email)

    async def get_active_session(self, sid: str) -> Optional[Session]:
        if not sid or not ObjectId.is_valid(sid):
            return None
        return await Session.find_one({"_id": PydanticObjectId(sid), "is_active": True})

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Verify user credentials.
        """
        user = await self.get_user_by_email(email)
        if not user:
            return None

        if not PasswordManager.verify_password(password, user.hashed_password):
            return None
        return user

    async def create_session(self, user: User, user_agent: str = None, ip_address: str = None) -> Dict[str, str]:
        """
        Create a new session and Generate tokens.
        """
        user_id = str(user.id)
        user_ref = DBRef("users", ObjectId(user_id))

        # 1. Create Session Record
        session_data = {
            "user": user_ref,
            "refresh_token": str(ObjectId()),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
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
        session = await self.get_active_session(sid)
        if not session:
            return False
        await session.set({"is_active": False})
        return True

    @staticmethod
    def hash_password_reset_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    async def create_password_reset_request(self, email: str, expires_in_minutes: int = 60) -> Optional[Dict[str, Any]]:
        user = await self.get_user_by_email(email)
        if not user or not user.is_active:
            return None

        now = datetime.now(timezone.utc)
        await PasswordResetToken.find({
            "user_id": str(user.id),
            "is_active": True,
        }).update({"$set": {"is_active": False, "used_at": now}})

        raw_token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=str(user.id),
            email=user.email,
            token_hash=self.hash_password_reset_token(raw_token),
            expires_at=now + timedelta(minutes=expires_in_minutes),
            is_active=True,
        )
        await reset_token.insert()
        return {
            "token": raw_token,
            "expires_at": reset_token.expires_at,
            "user_id": str(user.id),
            "email": user.email,
        }

    async def reset_password_with_token(self, raw_token: str, new_password: str) -> bool:
        if not raw_token:
            return False

        token_hash = self.hash_password_reset_token(raw_token)
        reset_token = await PasswordResetToken.find_one({
            "token_hash": token_hash,
            "is_active": True,
        })
        if not reset_token:
            return False

        now = datetime.now(timezone.utc)
        if reset_token.used_at or reset_token.expires_at < now:
            await reset_token.set({"is_active": False})
            return False

        user = await User.get(PydanticObjectId(reset_token.user_id))
        if not user or not user.is_active:
            return False

        user.hashed_password = PasswordManager.hash_password(new_password)
        user.updated_at = now
        await user.save()

        await reset_token.set({
            "is_active": False,
            "used_at": now,
        })
        await Session.find({
            "user.$id": ObjectId(reset_token.user_id),
            "is_active": True,
        }).update({"$set": {"is_active": False}})
        return True
