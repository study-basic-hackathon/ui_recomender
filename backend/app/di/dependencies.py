from typing import Generator
from sqlalchemy.orm import Session
from app.di.container import DIContainer


# DB接続を行うジェネレータ関数
def get_db() -> Generator[Session, None, None]:
    """データベースセッションを取得"""
    yield from DIContainer.get_db()


# Repository層の依存性注入
# 例:
# def get_user_repository(db: Session = Depends(get_db)) -> IUserRepository:
#     return DIContainer.get_user_repository(db)


# UseCase層の依存性注入
# 例:
# def get_user_usecase(repo: IUserRepository = Depends(get_user_repository)) -> UserUseCase:
#     return DIContainer.get_user_usecase(repo)