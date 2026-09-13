# Ventus deployment

Upstream recipe: `85305680fb0f8ebc72b7b8ebf49ba54471019285`.
EXL3 weights: `64ba41b6c916a587db06eae2e19b7845f7be6e6b`.
Native Engram: `dba1be0a40aa45a94ad051997016db3960a90277`.

The fleet profile uses local NVMe, TP2 over `10.10.10.0/24`, port 8000,
600000 context, two sequences, DSpark k=3, and text-only input.
The 1.5 GiB memory watchdog is enabled during initial validation.

Allow about 480 GiB per node for EXL3 weights, original Engram and packed
rank files, plus the image and caches. The backend still opens the original
Engram shards even when packed files are present.

Generate `.env` by sourcing `.env.example`, then `deploy/gx10.env` (includes
the pinned image digest). Preserve both old Vision-Exp containers stopped
for rollback. Stop the candidate on both nodes before restarting the old
worker, then the old head. Do not run both models concurrently.

Upstream code retains its AGPL/MIT notices. Deployment receipts belong in
ignored `logs/`; this profile does not replace the fleet registry.

## GX10 deployment, 2026-09-13

API: `http://192.168.0.101:8000/v1`.
Model ID: `DeepSeek-v4.1-Flash-EXL3`. Vision is disabled in this recipe.

- Full Hub checksums passed on both replicas; packed Engram is rank-local.
- Image config ID on both nodes: `sha256:4cdba4e946da2d19bf5b5a20c6d3a1a4bf421fa4d6db5082f271a986168176cb`.
- GPU EXL3 and Engram-dequantization checks passed on both nodes.
- Ten deployment unit tests and 19 reference-template cases passed.
- Arithmetic/logprobs, structured tools, tool-result replay and Korean copy passed.
- Short streaming sample: 1,024 output tokens, 0.395 s first text,
  approximately 37.65 output tokens/s after first text (temperature 0, thinking off).
- Context probes: 3,060 tokens recalled in 3.72 s; 126,972 in 137.45 s;
  **599,004 in 775.38 s**. Each was followed by a successful fresh streaming
  response. Full-context prefill is slow; the short-prompt decode rate above
  is not a measured 600K-context decode rate.
- Pi and OMP selected this model at 600K, text-only. Both passed real CLI
  read-tool requests with thinking off and high.

`deploy/accept.py --fleet-scripts PATH --context N` reuses the fleet needle
probe. `--benchmark` measures short-prompt streaming output. These are operational probes,
not model-quality benchmarks. Per-run receipts are in `logs/accept-*.jsonl`.

Normal startup is `bash start.sh` on the head. The legacy fleet user service
remains runtime-masked; this experiment does not change reboot selection in
`gx10-fleet/fleet.yaml`. Do not unmask it while the candidate owns port 8000.

The launcher space guard now estimates pending rsync replacements, rather
than requiring a second full copy beside already verified replicas. Shell
files are LF-enforced. No inference-kernel changes were made here.

For interrupted GHCR pulls, `deploy/fetch_image.py` checks the manifest and
every blob SHA-256, loads a Docker archive, verifies the config ID, then registers
the original registry digest. The one-time import copies (about 18 GiB) were
removed after both image installs; they can be downloaded again.

## AIDE client

Generate its existing `fleet-model.env` with `deploy/render_aide_env.py
--fleet-scripts PATH --output PATH`, then use AIDE's supported Compose deployment.
This reuses `fleetctl.client_env_lines` with the explicit experiment client YAML;
it does not promote this model or edit the fleet's boot selection. Preserve the
previous generated file for rollback. Temperature stays 0.6; context is 600K
and stall timeout is 900 seconds, covering the measured full-context prefill.

Requires AIDE's opt-in `deepseek-v41-chat-template` dialect (PR #49): the older
adapter sends `reasoning_effort=off`, which this server rejects with HTTP 400.
The new mapping uses `enable_thinking=false` for low/minimal and valid effort
values for all levels. Older model and cloud adapters are unchanged.
