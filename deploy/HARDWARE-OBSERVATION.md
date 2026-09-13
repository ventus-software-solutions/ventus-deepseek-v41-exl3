# Hardware observation — V4.1 EXL3 TP2

Started 2026-09-13 12:22 UTC. Initial assessment, not a lifetime guarantee.
AIDE is on the tested V4.1 adapter at `b67fdc68a`, 600K context; leave autonomy
paused. The operator will supply work. Do not synthesize load or change serving.
Archive originals under `E:/model-archive` are immutable sources; no experiments,
monitoring output, writable mounts or writable hardlinks there.

## Initial findings

| Signal | gx10-1 | gx10-2 |
|---|---:|---:|
| GPU temperature, first idle snapshot | 39 C | 40 C |
| SSD composite temperature, subsequent snapshot | 35.85 C | 38.85 C |
| Available unified memory | about 6.3 GiB | about 7.3 GiB |
| Swap occupied | about 3.6 GiB | about 3.1 GiB |
| Memguard observed low-water | 5,576 MiB | 7,428 MiB |
| SSD filesystem space available | 114.94 GB | 150.43 GB |
| SSD writes, approx. 11:50–12:20 UTC | 180.03 KiB/s | 16.40 KiB/s |
| SSD reads, same interval | 28,215.78 KiB/s | 28,208.68 KiB/s |

`sar -W` recorded 0.00 swap-out pages/s for the three intervals ending around
12:00, 12:10 and 12:20 UTC on both nodes. Startup did swap pages out; occupied
swap alone does not prove continuing thrashing. Both hosts use 4,096-byte pages.
Times printed by sar/journal default to CEST (UTC+2); record UTC explicitly.

Both kernels logged one `NV_ERR_NO_MEMORY` allocation failure at 11:40:55–57 UTC,
during loading, before the server became ready. This is a runtime warning, not
evidence of damaged hardware. No Xid, NVMe I/O/reset/timeout errors or kernel OOM
kills matched the inspected window. Watch for recurrence rather than hiding it.

No active GPU thermal throttling in the snapshots. GPU cumulative thermal
counters: head SW/HW=0/0 us; worker SW/HW=326136/0 us. Worker SW history predates
this observation and cannot be attributed to this model. Power-cap counters are
not equivalent to thermal faults. NVIDIA T.Limit is remaining thermal margin,
not an absolute safe temperature. Memory junction temperature is unavailable.
SSD sysfs composite max/critical thresholds: 82.85/84.85 C; sensor-2 max is an
obviously invalid 65261.85 C and must not be used. NIC sensors were 43–47 C.

## Mechanism and limits

The live image's `/opt/dsv41/row_store.cpp` matches the checkout after LF
normalization (SHA256 `79c3747f7c4bdf6f5a552dea146620f4d5b9f92f128ee74b820c89d2dab60505`).
It uses `O_RDONLY` and `pread` for Engram; writable caches are anonymous RAM.
Packing creates separate SSD files once. Runtime reads do not rewrite the
whole model per token. Other processes, logs, swap and SSD internal maintenance
can still cause writes. Host block counters are not NAND program/erase counts.

Sustained AI workloads are an intended use of GX10, but cooling, component aging
and SSD endurance still matter. The principal avoidable risks here are sustained
thermal stress, swap/write amplification and exhausted memory/free space.
Quantization itself is a numerical representation, not an overvoltage operation.
No clock, power, fan or firmware limits were changed for this assessment.

The observed write rates are mixed idle/test-system totals, not attributed solely
to AIDE or representative of continuous future load. Do not extrapolate SSD years
remaining from this short interval. Exact SSD model: `ESL01TBTLCZ-27J2-TYN`; an
authoritative endurance/TBW rating has not been established.

SMART reads need administrator credentials unavailable to this session. On each
GX10, the operator can run this read-only command (no self-test or writes):

```sh
sudo smartctl -a -j /dev/nvme0
```

Capture critical warning, available spare/threshold, percentage used, host writes,
media errors, error-log entries, unsafe shutdowns and thermal-warning time.
Compare counter deltas, including power-on hours, rather than historical totals.

## Observation procedure

Reuse installed sysstat history (`/var/log/sysstat/saDD`), `/proc` and `/sys`,
NVIDIA counters, kernel journal, vLLM metrics and the existing memguards.
No additional daemon, packages, stress test, model request, server restart or
global permission change is necessary. Small receipts live in ignored
`logs/hardware-observation/`, outside the model archive.

Every 15 minutes for the first 24 hours, correlate AIDE busy/effectiveProvider
with server request/token counter deltas, GPU thermal counters, memory pressure,
swap-in/out, SSD reads/writes/latency/free space and new kernel errors. Requests
from other clients or AIDE background maintenance are not proof of AIDE task work.
Sampled temperatures can miss peaks; thermal counter deltas improve coverage.

Separate boot/loading, prefill, decode and idle when evidence supports it. Do not
call an idle interval a load test. Preserve user pause and existing guard behavior.
Alert on new hardware/media errors, critical temperature/warning indicators,
repeated thermal throttling, guard kills or persistent swap/write pressure.
Use 3 GiB available RAM and 30 GiB free disk as conservative operator warning
thresholds, not manufacturer damage limits; existing memguard remains at 1.5 GiB.
Notify meaningful findings, not unchanged snapshots. Report after representative
work is observed and after 24 hours; if still idle, report insufficient exposure.
No automatic configuration changes or additional shutdown actions are authorized.

Counter baseline at 2026-09-13 12:26:26 UTC:

| Host | Boot ID | SSD read sectors | SSD written sectors | pswpin | pswpout |
|---|---|---:|---:|---:|---:|
| gx10-1 | dab657f6-4d12-438b-9fc2-0c01e33eecf2 | 3738770566 | 2819721250 | 2464237 | 4497307 |
| gx10-2 | b6f57f32-363e-495c-867f-0dcd0dc0e4e0 | 2836906246 | 2179419442 | 1394130 | 3345859 |

Block sectors are 512 bytes. In `/sys/class/block/nvme0n1/stat`, read/written
sectors are fields 3/7 (one-based). Do not sum the whole disk and partitions.
Reset comparisons on boot/device/counter reset. SMART data units use a different
scale: do not interpret them as these block sectors.

## Primary references

- [ASUS GX10 intended workloads and cooling](https://press.asus.com/news/press-releases/asus-ascent-gx10-ai-supercomputer/)
- [NVM Express SSD endurance and health indicators](https://nvmexpress.org/how-ssds-fail-nvme-ssd-management-error-reporting-and-logging-capabilities/)
- [NVIDIA thermal margins and throttling counters](https://docs.nvidia.com/deploy/nvidia-smi/)
- [Linux block statistics units](https://cdn.kernel.org/doc/html/latest/block/stat.html)
