"""Statistical analysis for latency samples (percentiles, jitter, CV)."""

from __future__ import annotations

import math
from typing import Sequence


def percentile_sorted(sorted_samples: Sequence[float], p: float) -> float:
    if not sorted_samples:
        return float("nan")
    if p <= 0:
        return float(sorted_samples[0])
    if p >= 100:
        return float(sorted_samples[-1])
    k = (len(sorted_samples) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_samples[int(k)])
    d0 = sorted_samples[f] * (c - k)
    d1 = sorted_samples[c] * (k - f)
    return float(d0 + d1)


def summarize_ns(samples_ns: Sequence[float]) -> dict[str, float]:
    """Return summary statistics for RTT samples in nanoseconds."""
    if not samples_ns:
        return {
            "count": 0.0,
            "mean_ns": float("nan"),
            "std_ns": float("nan"),
            "jitter_ns": float("nan"),
            "cv": float("nan"),
            "min_ns": float("nan"),
            "max_ns": float("nan"),
            "p50_ns": float("nan"),
            "p90_ns": float("nan"),
            "p99_ns": float("nan"),
            "p999_ns": float("nan"),
        }

    xs = sorted(float(x) for x in samples_ns)
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n
    std = math.sqrt(var)

    return {
        "count": float(n),
        "mean_ns": mean,
        "std_ns": std,
        "jitter_ns": std,
        "cv": std / mean if mean > 0 else float("nan"),
        "min_ns": xs[0],
        "max_ns": xs[-1],
        "p50_ns": percentile_sorted(xs, 50),
        "p90_ns": percentile_sorted(xs, 90),
        "p99_ns": percentile_sorted(xs, 99),
        "p999_ns": percentile_sorted(xs, 99.9),
    }


def inter_arrival_jitter_ns(timestamps_ns: Sequence[int]) -> dict[str, float]:
    """RFC-style inter-arrival jitter estimate for ordered event timestamps."""
    if len(timestamps_ns) < 3:
        return {"mean_delta_ns": float("nan"), "jitter_ia_ns": float("nan")}
    ts = sorted(int(t) for t in timestamps_ns)
    deltas = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    if not deltas:
        return {"mean_delta_ns": float("nan"), "jitter_ia_ns": float("nan")}
    mean_d = sum(deltas) / len(deltas)
    var = sum((d - mean_d) ** 2 for d in deltas) / len(deltas)
    return {"mean_delta_ns": mean_d, "jitter_ia_ns": math.sqrt(var)}
