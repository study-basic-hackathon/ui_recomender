# Repository層
# - 役割
#     - データ永続化の抽象化
#     - データベースアクセスの実装
#     - 外部API連携の実装
#     - Domainエンティティ ⇔ ORMモデルの変換
# - 特徴
#     - インターフェース（抽象基底クラス）と実装を分離
#     - UseCaseからはインターフェース経由で呼び出す
#     - テスト時にモックに差し替え可能
# - 構成
#     - database.py: DB接続設定
#     - *_repository_interface.py: リポジトリインターフェース
#     - *_repository_sql.py: SQL実装

from .database import SessionLocal, engine
from .job_repository import JobRepository
from .proposal_repository import ProposalRepository
from .setting_repository import SettingRepository

__all__ = [
    "SessionLocal",
    "engine",
    "JobRepository",
    "ProposalRepository",
    "SettingRepository",
]
