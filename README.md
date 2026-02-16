# UI Recommender

既存GitHubリポジトリからAIがUIデザインを複数生成し、ユーザーに提案、選ばれた案のPRを作成する。

## 構成

```
frontend/   # React + Vite
backend/    # FastAPI + Postgres (Orchestrator)
docker/     # Dockerfiles (orchestrator, worker)
k8s/        # Kubernetes manifests
scripts/    # Development scripts
```

セットアップ方法は `frontend/README.md` および `backend/README.md` を参照。
