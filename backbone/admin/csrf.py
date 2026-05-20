"""CSRF protection for cookie-authenticated admin routes."""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSRF_COOKIE_NAME = "admin_csrf"
CSRF_FIELD_NAME = "_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_COOKIE_MAX_AGE = 60 * 60 * 2
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class AdminCSRFMiddleware:
    """Signed double-submit CSRF protection for ``/admin`` mutations."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        cookie_name: str = CSRF_COOKIE_NAME,
        field_name: str = CSRF_FIELD_NAME,
        header_name: str = CSRF_HEADER_NAME,
        path_prefix: str = "/admin",
    ) -> None:
        self.app = app
        self.cookie_name = cookie_name
        self.field_name = field_name
        self.header_name = header_name.lower()
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})
        method = scope.get("method", "GET").upper()
        request = Request(scope, receive)
        signed_cookie = request.cookies.get(self.cookie_name)
        token = self._verified_cookie_token(scope, signed_cookie)
        should_set_cookie = token is None
        if token is None:
            token = secrets.token_urlsafe(32)
        scope["state"]["admin_csrf_token"] = token

        if method not in SAFE_METHODS:
            body = await request.body()
            submitted = self._submitted_token(scope, body)
            if not token or not submitted or not hmac.compare_digest(token, submitted):
                response = PlainTextResponse(
                    "CSRF token missing or invalid.",
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )
                response.delete_cookie(self.cookie_name, path=self.path_prefix)
                await response(scope, self._replay_body(body), send)
                return

            receive = self._replay_body(body)

        async def send_with_cookie(message: Message) -> None:
            if should_set_cookie and message["type"] == "http.response.start":
                cookie = self._build_cookie(scope, token)
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie.encode("latin-1")))
                message["headers"] = headers
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    def _verified_cookie_token(self, scope: Scope, signed_cookie: str | None) -> str | None:
        if not signed_cookie or ":" not in signed_cookie:
            return None
        token, signature = signed_cookie.rsplit(":", 1)
        expected = self._sign(scope, token)
        if hmac.compare_digest(signature, expected):
            return token
        return None

    def _submitted_token(self, scope: Scope, body: bytes) -> str | None:
        headers = Headers(scope=scope)
        header_token = headers.get(self.header_name)
        if header_token:
            return header_token

        content_type = headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
            values = form.get(self.field_name)
            return values[0] if values else None

        if "multipart/form-data" in content_type:
            token_marker = f'name="{self.field_name}"'.encode()
            marker_index = body.find(token_marker)
            if marker_index == -1:
                return None
            value_start = body.find(b"\r\n\r\n", marker_index)
            if value_start == -1:
                return None
            value_start += 4
            value_end = body.find(b"\r\n", value_start)
            if value_end == -1:
                return None
            return body[value_start:value_end].decode("utf-8", errors="ignore")

        return None

    def _build_cookie(self, scope: Scope, token: str) -> str:
        config = scope.get("app").state.backbone_config
        cookie_settings = getattr(config, "cookie_settings", {})
        signed = f"{token}:{self._sign(scope, token)}"

        cookie = SimpleCookie()
        cookie[self.cookie_name] = signed
        morsel = cookie[self.cookie_name]
        morsel["path"] = self.path_prefix
        morsel["httponly"] = True
        morsel["samesite"] = cookie_settings.get("samesite", "lax")
        if cookie_settings.get("secure", False):
            morsel["secure"] = True
        max_age = getattr(config.config, "ADMIN_CSRF_COOKIE_MAX_AGE", CSRF_COOKIE_MAX_AGE)
        if max_age:
            morsel["max-age"] = str(max_age)
        return morsel.OutputString()

    def _sign(self, scope: Scope, token: str) -> str:
        config = scope.get("app").state.backbone_config.config
        secret = getattr(config, "secret_key", None) or getattr(config, "SECRET_KEY", "")
        return hmac.new(str(secret).encode(), token.encode(), sha256).hexdigest()

    @staticmethod
    def _replay_body(body: bytes) -> Receive:
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return receive
