from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import Cookie, Depends, HTTPException, Response, status
from pwdlib import PasswordHash
from pydantic import BaseModel

from app.settings import Settings, get_settings


AUTH_COOKIE_NAME = "chartdex_access_token"
JWT_ALG = "HS256"
password_hash = PasswordHash.recommended()


class User(BaseModel):
    id: str
    email: str
    name: str
    org_id: str
    role: Literal["admin", "analyst", "viewer"]
    password_hash: str


class AuthContext(BaseModel):
    user_id: str
    email: str
    name: str
    org_id: str
    role: str


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user: User, settings: Settings | None = None) -> str:
    resolved_settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "org_id": user.org_id,
        "role": user.role,
        "iss": resolved_settings.jwt_issuer,
        "aud": resolved_settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=resolved_settings.access_token_minutes),
    }
    return jwt.encode(payload, resolved_settings.jwt_secret, algorithm=JWT_ALG)


def verify_access_token(token: str, settings: Settings | None = None) -> AuthContext:
    resolved_settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            resolved_settings.jwt_secret,
            algorithms=[JWT_ALG],
            issuer=resolved_settings.jwt_issuer,
            audience=resolved_settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc

    return AuthContext(
        user_id=claims["sub"],
        email=claims["email"],
        name=claims["name"],
        org_id=claims["org_id"],
        role=claims["role"],
    )


def set_auth_cookie(response: Response, token: str, settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=resolved_settings.access_token_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="lax")


def require_auth(chartdex_access_token: str | None = Cookie(default=None)) -> AuthContext:
    if not chartdex_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return verify_access_token(chartdex_access_token)


def require_role(*allowed_roles: str):
    def dependency(auth: AuthContext = Depends(require_auth)) -> AuthContext:
        if auth.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return auth

    return dependency
