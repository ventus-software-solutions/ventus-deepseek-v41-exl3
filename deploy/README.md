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

Generate `.env` by sourcing `.env.example`, then `deploy/gx10.env`, then
the verified image digest. Preserve both old Vision-Exp containers stopped
for rollback. Stop the candidate on both nodes before restarting the old
worker, then the old head. Do not run both models concurrently.

Upstream code retains its AGPL/MIT notices. Deployment receipts belong in
ignored `logs/`; this profile does not replace the fleet registry.
