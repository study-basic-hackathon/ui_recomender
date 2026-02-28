import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.middleware import ErrorHandlerMiddleware, RequestLoggingMiddleware
from app.router import router
from app.router.sessions import router as sessions_router
from app.router.settings import router as settings_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    from app.usecase.session_usecase import recover_stuck_proposals

    await recover_stuck_proposals()
    yield


# FastAPIのインスタンスを作成（Swagger UIのメタデータを設定）
app = FastAPI(
    title="UI Recommender API",
    description="UI推薦システムのバックエンドAPI",
    version="0.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    lifespan=lifespan,
)

# ミドルウェア登録（後に追加したものが先に実行される）
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlerMiddleware)

# CORS を許可（Vite の URL）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # フロントエンドのURL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API層のルーティングを読み込む
app.include_router(router)
app.include_router(sessions_router)
app.include_router(settings_router)
