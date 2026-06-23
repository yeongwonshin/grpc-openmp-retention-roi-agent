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


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    rank = (len(values) - 1) * pct / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    weight = rank - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _parse_levels(raw: str) -> list[int]:
    levels = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not levels:
        raise ValueError("at least one concurrency level is required")
    return levels


def _post_optimize(api_base_url: str, budget: int, timeout: float) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/api/v1/pipeline/optimize"
    started = time.perf_counter()
    response = requests.post(
        url,
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
        "parallel_kernel": distributed.get("parallel_kernel", "unknown"),
        "worker_elapsed_ms": distributed.get("elapsed_ms"),
        "client_worker_elapsed_ms": distributed.get("client_elapsed_ms"),
    }


def _healthcheck(api_base_url: str, timeout: float) -> None:
    url = f"{api_base_url.rstrip('/')}/health"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()


def run_concurrency_level(
    api_base_url: str,
    concurrency: int,
    requests_per_level: int,
    budget: int,
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_post_optimize, api_base_url, budget, timeout) for _ in range(requests_per_level)]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # keep failed requests visible in the reportable CSV
                failures += 1
                results.append({"ok": False, "error": str(exc), "elapsed_ms": timeout * 1000.0})

    elapsed_s = time.perf_counter() - started
    latencies = [float(row["elapsed_ms"]) for row in results]
    successes = [row for row in results if row.get("ok")]
    worker_latencies = [float(row["worker_elapsed_ms"]) for row in successes if row.get("worker_elapsed_ms") is not None]
    kernels = sorted({str(row.get("parallel_kernel")) for row in successes if row.get("parallel_kernel")})

    return {
        "concurrency": concurrency,
        "requests": requests_per_level,
        "successes": len(successes),
        "failures": failures,
        "elapsed_s": round(elapsed_s, 6),
        "throughput_requests_per_s": round(len(successes) / elapsed_s if elapsed_s else 0.0, 6),
        "avg_latency_ms": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 6) if latencies else 0.0,
        "p95_latency_ms": round(_percentile(latencies, 95), 6) if latencies else 0.0,
        "avg_worker_elapsed_ms": round(statistics.mean(worker_latencies), 6) if worker_latencies else 0.0,
        "distributed_successes": sum(1 for row in successes if row.get("distributed_used")),
        "parallel_kernels": ";".join(kernels),
    }


def _plot_line(rows: list[dict[str, Any]], x: str, y: str, title: str, ylabel: str, output: Path) -> None:
    plt.figure(figsize=(8.0, 5.0))
    plt.plot([row[x] for row in rows], [row[y] for row in rows], marker="o", linewidth=2.2)
    plt.title(title, fontweight="bold")
    plt.xlabel(x.replace("_", " "), fontweight="bold")
    plt.ylabel(ylabel, fontweight="bold")
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "api_concurrency_scaling.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    (output_dir / "api_concurrency_scaling.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _plot_line(rows, "concurrency", "throughput_requests_per_s", "API Throughput vs Concurrent Requests", "requests/s", output_dir / "api_throughput_vs_concurrency.png")
    _plot_line(rows, "concurrency", "p95_latency_ms", "API P95 Latency vs Concurrent Requests", "milliseconds", output_dir / "api_p95_latency_vs_concurrency.png")
    _plot_line(rows, "concurrency", "avg_latency_ms", "API Average Latency vs Concurrent Requests", "milliseconds", output_dir / "api_avg_latency_vs_concurrency.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark API-level throughput and latency under concurrent requests.")
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--concurrency-levels", default="1,2,4,8")
    parser.add_argument("--requests-per-level", type=int, default=12)
    parser.add_argument("--budget", type=int, default=50_000_000)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output-dir", type=Path, default=Path("results_distributed") / "api_scaling")
    parser.add_argument("--skip-healthcheck", action="store_true")
    args = parser.parse_args()

    if not args.skip_healthcheck:
        _healthcheck(args.api_base_url, min(args.timeout, 10.0))

    rows = [
        run_concurrency_level(args.api_base_url, level, args.requests_per_level, args.budget, args.timeout)
        for level in _parse_levels(args.concurrency_levels)
    ]
    write_outputs(rows, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "rows": rows}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
