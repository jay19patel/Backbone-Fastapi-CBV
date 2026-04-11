import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import Request
from beanie import PydanticObjectId
from bson import ObjectId
from bson.dbref import DBRef

from backbone.core.models import Session, User
from backbone.common.utils import PasswordManager, TokenManager, logger
from backbone.core.repository import BeanieRepository
from backbone.email_sender import email_sender


class AuthService:
    def __init__(self, request: Request = None, db_instance: Any = None):
        """
        Initialize AuthService with request context to access app state and DB.
        """
        self.request = request
        self.db = db_instance
        
        # Resolve DB from request if not provided explicitly
        if self.db is None and request:
            self.db = request.app.state.backbone_config.database

        self.user_repo = BeanieRepository(self.db)
        self.user_repo.initialize(User)
        
        self.session_repo = BeanieRepository(self.db)
        self.session_repo.initialize(Session)

    async def sync_admin_user(self, email: str, password: str):
        """
        Ensure the admin user exists with the configured credentials.
        Updates the password if the user already exists.
        """
        if not email or not password:
            return

        user = await self.get_user_by_email(email)
        hashed_password = PasswordManager.hash_password(password)

        if not user:
            from backbone.core.models import User
            admin = User(
                email=email,
                full_name="Administrator",
                hashed_password=hashed_password,
                is_active=True,
                is_staff=True,
                is_superuser=True
            )
            await admin.insert()
            from backbone.common.utils import logger
            logger.info(f"Admin user created: {email}")
        else:
            # Update password if it has changed (optional check, but safer to just update)
            if not PasswordManager.verify_password(password, user.hashed_password):
                user.hashed_password = hashed_password
                await user.save()
                from backbone.common.utils import logger
                logger.info(f"Admin user password updated: {email}")
            
            # Ensure staff/active status
            if not user.is_staff or not user.is_active:
                user.is_staff = True
                user.is_active = True
                await user.save()


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
    def create_action_token(data: dict, action: str, expires_delta: Optional[timedelta] = None) -> str:
        from ..core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
        to_encode.update({"exp": expire, "action": action})
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        from ..core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        try:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        except Exception:
            return None

    async def create_password_reset_request(self, email: str, expires_in_minutes: int = 60) -> Optional[Dict[str, Any]]:
        user = await self.get_user_by_email(email)
        if not user or not user.is_active:
            return None

        # To make it one-time use without a DB, we use a fragment of the password hash as a 'stamp'.
        # If the password changes, the stamp changes, and the JWT becomes invalid.
        stamp = hashlib.sha256(user.hashed_password.encode()).hexdigest()[:16]
        
        token = self.create_action_token(
            {"sub": str(user.id), "email": user.email, "stamp": stamp},
            action="password_reset",
            expires_delta=timedelta(minutes=expires_in_minutes)
        )
        
        return {
            "token": token,
            "user_id": str(user.id),
            "email": user.email,
        }

    async def reset_password_with_token(self, token: str, new_password: str) -> bool:
        if not token:
            return False

        payload = self.decode_token(token)
        if not payload or payload.get("action") != "password_reset":
            return False

        user_id = payload.get("sub")
        stamp = payload.get("stamp")
        if not user_id or not stamp:
            return False

        user = await User.get(PydanticObjectId(user_id))
        if not user or not user.is_active:
            return False

        # Verify the security 'stamp' hasn't changed (password hasn't been reset already)
        current_stamp = hashlib.sha256(user.hashed_password.encode()).hexdigest()[:16]
        if current_stamp != stamp:
             return False

        now = datetime.now(timezone.utc)
        user.hashed_password = PasswordManager.hash_password(new_password)
        user.updated_at = now
        await user.save()

        # Invalidate all active sessions for this user on password change
        await Session.find({
            "user.$id": ObjectId(user_id),
            "is_active": True,
        }).update({"$set": {"is_active": False}})
        return True

    async def create_verification_request(self, user: User) -> str:
        """
        Produce a secure stateless verification JWT.
        """
        token = TokenManager.create_action_token(
            {"sub": str(user.id), "email": user.email},
            action="email_verification",
            expires_delta=timedelta(hours=24)
        )
        return token

    async def verify_email_with_token(self, token: str) -> bool:
        """
        Validate a stateless JWT, mark user as verified.
        """
        if not token:
            return False
            
        payload = TokenManager.decode_token(token)
        if not payload or payload.get("action") != "email_verification":
            return False

        user_id = payload.get("sub")
        if not user_id:
            return False
            
        user = await User.get(PydanticObjectId(user_id))
        if not user:
            return False
            
        if getattr(user, "is_verified", False):
            return True # Already verified
            
        user.is_verified = True
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        
        return True

    async def send_welcome_email(self, user: User, verification_url: Optional[str] = None):
        """Send a welcome email using the default backbone template."""
        try:
            from backbone.core.config import BackboneConfig
            settings = BackboneConfig.get_instance().config
            
            context = {
                "full_name": user.full_name,
                "verification_url": verification_url,
                "current_year": datetime.now(timezone.utc).year,
                "site_name": getattr(settings, "SITE_NAME", "Soul Craft Studio")
            }
            await email_sender.queue_email(
                to_email=user.email,
                subject=f"Welcome to {getattr(settings, 'SITE_NAME', 'Soul Craft Studio')}!",
                template_name="email/welcome.html",
                context=context
            )
        except Exception as e:
            logger.error(f"Failed to queue welcome email: {e}")


    async def send_verification_email(self, user: User, backend_verify_url: str):
        """Send verification email with a personalized link hitting the backend directly."""
        try:
            token = await self.create_verification_request(user)
            from backbone.core.config import BackboneConfig
            settings = BackboneConfig.get_instance().config
            
            # Use the provided backend URL (e.g. http://localhost:8000/api/auth/verify)
            full_url = f"{backend_verify_url}?token={token}"
            
            context = {
                "full_name": user.full_name,
                "verification_url": full_url,
                "current_year": datetime.now(timezone.utc).year,
                "site_name": getattr(settings, "SITE_NAME", "Soul Craft Studio")
            }
            await email_sender.queue_email(
                to_email=user.email,
                subject=f"Verify your email for {getattr(settings, 'SITE_NAME', 'Soul Craft Studio')}",
                template_name="email/verify_email.html",
                context=context
            )
        except Exception as e:
            logger.error(f"Failed to queue verification email: {e}")

