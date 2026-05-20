from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ..common.utils import PasswordManager, TokenManager
from ..core.models import User
from .shared import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    settings = request.app.state.backbone_config.config
    superuser_count = await User.find({"is_superuser": True}).count()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "superuser_exists": superuser_count > 0,
            "default_email": settings.ADMIN_EMAIL,
            "default_password": settings.ADMIN_PASSWORD,
            "error": None,
        },
    )


@router.post("/login")
async def login_handle(request: Request, email: str = Form(...), password: str = Form(...)):
    superuser_count = await User.find({"is_superuser": True}).count()

    # 1. Handle Superuser Creation if none exists
    if superuser_count == 0:
        hashed_pw = PasswordManager.hash_password(password)
        new_superuser = User(
            email=email,
            full_name=email.split("@")[0].title() or "Admin",
            hashed_password=hashed_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        await new_superuser.insert()
        user = new_superuser
    else:
        # 2. Normal Login via AuthService
        # Fetch user by email manually since AuthService expects email for standard login
        user = await User.find_one({"email": email})

        if not user or not PasswordManager.verify_password(password, user.hashed_password):
            settings = request.app.state.backbone_config.config
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "request": request,
                    "superuser_exists": True,
                    "default_email": settings.ADMIN_EMAIL,
                    "default_password": settings.ADMIN_PASSWORD,
                    "error": "Invalid username or password",
                },
            )

        if not user.is_superuser:
            settings = request.app.state.backbone_config.config
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "request": request,
                    "superuser_exists": True,
                    "default_email": settings.ADMIN_EMAIL,
                    "default_password": settings.ADMIN_PASSWORD,
                    "error": "Access denied. Superuser only.",
                },
            )

    # Create Session via AuthService
    from ..auth.service import AuthService

    auth_service = AuthService(request)

    # We use a manual session creation here because we already verified password
    session_data = await auth_service.create_session(
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    access_token = session_data["access_token"]

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    cookie_opts = request.app.state.backbone_config.cookie_settings
    response.set_cookie(key="admin_session", value=access_token, **cookie_opts)
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    cookie_opts = request.app.state.backbone_config.cookie_settings
    response.delete_cookie(
        "admin_session",
        secure=cookie_opts.get("secure", False),
        samesite=cookie_opts.get("samesite", "lax"),
    )

    # Ideally invalidate session in DB too
    token = request.cookies.get("admin_session")
    if token:
        try:
            payload = TokenManager.decode_token(token)
            if payload:
                sid = payload.get("sid")
                from ..auth.service import AuthService

                auth_service = AuthService(request)
                await auth_service.logout(sid)
        except Exception:
            pass

    return response
