# Model層
# - 役割
#     - SQLAlchemyのORMモデル定義
#     - データベーステーブル構造の定義
#     - データベーススキーマとの対応付け
# - 特徴
#     - Domainエンティティとは分離
#     - マイグレーション（Alembic）で使用
#     - Repository層の実装で使用

from .job import Job, JobStatus, Proposal, ProposalStatus, Setting

__all__ = ["Job", "JobStatus", "Proposal", "ProposalStatus", "Setting"]
