from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth import (
    AuthContext,
    clear_auth_cookie,
    create_access_token,
    require_auth,
    set_auth_cookie,
    verify_password,
)
from app.database import get_user_by_email
from app.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(req: LoginRequest, response: Response):
    settings = get_settings()
    user = get_user_by_email(settings.app_db_path, req.email.lower())
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user, settings)
    set_auth_cookie(response, token, settings)
    return {
        "user": {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "org_id": user.org_id,
            "role": user.role,
        }
    }


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(auth: AuthContext = Depends(require_auth)) -> dict[str, AuthContext]:
    return {"user": auth}
