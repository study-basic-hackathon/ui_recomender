from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.di import get_db
import logging

# ロガーの設定
logger = logging.getLogger(__name__)

# APIRouterインスタンスを作成（ルーティングを管理する）
router = APIRouter()


@router.get("/")
def get_root():
    """ルートエンドポイント"""
    return {"message": "UI Recommender API is running"}


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    ヘルスチェック用エンドポイント
    - アプリケーションの稼働状態を確認
    - データベース接続を確認
    - Dockerのヘルスチェックで使用
    """
    try:
        # データベース接続確認
        result = db.execute(text("SELECT 1"))
        result.scalar()  # 結果を取得して接続を確認
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }