#!/usr/bin/env bash
# Phase 1 for one model on a single GPU node with offline vLLM.
#   MODEL=Qwen/Qwen3-4B NAME=qwen3-4b bash scripts/run_qwen3_4b.sh
# Run it again with MODEL=Qwen/Qwen3-32B NAME=qwen3-32b for the reference model.
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${MODEL:-Qwen/Qwen3-4B}
NAME=${NAME:-qwen3-4b}
SAMPLES=${SAMPLES:-10}

python -m persist generate --out data/tasks.jsonl
python -m persist sanity --out results/sanity
python -m persist probe   --backend vllm --model "$MODEL" --name "$NAME" --samples "$SAMPLES" --out "results/probe_$NAME"
python -m persist rollout --backend vllm --model "$MODEL" --name "$NAME" --repeats 2 --out "results/rollout_$NAME"
