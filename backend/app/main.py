"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.db import init_db
from app.routers import router
from app.routers_cash import router as cash_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Tuition Cash Desk API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(cash_router)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
