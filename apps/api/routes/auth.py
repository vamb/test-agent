from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response

from apps.api.auth_service import SESSION_COOKIE_NAME
from apps.api.dependencies import auth_service
from apps.api.schemas.auth import AuthResponse, LoginRequest, RegisterRequest


router = APIRouter(prefix="/auth", tags=["auth"])


def current_user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    return auth_service.get_user_by_session(token)


def require_current_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> dict:
    user = current_user_from_token(_token_from_request(session_cookie, authorization))
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def require_admin_user(user: dict = Depends(require_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user


def optional_current_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> dict | None:
    return current_user_from_token(_token_from_request(session_cookie, authorization))


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest) -> dict:
    try:
        user = auth_service.register(
            username=payload.username,
            password=payload.password,
            email=payload.email,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail="user already exists") from exc
    return {"user": user}


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> dict:
    try:
        session = auth_service.login(
            username_or_email=payload.username,
            password=payload.password,
            user_agent=request.headers.get("user-agent", ""),
            ip_address=request.client.host if request.client else "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        expires=session.expires_at,
        httponly=True,
        samesite="lax",
    )
    return {"user": session.user}


@router.post("/logout")
def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> dict:
    token = _token_from_request(session_cookie, authorization)
    revoked = auth_service.logout(token or "")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"logged_out": True, "revoked": revoked}


@router.get("/me", response_model=AuthResponse)
def me(user: dict = Depends(require_current_user)) -> dict:
    return {"user": user}


def _token_from_request(
    session_cookie: str | None,
    authorization: str | None,
) -> str | None:
    if session_cookie:
        return session_cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None
