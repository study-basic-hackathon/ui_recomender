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

## デプロイ手順

Backend と Worker の変更を反映する手順です。

### Backend (FastAPI) の再起動
```bash
cd backend
docker compose restart app
```

### Worker イメージの再ビルド・K8s ロード
```bash
# 1. イメージをビルド
docker build -t ui-recommender-worker:latest -f docker/worker.Dockerfile .

# 2. Docker Desktop の組み込み K8s にロード
docker save ui-recommender-worker:latest | docker exec -i desktop-control-plane ctr -n k8s.io images import -
```

> **Note:** Worker Pod は `imagePullPolicy: Never` で運用しているため、レジストリへの push は不要です。

## 技術スタック
- Python 3.13
- FastAPI 0.129.0
- SQLAlchemy 2.0.46
- PostgreSQL 17
- Alembic 1.18.4
- uv