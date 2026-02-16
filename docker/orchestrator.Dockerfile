# ベースイメージ
FROM python:3.13-slim

# 作業ディレクトリの設定
WORKDIR /app

# 必要なシステムパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uvのインストール
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# プロジェクトファイルのコピー
COPY backend/pyproject.toml backend/uv.lock ./

# 依存関係のインストール
# --system: システムのPythonに直接インストール（コンテナ内では問題ない）
RUN uv sync --frozen --no-cache

# ソースコードのコピー
COPY backend/ .

# FastAPIアプリケーションの起動
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
