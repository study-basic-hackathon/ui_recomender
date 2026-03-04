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
#     - *_repository.py: リポジトリ実装

from .database import SessionLocal
from .iteration_repository import IterationRepository
from .proposal_repository import ProposalRepository
from .protocols import (
    IterationRepositoryProtocol,
    ProposalRepositoryProtocol,
    SessionRepositoryProtocol,
    SettingRepositoryProtocol,
)
from .session_repository import SessionRepository
from .setting_repository import SettingRepository

__all__ = [
    "SessionLocal",
    "SessionRepository",
    "IterationRepository",
    "ProposalRepository",
    "SettingRepository",
    "SessionRepositoryProtocol",
    "IterationRepositoryProtocol",
    "ProposalRepositoryProtocol",
    "SettingRepositoryProtocol",
]
