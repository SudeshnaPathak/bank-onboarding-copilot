from __future__ import annotations

from sqlalchemy import select

from ..db import session_scope
from ..models import User
from ..security.auth import hash_password

DEMO_USERS = [
    ("priya@example.com", "Priya Sharma", "customer", "demo1234"),
    ("amit@example.com", "Amit Verma", "customer", "demo1234"),
    ("ravi@bank.example.com", "Ravi Menon", "analyst", "demo1234"),
]


async def seed_demo_users() -> None:
    async with session_scope() as s:
        for email, name, role, pw in DEMO_USERS:
            if (await s.execute(select(User).where(User.email == email))).scalar_one_or_none() is None:
                s.add(User(email=email, name=name, role=role, password_hash=hash_password(pw)))
