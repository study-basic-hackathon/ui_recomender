from typing import Generator
from sqlalchemy.orm import Session
from app.repository.database import SessionLocal


class DIContainer:
    """依存性注入コンテナ"""

    @staticmethod
    def get_db() -> Generator[Session, None, None]:
        """データベースセッションを取得"""
        try:
            db = SessionLocal()
            yield db
        finally:
            db.close()

    # Repository層のインスタンス生成
    # 例:
    # @staticmethod
    # def get_user_repository(db: Session) -> IUserRepository:
    #     return UserSQLRepository(db)

    # UseCase層のインスタンス生成
    # 例:
    # @staticmethod
    # def get_user_usecase(user_repo: IUserRepository) -> UserUseCase:
    #     return UserUseCase(user_repo)
