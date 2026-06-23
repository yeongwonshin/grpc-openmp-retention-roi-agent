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
        "elapsed_ms": elapsed_ms,
        "distributed_used": bool(distributed.get("used", False)),
        "parallel_kernel": distributed.get("parallel_kernel", "unknown"),
        "worker_elapsed_ms": distributed.get("elapsed_ms"),
    }


def run_case(label: str, api_base_url: str, concurrency: int, requests: int, budget: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_post_optimize, api_base_url, budget, timeout) for _ in range(requests)]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                failures += 1
                results.append({"ok": False, "error": str(exc), "elapsed_ms": timeout * 1000.0})
    elapsed_s = time.perf_counter() - started
    successes = [row for row in results if row.get("ok")]
    latencies = [float(row["elapsed_ms"]) for row in results]
    worker_latencies = [float(row["worker_elapsed_ms"]) for row in successes if row.get("worker_elapsed_ms") is not None]
    return {
        "mode": label,
        "api_base_url": api_base_url,
        "concurrency": concurrency,
        "requests": requests,
        "successes": len(successes),
        "failures": failures,
        "elapsed_s": round(elapsed_s, 6),
        "throughput_requests_per_s": round(len(successes) / elapsed_s if elapsed_s else 0.0, 6),
        "avg_latency_ms": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "p95_latency_ms": round(_percentile(latencies, 95), 6) if latencies else 0.0,
        "avg_worker_elapsed_ms": round(statistics.mean(worker_latencies), 6) if worker_latencies else 0.0,
        "distributed_successes": sum(1 for row in successes if row.get("distributed_used")),
        "parallel_kernels": ";".join(sorted({str(row.get("parallel_kernel")) for row in successes if row.get("parallel_kernel")})),
    }


def _plot_bars(rows: list[dict[str, Any]], metric: str, title: str, ylabel: str, output: Path) -> None:
    labels = [row["mode"] for row in rows]
    values = [float(row[metric]) for row in rows]
    plt.figure(figsize=(8.0, 5.0))
    plt.bar(labels, values)
    plt.title(title, fontweight="bold")
    plt.xlabel("mode", fontweight="bold")
    plt.ylabel(ylabel, fontweight="bold")
    for idx, value in enumerate(values):
        plt.text(idx, value, f"{value:.2f}", ha="center", va="bottom", fontweight="bold")
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "distributed_on_off_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "distributed_on_off_comparison.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _plot_bars(rows, "throughput_requests_per_s", "Distributed On/Off Throughput", "requests/s", output_dir / "distributed_on_off_throughput.png")
    _plot_bars(rows, "p95_latency_ms", "Distributed On/Off P95 Latency", "milliseconds", output_dir / "distributed_on_off_p95_latency.png")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare distributed gRPC+OpenMP mode against local/in-process mode. "
            "Run two stacks or two API ports and pass both URLs."
        )
    )
    parser.add_argument("--distributed-url", default="http://localhost:8000", help="API URL with RETENTION_DISTRIBUTED_ENGINE=on")
    parser.add_argument("--local-url", default=None, help="API URL with RETENTION_DISTRIBUTED_ENGINE=off")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--budget", type=int, default=50_000_000)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output-dir", type=Path, default=Path("results_distributed") / "distributed_on_off")
    args = parser.parse_args()

    cases = [("distributed_grpc_openmp", args.distributed_url)]
    if args.local_url:
        cases.append(("local_in_process", args.local_url))

    rows = [run_case(label, url, args.concurrency, args.requests, args.budget, args.timeout) for label, url in cases]
    write_outputs(rows, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "rows": rows}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
