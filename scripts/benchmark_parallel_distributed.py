from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import requests


def _post_optimize(api_base_url: str, budget: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(
        f"{api_base_url.rstrip('/')}/api/v1/pipeline/optimize",
        params={"budget": budget},
        json={"budget": budget, "force_simulation": False},
        timeout=timeout,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    response.raise_for_status()
    body = response.json()
    distributed = body.get("metadata", {}).get("distributed_engine", {})
    return {
        "ok": True,
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "distributed_used": bool(distributed.get("used", False)),
        "parallel_kernel": distributed.get("parallel_kernel"),
        "worker_elapsed_ms": distributed.get("elapsed_ms"),
        "client_worker_elapsed_ms": distributed.get("client_elapsed_ms"),
    }


def _plot(rows: list[dict[str, Any]], x: str, y: str, title: str, output: Path) -> None:
    plt.figure(figsize=(7.5, 4.8))
    plt.plot([row[x] for row in rows], [row[y] for row in rows], marker="o")
    plt.title(title)
    plt.xlabel(x.replace("_", " "))
    plt.ylabel(y.replace("_", " "))
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(output, dpi=160)
    plt.close()


def run_level(api_base_url: str, concurrency: int, requests_per_level: int, budget: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [_post_future(pool, api_base_url, budget, timeout) for _ in range(requests_per_level)]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                failures += 1
                results.append({"ok": False, "error": str(exc), "elapsed_ms": timeout * 1000.0})
    elapsed_s = time.perf_counter() - started
    latencies = [float(row["elapsed_ms"]) for row in results]
    successes = [row for row in results if row.get("ok")]
    return {
        "concurrency": concurrency,
        "requests": requests_per_level,
        "successes": len(successes),
        "failures": failures,
        "elapsed_s": round(elapsed_s, 6),
        "throughput_requests_per_s": round(len(successes) / elapsed_s if elapsed_s else 0.0, 6),
        "avg_latency_ms": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "p95_latency_ms": round(_percentile(latencies, 95), 6) if latencies else 0.0,
        "distributed_successes": sum(1 for row in successes if row.get("distributed_used")),
        "parallel_kernels": sorted({str(row.get("parallel_kernel")) for row in successes if row.get("parallel_kernel")}),
    }


def _post_future(pool: ThreadPoolExecutor, api_base_url: str, budget: int, timeout: float):
    return pool.submit(_post_optimize, api_base_url, budget, timeout)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    rank = (len(values) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    weight = rank - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the integrated dashboard API path behind the load balancer.")
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("results_distributed") / "platform_benchmark")
    parser.add_argument("--concurrency-levels", default="1,2,4,8")
    parser.add_argument("--requests-per-level", type=int, default=8)
    parser.add_argument("--budget", type=int, default=50_000_000)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    levels = [int(item) for item in args.concurrency_levels.split(",") if item.strip()]
    rows = [run_level(args.api_base_url, level, args.requests_per_level, args.budget, args.timeout) for level in levels]

    csv_path = args.output_dir / "platform_scaling.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    _plot(rows, "concurrency", "throughput_requests_per_s", "Dashboard API Throughput vs Concurrent Requests", args.output_dir / "throughput_vs_concurrency.png")
    _plot(rows, "concurrency", "p95_latency_ms", "Dashboard API P95 Latency vs Concurrent Requests", args.output_dir / "p95_latency_vs_concurrency.png")
    summary = {"rows": len(rows), "output_dir": str(args.output_dir), "csv": str(csv_path)}
    (args.output_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
