from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.router import router

# FastAPIのインスタンスを作成（Swagger UIのメタデータを設定）
app = FastAPI(
    title="UI Recommender API",
    description="UI推薦システムのバックエンドAPI",
    version="0.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
)

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
