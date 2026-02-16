# UI Recommender Backend

## セットアップ
```bash
# 環境変数ファイルをコピー
cp .env.example .env

# サーバー起動
docker-compose up --build
```
開発サーバーが http://localhost:8000 で起動します。

## 利用可能なコマンド
```bash
# サーバー起動
docker-compose up

# サーバー停止
docker-compose down

# コンテナ内でコマンド実行
docker-compose exec app <コマンド>

# コンテナ内のシェルに入る
docker-compose exec app bash

# 依存パッケージの追加
docker-compose exec app uv add <パッケージ名>

# マイグレーションファイル作成
docker-compose exec app uv run alembic revision --autogenerate -m "<メッセージ>"

# マイグレーション実行
docker-compose exec app uv run alembic upgrade head

# マイグレーション履歴確認
docker-compose exec app uv run alembic history
```

## 技術スタック
- Python 3.13
- FastAPI 0.129.0
- SQLAlchemy 2.0.46
- PostgreSQL 17
- Alembic 1.18.4
- uv