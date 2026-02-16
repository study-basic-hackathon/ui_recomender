# API層
# - 役割
#     - 外部からの REST リクエストの受付
#     - リクエスト / レスポンスの変換
#     - 認証・認可の確認
#     - UseCase 層への処理委譲
# - 特徴
#     - 薄い層でビジネスロジックは含まない
#     - ドメインごとにファイル分割（例: users.py, items.py）
#     - テストファイルも同階層に配置

from .api import router

__all__ = ["router"]
