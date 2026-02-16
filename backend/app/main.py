from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.middleware import ErrorHandlerMiddleware, RequestLoggingMiddleware
from app.router import router
from app.router.jobs import router as jobs_router
from app.router.settings import router as settings_router

# FastAPIのインスタンスを作成（Swagger UIのメタデータを設定）
app = FastAPI(
    title="UI Recommender API",
    description="UI推薦システムのバックエンドAPI",
    version="0.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
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
app.include_router(jobs_router)
app.include_router(settings_router)
