#!/bin/bash
set -e

CLUSTER_NAME="ui-recommender"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== UI Recommender - Local Kubernetes Setup ==="

# Check prerequisites
echo "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "Error: docker is not installed"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl is not installed"; exit 1; }
command -v kind >/dev/null 2>&1 || { echo "Error: kind is not installed"; exit 1; }

# Check if cluster already exists
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "Cluster '${CLUSTER_NAME}' already exists."
  read -p "Do you want to delete and recreate it? (y/N): " -r
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Deleting existing cluster..."
    kind delete cluster --name="${CLUSTER_NAME}"
  else
    echo "Using existing cluster."
    kubectl cluster-info --context "kind-${CLUSTER_NAME}"
    exit 0
  fi
fi

# Create kind cluster
echo "Creating kind cluster..."
kind create cluster --config="${PROJECT_ROOT}/k8s/kind-config.yaml"

# Wait for cluster to be ready
echo "Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s

# Create shared artifact directory
echo "Creating shared artifact directory..."
mkdir -p /tmp/ui-recommender-artifacts

# Build worker image
echo "Building worker Docker image..."
cd "${PROJECT_ROOT}"
docker build -f docker/worker.Dockerfile -t ui-recommender-worker:latest .

# Load image into kind
echo "Loading worker image into kind cluster..."
kind load docker-image ui-recommender-worker:latest --name="${CLUSTER_NAME}"

# Create K8s secret for Anthropic API key
if [ -n "$ANTHROPIC_API_KEY" ]; then
  echo "Creating K8s secret for Anthropic API key..."
  kubectl create secret generic ui-recommender-secrets \
    --from-literal=anthropic-api-key="$ANTHROPIC_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
else
  echo "Warning: ANTHROPIC_API_KEY not set. Run the following to set it later:"
  echo "  kubectl create secret generic ui-recommender-secrets --from-literal=anthropic-api-key=YOUR_KEY"
fi

echo ""
echo "=== Setup Complete ==="
echo "Cluster name: ${CLUSTER_NAME}"
echo "Context: kind-${CLUSTER_NAME}"
echo "Artifact dir: /tmp/ui-recommender-artifacts"
echo ""
echo "Useful commands:"
echo "  kubectl get nodes"
echo "  kubectl get pods -A"
echo "  kubectl get secrets"
echo "  kind delete cluster --name=${CLUSTER_NAME}"
echo ""
