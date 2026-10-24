#!/usr/bin/env bash
# Serve cog-qwen's pinned model on the GPU, mirroring cog-qwen's
# `pixi run serve-model` (scripts/model.py serve): the same checksum check,
# model file, alias, loopback port, context size, chat template options and
# backend token. Two differences: the llama.cpp build (CUDA instead of cpu_mkl),
# and a 3,000-token cap on Qwen's thinking. Normal thinking stayed under 2,400
# tokens in our tests; at temperature 0 it sometimes loops until the output
# limit, and the cap makes it stop and answer instead (19 Oct 2026).
# Run with COG_QWEN_BACKEND_TOKEN set (source ~/.config/cog-qwen.env).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
qwen=$(cd "$here/../cog-qwen" && pwd)

# The pinned weights' size and sha256, checked by cog-qwen's own code.
(cd "$qwen" && pixi run --quiet python scripts/model.py check) | grep -q '"ok": true' \
  || { echo "cog-qwen's model check failed" >&2; exit 1; }

token=${COG_QWEN_BACKEND_TOKEN:-}
if [ ${#token} -lt 32 ] || [[ $token == *$'\n'* || $token == *$'\r'* ]]; then
  echo "Set COG_QWEN_BACKEND_TOKEN to a random token of at least 32 characters." >&2
  exit 1
fi

# As in model.py: a minimal environment, and the key passed as LLAMA_API_KEY,
# never on the command line.
exec env -i PATH="$PATH" HOME="$HOME" LANG="${LANG:-C.UTF-8}" LLAMA_API_KEY="$token" \
  "$here/.pixi/envs/default/bin/llama-server" \
  --model "$qwen/models/model.gguf" --alias qwen3-4b-q4_k_m \
  --host 127.0.0.1 --port 8080 --ctx-size 8192 --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --reasoning-budget 3000 --reasoning-budget-message "Time to give the answer now."
