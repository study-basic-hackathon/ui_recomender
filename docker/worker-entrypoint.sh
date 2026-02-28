#!/bin/bash
set -e

echo "=== Worker Starting ==="
echo "Mode: ${WORKER_MODE}"
echo "Session: ${SESSION_ID} Iter: ${ITERATION_INDEX}"
echo "Repository: ${REPO_URL}"

if [ -z "$WORKER_MODE" ]; then
  echo "Error: WORKER_MODE is required (analyze, implement, or createpr)"
  exit 1
fi

case "$WORKER_MODE" in
  analyze)
    exec python /usr/local/bin/worker-analyze.py
    ;;
  implement)
    exec python /usr/local/bin/worker-implement.py
    ;;
  createpr)
    exec python /usr/local/bin/worker-createpr.py
    ;;
  *)
    echo "Error: Unknown WORKER_MODE: $WORKER_MODE"
    exit 1
    ;;
esac
