"""backbone.auth.router — Authentication endpoints."""

import logging

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from bson import ObjectId

from ..core.dependencies import get_current_user
from ..core.models import Attachment, User, Session
from ..core.repository import BeanieRepository
from ..schemas import (
    GoogleLoginSchema, LoginSchema, RegisterSchema,
    TokenResponse, UserOut, UserUpdate,
)
from ..common.utils import PasswordManager, TokenManager
from .hooks import register_auth_hooks

logger = logging.getLogger("backbone.auth")

class AuthRouter:
    def __init__(self, config: Any, db_instance: Any = None, prefix: str = "/auth", tags: list = ["Auth"]):
        self.router = APIRouter(prefix=prefix, tags=tags)
        self.config = config
        
        self.user_repository = BeanieRepository(db_instance)
        self.user_repository.initialize(User)
        
        self.session_repository = BeanieRepository(db_instance)
        self.session_repository.initialize(Session)

        register_auth_hooks()
        
        self._register_routes()
    
    async def _resolve_repos(self, request: Request):
        config = request.app.state.backbone_config
        if self.user_repository.db is None:
            self.user_repository.db = config.database
        if self.session_repository.db is None:
            self.session_repository.db = config.database

    async def _resolve_profile_image(self, user: User) -> User:
        profile_image = getattr(user, "profile_image", None)
        if not profile_image:
            return user

        attachment_id = None
        if hasattr(profile_image, "ref"):
            attachment_id = profile_image.ref.id
        elif isinstance(profile_image, dict):
            attachment_id = profile_image.get("id") or profile_image.get("_id")
        elif isinstance(profile_image, str) and ObjectId.is_valid(profile_image):
            attachment_id = ObjectId(profile_image)

        if not attachment_id:
            user.profile_image = None
            return user

        attachment = await Attachment.get(attachment_id)
        user.profile_image = attachment
        return user

    @staticmethod
    def _serialise_user(user: User) -> UserOut:
        return UserOut(**user.model_dump(by_alias=True))

    def _register_routes(self):
        @self.router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
        async def register(
            request: Request, 
            user_data: RegisterSchema
        ):
            try:
                from .service import AuthService

                await self._resolve_repos(request)
                auth_service = AuthService(request)
                existing_user = await auth_service.get_user_by_email(user_data.email)
                if existing_user:
                    raise HTTPException(status_code=400, detail="Email already registered")
            
                hashed_pw = PasswordManager.hash_password(user_data.password)
                user_dict = user_data.model_dump()
                user_dict["hashed_password"] = hashed_pw
                del user_dict["password"]
                user_dict["is_active"] = True
                user_dict["is_staff"] = False
            
                new_user = await self.user_repository.create(user_dict, request=request)

                return self._serialise_user(new_user)
            except HTTPException:
                raise
            except Exception:
                logger.exception("Registration failed")
                raise

        @self.router.post("/login", response_model=TokenResponse)
        async def login(
            request: Request, 
            response: Response, 
            login_data: LoginSchema
        ):
            try:
                # await self._resolve_repos(request) # No need, AuthService handles it
                
                from .service import AuthService
                auth_service = AuthService(request)
                
                user = await auth_service.authenticate_user(login_data.email, login_data.password)
                if not user:
                     raise HTTPException(status_code=401, detail="Invalid email or password")
                
                # Create Session via AuthService
                session_data = await auth_service.create_session(
                    user=user, 
                    user_agent=request.headers.get("user-agent"),
                    ip_address=request.client.host if request.client else None
                )
    
                # Use environment-aware cookie settings from BackboneConfig
                backbone_config = request.app.state.backbone_config
                cookie_opts = backbone_config.cookie_settings
                
                response.set_cookie(
                    key="refresh_token",
                    value=session_data["refresh_token"],
                    max_age=7 * 24 * 60 * 60,
                    **cookie_opts
                )
                
                return {
                    "access_token": session_data["access_token"],
                    "refresh_token": session_data["refresh_token"],
                    "token_type": "bearer"
                }
            except HTTPException:
                raise
            except Exception:
                logger.exception("Login failed")
                raise

        @self.router.post("/google/login", response_model=TokenResponse)
        async def google_login(
            request: Request,
            response: Response,
            login_data: GoogleLoginSchema
        ):
            try:
                import httpx
                await self._resolve_repos(request)
                
                # Retrieve configured Client ID and Secret
                backbone_config = request.app.state.backbone_config
                client_id = backbone_config.config.GOOGLE_CLIENT_ID
                client_secret = backbone_config.config.GOOGLE_CLIENT_SECRET
                
                if not client_id or not client_secret:
                    raise HTTPException(status_code=500, detail="Google authentication is not configured on the server.")

                # Exchange auth code for access token
                token_url = "https://oauth2.googleapis.com/token"
                token_data = {
                    "code": login_data.code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": "postmessage",  # Usually required for frontend popup flow
                    "grant_type": "authorization_code"
                }
                
                async with httpx.AsyncClient() as client:
                    token_res = await client.post(token_url, data=token_data)
                    
                    if token_res.status_code != 200:
                        raise HTTPException(status_code=400, detail=f"Failed to verify Google code: {token_res.text}")
                        
                    tokens = token_res.json()
                    access_token = tokens.get("access_token")
                    
                    # Fetch user info using access token
                    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
                    user_res = await client.get(user_info_url, headers={"Authorization": f"Bearer {access_token}"})
                    
                    if user_res.status_code != 200:
                        raise HTTPException(status_code=400, detail="Failed to fetch user profile from Google")
                        
                    user_info = user_res.json()
                    
                email = user_info.get("email")
                full_name = user_info.get("name")
                picture_url = user_info.get("picture")
                
                if not email:
                    raise HTTPException(status_code=400, detail="Google account has no email associated")
                    
                from .service import AuthService
                auth_service = AuthService(request)
                
                # Check if user already exists
                user = await auth_service.get_user_by_email(email)
                
                # Create user if they don't exist
                if not user:
                    # Provide a random secure password for OAuth users because it's required by the model
                    import secrets
                    random_password = secrets.token_urlsafe(32)
                    hashed_pw = PasswordManager.hash_password(random_password)
                    
                    new_user_data = {
                        "email": email,
                        "full_name": full_name,
                        "hashed_password": hashed_pw,
                        "is_active": True,
                        "is_staff": False,
                        "is_google_account": True,
                    }
                    user = await self.user_repository.create(new_user_data, request=request)

                # After creating/fetching user, ensure is_google_account is True and update picture if needed
                needs_save = False
                
                # Ensure is_google_account is True for existing users logging in via Google
                if getattr(user, "is_google_account", False) is False:
                    user.is_google_account = True
                    needs_save = True

                # Handle Google profile picture
                if picture_url and not getattr(user, "profile_image", None):
                    from ..core.models import Attachment
                    # Create attachment for the Google profile image
                    attachment = Attachment(
                        filename=f"google_profile_{user.id}.jpg",
                        file_path=picture_url,
                        content_type="image/jpeg",
                        collection_name="users",
                        document_id=str(user.id),
                        field_name="profile_image",
                        status="completed"
                    )
                    await attachment.insert()
                    
                    # Beanie requires Link fields to either be the raw Document or a DBRef
                    user.profile_image = attachment
                    needs_save = True
                    
                if needs_save:
                    await user.save()

                # Create Session via AuthService
                session_data = await auth_service.create_session(
                    user=user, 
                    user_agent=request.headers.get("user-agent"),
                    ip_address=request.client.host if request.client else None
                )
    
                # Use environment-aware cookie settings from BackboneConfig
                cookie_opts = backbone_config.cookie_settings
                
                response.set_cookie(
                    key="refresh_token",
                    value=session_data["refresh_token"],
                    max_age=7 * 24 * 60 * 60,
                    **cookie_opts
                )
                
                return {
                    "access_token": session_data["access_token"],
                    "refresh_token": session_data["refresh_token"],
                    "token_type": "bearer"
                }

            except HTTPException:
                raise
            except Exception:
                logger.exception("Google login failed")
                raise HTTPException(status_code=500, detail="Google login failed")
                
        @self.router.post("/refresh")
        async def refresh(
            request: Request, 
            response: Response
        ):
            await self._resolve_repos(request)
            refresh_token = request.cookies.get("refresh_token")
            if not refresh_token:
                raise HTTPException(status_code=401, detail="No refresh token")

            payload = TokenManager.verify_token(refresh_token)
            if not payload:
                raise HTTPException(status_code=401, detail="Invalid refresh token")

            sid = payload.get("sid")
            from .service import AuthService
            auth_service = AuthService(request)
            session = await auth_service.get_active_session(sid)
            if not session or session.refresh_token != refresh_token:
                raise HTTPException(status_code=401, detail="Session expired or invalid")
            
            user_id = payload.get("sub")
            new_access_token = TokenManager.create_access_token({"sub": user_id}, sid=sid)
            
            return {"access_token": new_access_token, "token_type": "bearer"}

        @self.router.post("/logout")
        async def logout(
            request: Request,
            response: Response
        ):
            await self._resolve_repos(request)
            refresh_token = request.cookies.get("refresh_token")
            
            if refresh_token:
                try:
                    payload = TokenManager.verify_token(refresh_token)
                    if payload:
                        sid = payload.get("sid")
                        if sid:
                            from .service import AuthService
                            auth_service = AuthService(request)
                            await auth_service.logout(sid)
                except Exception:
                    pass # Ignore verification failures on logout

            cookie_opts = request.app.state.backbone_config.cookie_settings
            response.delete_cookie(
                key="refresh_token",
                httponly=True,
                secure=cookie_opts.get("secure", False),
                samesite=cookie_opts.get("samesite", "lax")
            )
            return {"detail": "Logged out successfully"}

        @self.router.get("/me", response_model=UserOut)
        async def get_me(
            user: User = Depends(get_current_user)
        ):
            try:
                user = await self._resolve_profile_image(user)
                return self._serialise_user(user)
            except Exception:
                logger.exception("Get user profile failed")
                raise

        @self.router.patch("/me", response_model=UserOut)
        async def update_me(
            request: Request,
            user_data: UserUpdate,
            user: User = Depends(get_current_user)
        ):
            try:
                if user_data.full_name is not None:
                    user.full_name = user_data.full_name
                if user_data.headline is not None:
                    user.headline = user_data.headline
                if user_data.bio is not None:
                    user.bio = user_data.bio
                
                if user_data.profile_image:
                    try:
                        attachment = await Attachment.get(user_data.profile_image)
                        if attachment:
                            user.profile_image = attachment
                    except Exception:
                        logger.warning("Failed to fetch profile image attachment '%s'", user_data.profile_image)
                
                await user.save()

                user = await self._resolve_profile_image(user)
                return self._serialise_user(user)
            except Exception:
                logger.exception("Update user profile failed")
                raise
