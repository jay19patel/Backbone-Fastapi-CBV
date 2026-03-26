from typing import Any, Dict

from fastapi import APIRouter, Request

from ..core.permissions import AllowAny
from ..generic.views import GenericFormView
from .service import AuthService


class PasswordResetRequestPage(GenericFormView):
    template_name = "pages/auth/reset_password_request.html"
    permission_classes = [AllowAny]
    page_name = "Reset Password"
    page_description = "Request a password reset token for an account."
    admin_category = "Auth Pages"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        return {
            "submitted": False,
            "success": False,
            "submitted_email": "",
            "reset_token": "",
            "reset_url": "",
            "error": "",
        }

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        email = str(form_data.get("email", "")).strip()
        if not email:
            return {
                "submitted": True,
                "success": False,
                "submitted_email": "",
                "reset_token": "",
                "reset_url": "",
                "error": "Email is required.",
            }

        auth_service = AuthService(request)
        reset_request = await auth_service.create_password_reset_request(email)
        context = {
            "submitted": True,
            "success": True,
            "submitted_email": email,
            "message": "If the account exists, a reset flow has been created.",
            "reset_token": "",
            "reset_url": "",
            "error": "",
        }

        if reset_request and request.app.state.backbone_config.is_development:
            token = reset_request["token"]
            context["reset_token"] = token
            context["reset_url"] = str(request.url_for("password_reset_confirm_page")) + f"?token={token}"

        return context


class PasswordResetConfirmPage(GenericFormView):
    template_name = "pages/auth/reset_password_confirm.html"
    permission_classes = [AllowAny]
    page_name = "Confirm Password Reset"
    page_description = "Complete the password reset with the provided token."
    admin_category = "Auth Pages"

    async def get_context_data(self, request: Request, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        token = request.query_params.get("token", "")
        return {
            "token": token,
            "success": False,
            "error": "",
            "submitted": False,
        }

    async def handle_submit(self, request: Request, form_data: Dict[str, Any], user: Any = None) -> Dict[str, Any]:
        token = str(form_data.get("token", "")).strip()
        password = str(form_data.get("password", "")).strip()
        confirm_password = str(form_data.get("confirm_password", "")).strip()

        if not token:
            return {"token": token, "success": False, "submitted": True, "error": "Reset token is required."}
        if not password or len(password) < 8:
            return {"token": token, "success": False, "submitted": True, "error": "Password must be at least 8 characters."}
        if password != confirm_password:
            return {"token": token, "success": False, "submitted": True, "error": "Passwords do not match."}

        auth_service = AuthService(request)
        success = await auth_service.reset_password_with_token(token, password)
        if not success:
            return {"token": token, "success": False, "submitted": True, "error": "Reset token is invalid or expired."}

        return {
            "token": "",
            "success": True,
            "submitted": True,
            "error": "",
        }


router = APIRouter()
router.include_router(
    PasswordResetRequestPage.as_router(
        "/reset-password",
        tags=["Pages"],
        name="password_reset_request_page",
        admin_path="/pages/reset-password",
    )
)
router.include_router(
    PasswordResetConfirmPage.as_router(
        "/reset-password/confirm",
        tags=["Pages"],
        name="password_reset_confirm_page",
        admin_path="/pages/reset-password/confirm",
    )
)
