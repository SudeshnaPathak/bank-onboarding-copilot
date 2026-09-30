from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # customer | analyst
    password_hash: Mapped[str] = mapped_column(String(300))


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    product: Mapped[str] = mapped_column(String(40))
    # draft | under_review | info_requested | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    form: Mapped[dict] = mapped_column(JSON, default=dict)  # confirmed values + details
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)  # field -> [candidate, ...] (masked)
    submission_no: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(lazy="joined")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(30))
    storage_key: Mapped[str] = mapped_column(String(200))  # encrypted file on disk
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(40), default="image/png")
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    fields_enc: Mapped[str] = mapped_column(Text, default="")  # Fernet(JSON): full values + raw text
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # masked fields, confidence, source
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant | system
    text: Mapped[str] = mapped_column(Text)
    ui: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # cards: confirm, upload_request, ...
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # agent trace for this turn
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewRun(Base):
    __tablename__ = "review_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    submission_no: Mapped[int] = mapped_column(Integer)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(20))
    breakdown: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)  # rules hash, model, prompt versions
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    submission_no: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(20))  # approve | reject | request_info
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    """Append-only, hash-chained. On Postgres also enforce with db/immutability.sql."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80))  # "user:<id>" | "agent:<node>" | "system"
    action: Mapped[str] = mapped_column(String(60))
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
