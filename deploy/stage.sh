#!/usr/bin/env bash
# Stage verified local replicas and packed Engram without changing serving.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .env
mkdir -p logs
exec 9>logs/stage.lock
flock -n 9 || { echo 'another staging process is running'; exit 1; }
trap 'echo "stage failed at line $LINENO"' ERR
status() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
worker() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$WORKER_SSH" "$@"; }

status 'waiting for pinned EXL3 download'
code=$(docker wait ventus-v41-download)
[[ "$code" == 0 ]] || { docker logs --tail 30 ventus-v41-download; exit 1; }
status 'verifying EXL3 snapshot'
python3 deploy/verify_snapshot.py "$MODEL_HOST" "$HF_MODEL_REPO" \
    64ba41b6c916a587db06eae2e19b7845f7be6e6b >logs/exl3-verified.jsonl

status 'waiting for archive Engram copy'
deadline=$((SECONDS + 14400))
while [[ "$(stat -c %s "$ENGRAM_DIR/model-00047-of-00048.safetensors" 2>/dev/null || true)" != 101535150936 ]] \
   || [[ "$(stat -c %s "$ENGRAM_DIR/model-00048-of-00048.safetensors" 2>/dev/null || true)" != 101537926640 ]]; do
    (( SECONDS < deadline )) || { echo 'archive copy timed out'; exit 1; }
    sleep 30
done
status 'verifying original Engram shards'
python3 deploy/verify_snapshot.py "$ENGRAM_DIR" "$HF_ENGRAM_REPO" \
    dba1be0a40aa45a94ad051997016db3960a90277 --files \
    model-00047-of-00048.safetensors model-00048-of-00048.safetensors \
    config.json model.safetensors.index.json >logs/engram-verified.jsonl

status 'distributing local replicas over RoCE link'
worker "mkdir -p '$WORKER_MODEL_DIR' '$WORKER_ENGRAM_DIR' /home/hibbault/ventus-deepseek-v41-exl3/deploy"
rsync -a --partial --exclude='.cache' --exclude='.hf-cache' "$MODEL_HOST/" "$WORKER_SSH:$WORKER_MODEL_DIR/"
rsync -a --partial "$ENGRAM_DIR/" "$WORKER_SSH:$WORKER_ENGRAM_DIR/"
scp -q deploy/verify_snapshot.py "$WORKER_SSH:/home/hibbault/ventus-deepseek-v41-exl3/deploy/"
status 'verifying worker copies'
worker "python3 /home/hibbault/ventus-deepseek-v41-exl3/deploy/verify_snapshot.py '$WORKER_MODEL_DIR' '$HF_MODEL_REPO' 64ba41b6c916a587db06eae2e19b7845f7be6e6b" >logs/worker-exl3-verified.jsonl
worker "python3 /home/hibbault/ventus-deepseek-v41-exl3/deploy/verify_snapshot.py '$WORKER_ENGRAM_DIR' '$HF_ENGRAM_REPO' dba1be0a40aa45a94ad051997016db3960a90277 --files model-00047-of-00048.safetensors model-00048-of-00048.safetensors config.json model.safetensors.index.json" >logs/worker-engram-verified.jsonl

status 'checking immutable image on both nodes'
head_id=$(docker image inspect "$IMAGE" --format '{{.Id}}')
worker_id=$(worker "docker image inspect '$IMAGE' --format '{{.Id}}'")
[[ "$head_id" == "$worker_id" ]] || { echo 'image IDs differ'; exit 1; }
printf '%s\n%s\n' "$IMAGE" "$head_id" >logs/image-pin.txt

status 'packing Engram into local rank files'
mkdir -p "$HEAD_PACKED_DIR"
worker "mkdir -p '$WORKER_PACKED_DIR'"
docker run --rm --name ventus-v41-pack --memory=2g --memory-swap=2g --cpus=2 \
    --user "$(id -u):$(id -g)" -v "$ENGRAM_DIR:/models:ro" -v "$HEAD_PACKED_DIR:/engram" \
    --entrypoint python3 "$IMAGE" /opt/dsv41/pack_engram.py \
    --model /models --rank 0 --tp 2 --out /engram >logs/pack-head.log 2>&1 &
pack_pid=$!
worker "docker run --rm --name ventus-v41-pack --memory=2g --memory-swap=2g --cpus=2 --user 1000:1000 -v '$WORKER_ENGRAM_DIR:/models:ro' -v '$WORKER_PACKED_DIR:/engram' --entrypoint python3 '$IMAGE' /opt/dsv41/pack_engram.py --model /models --rank 1 --tp 2 --out /engram" >logs/pack-worker.log 2>&1 &
worker_pack_pid=$!
wait "$pack_pid"
wait "$worker_pack_pid"
status 'STAGED: verified weights, images and packed Engram on both nodes'
date -u +%FT%TZ >logs/staged.ok
