from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..db import session_scope
from ..deps import current_user
from ..models import User
from ..security.auth import create_token, verify_password
from ..services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role}


@router.post("/login")
async def login(body: LoginIn) -> dict:
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == body.email.strip().lower()))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        await audit.record("system", "auth.login_failed", None, {"email": body.email[:80]})
        raise HTTPException(401, "Incorrect email or password")
    await audit.record(f"user:{user.id}", "auth.login", None, {"role": user.role})
    return {"token": create_token(user.id, user.role), "user": _user_out(user)}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return _user_out(user)
