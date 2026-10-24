#!/usr/bin/env bash
# Restart the local model server detached (serve.sh, or the script given), and
# wait until it answers. Run from its own process so the pattern below can't
# match the caller's command line.
set -u
here=$(cd "$(dirname "$0")" && pwd)
script=${1:-$here/serve.sh}
source ~/.config/cog-qwen.env; export PATH="$HOME/.pixi/bin:$PATH"
pkill -f "llama-cuda/.pixi/envs/default/bin/llama-server"; sleep 5
setsid nohup "$script" > "$here/logs/model-server.log" 2>&1 < /dev/null &
sleep 3
for i in $(seq 1 100); do
  curl -sf -m 2 -o /dev/null -H "Authorization: Bearer $COG_QWEN_BACKEND_TOKEN" http://127.0.0.1:8080/v1/models && { echo "model server ready"; exit 0; }
  sleep 3
done
echo "model server did not become ready" >&2; exit 1
