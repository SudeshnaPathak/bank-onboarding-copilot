from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, cases, demo, review
from .config import get_settings
from .db import dispose_db, init_db
from .deps import require_role
from .graphs.review import build_review_graph, set_review_graph
from .llm import stats
from .llm.factory import get_llm
from .ocr.engine import get_engine
from .services import audit
from .services.seed import seed_demo_users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _open_checkpointer(stack, url: str):
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(url))
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(url))
    await saver.setup()
    return saver


@asynccontextmanager
async def lifespan(app: FastAPI):
    from contextlib import AsyncExitStack
    settings = get_settings()
    await init_db()
    if settings.demo_mode:
        await seed_demo_users()
    async with AsyncExitStack() as stack:
        saver = await _open_checkpointer(stack, settings.checkpoint_url)
        set_review_graph(build_review_graph(saver))
        yield
    await dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Onboarding Copilot API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    for r in (auth.router, cases.router, review.router):
        app.include_router(r, prefix="/api")
    if settings.demo_mode:
        app.include_router(demo.router, prefix="/api")

    @app.get("/api/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "ok", "llm": get_llm().name, "ocr": get_engine().name, "demo_mode": settings.demo_mode}

    @app.get("/api/health/llm", tags=["ops"])
    async def llm_usage() -> dict:
        return {"provider": get_llm().name, **stats.snapshot()}

    @app.get("/api/audit/verify", tags=["ops"], dependencies=[Depends(require_role("analyst"))])
    async def verify_audit() -> dict:
        return await audit.verify_chain()

    return app


app = create_app()
