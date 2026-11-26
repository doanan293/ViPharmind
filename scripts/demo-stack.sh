#!/usr/bin/env bash
# Local demo stack: Postgres, Qdrant, backend, frontend and nginx, the LLM through the Gemini
# proxy, embedding and reranker on this machine with llama.cpp. Web: http://localhost:8080.
#
#   scripts/demo-stack.sh up        build, start, wait until healthy, import the corpus if missing
#   scripts/demo-stack.sh status    service health
#   scripts/demo-stack.sh logs [S]  logs of every service or of S (e.g. backend)
#   scripts/demo-stack.sh reset-db  drop user data: fresh Postgres and Qdrant, corpus imported again
#   scripts/demo-stack.sh down      stop and remove the containers (volumes stay)
#
# The corpus import only loads the bundle's precomputed vectors; nothing is embedded again.
# Variables: GGUF_DIR, PHARMA_DATA_DIR, DEMO_RERANKER (GGUF file name of the reranker, or none).
set -euo pipefail

cd "$(dirname "$0")/.."

export GGUF_DIR="${GGUF_DIR:-$HOME/personal/vipharmind/ai-models/gguf}"
export PHARMA_DATA_DIR="${PHARMA_DATA_DIR:-$HOME/personal/vipharmind/pharma-lab/data}"
# `none` turns reranking off (hybrid RRF only): on this CPU (about 100 tokens/s for a 0.6B
# model) one rerank round of 15 passages takes minutes, past the 90 s turn deadline.
DEMO_RERANKER="${DEMO_RERANKER:-none}"
if [ "$DEMO_RERANKER" = none ]; then
  export LLAMA_RERANKER_PROTOCOL=none
  DEMO_RERANKER=qwen3-reranker-0.6b-q8_0-vimed.gguf
fi
export LLAMA_RERANKER_MODEL="$DEMO_RERANKER"
# qwen3-reranker-0.6b-q8_0-vimed.gguf -> qwen3-reranker:0.6b-q8_0
name="${DEMO_RERANKER%-vimed.gguf}"
name="${name%.gguf}"
export LLAMA_RERANKER_MODEL_NAME="${name/qwen3-reranker-/qwen3-reranker:}"

PROJECT=vipharmind-demo
compose() {
  docker compose -p "$PROJECT" -f compose.yaml -f compose.llm-proxy.yaml \
    -f compose.local-models.yaml -f compose.demo.yaml "$@"
}

# One-off backend containers: the long-running backend only turns healthy once the corpus exists.
backend_once() {
  compose run --rm --no-deps -T backend "$@"
}

up() {
  compose build
  compose up -d --wait postgres qdrant llama-embedding llama-reranker cli-proxy-api
  backend_once pharma-agent migrate
  if ! backend_once pharma-agent check >/dev/null 2>&1; then
    echo "importing the corpus (precomputed vectors only)"
    backend_once pharma-agent corpus import /data/corpus/formulary --collection formulary --publish
  fi
  compose up -d --wait
  compose exec -T backend pharma-agent check
  echo "ready: http://localhost:${WEB_PORT:-8080}"
}

case "${1:-}" in
  up) up ;;
  status) compose ps --format 'table {{.Service}}\t{{.Status}}' ;;
  logs) shift; compose logs --no-color "$@" ;;
  reset-db)
    compose stop backend frontend nginx
    compose rm -f -s postgres qdrant
    docker volume rm -f "${PROJECT}_postgres_data" "${PROJECT}_qdrant_data" >/dev/null
    up
    ;;
  down) compose down ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
