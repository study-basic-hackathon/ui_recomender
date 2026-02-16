# Schema層（DTO層）
# - 役割
#     - APIリクエスト/レスポンスの型定義
#     - バリデーション
#     - ドメインエンティティとの変換
# - 特徴
#     - Pydanticを使用
#     - Request/Responseで分離
#     - OpenAPI（Swagger）のドキュメント生成に使用
#
# 例: from .user import UserRequest, UserResponse

__all__ = []
