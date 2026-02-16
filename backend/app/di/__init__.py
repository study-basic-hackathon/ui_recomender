# 依存性注入層（DI Layer）
# - 役割
#     - 依存性の管理
#     - オブジェクトの生成・注入

from .container import DIContainer
from .dependencies import get_db

__all__ = [
    "DIContainer",
    "get_db",
]
