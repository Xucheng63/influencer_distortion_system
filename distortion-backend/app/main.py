"""
app/main.py  —  FastAPI 应用入口
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.core.database import init_db
from app.api.routes import router
from app.services.scheduler import start_scheduler, shutdown_scheduler

load_dotenv()

CORS_ORIGINS = [
    o.strip() for o in
    os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",")
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()      # 每日 06:00 UTC 刷新 watchlist
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Influencer Distortion Detection API",
    version="1.0.0",
    docs_url="/docs",       # Swagger UI: http://localhost:8000/docs
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
