from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from .db import session_scope
from .models import Case, User
from .security.auth import decode_token

_bearer = HTTPBearer(auto_error=False)


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    async with session_scope() as s:
        user = await s.get(User, payload["sub"])
    if user is None:
        raise HTTPException(401, "Unknown user")
    return user


def require_role(role: str):
    async def _dep(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(403, "Forbidden")
        return user
    return _dep


async def customer_case(case_id: str, user: User = Depends(require_role("customer"))) -> Case:
    """A customer can only ever touch their own case (blocks IDOR). 404, not 403, to avoid leaking existence."""
    async with session_scope() as s:
        case = (await s.execute(select(Case).where(Case.id == case_id, Case.user_id == user.id))).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Case not found")
    return case
