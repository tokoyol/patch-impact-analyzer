from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import patch as patch_api
from .api import rag as rag_api
from .api import search as search_api
from .db import engine

app = FastAPI(title="Patch Impact Analyzer API")

# Allow the Next.js dev server to call the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(patch_api.router, prefix="/patch", tags=["patch"])
app.include_router(search_api.router, prefix="/search", tags=["search"])
app.include_router(rag_api.router, prefix="/rag", tags=["rag"])


@app.get("/")
def root():
    return {"status": "backend running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "database": "disconnected", "detail": str(exc)}


