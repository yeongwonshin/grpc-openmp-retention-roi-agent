from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ELAPSED_RE = re.compile(r"elapsed_ms=([0-9.]+)")


def _parse_levels(raw: str) -> list[int]:
    levels = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not levels:
        raise ValueError("at least one thread level is required")
    return levels


def build_kernel(project_root: Path) -> Path:
    script = project_root / "scripts" / "build_openmp_roi.sh"
    subprocess.run(["bash", str(script)], cwd=project_root, check=True)
    kernel = project_root / "build" / "openmp_roi"
    if not kernel.exists():
        raise FileNotFoundError(f"OpenMP kernel was not built: {kernel}")
    return kernel


def generate_features_csv(output_path: Path, rows: int, seed: int) -> None:
    rng = random.Random(seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["customer_id", "churn_probability", "uplift_score", "clv", "coupon_cost"])
        for idx in range(rows):
            churn = min(0.98, max(0.01, rng.betavariate(2.2, 4.8)))
            uplift = min(0.35, max(0.01, 0.025 + 0.22 * churn + rng.gauss(0.0, 0.018)))
            clv = max(20.0, rng.lognormvariate(math.log(180.0), 0.85))
            coupon = min(75.0, max(3.0, 4.0 + 0.015 * clv + 2.0 * churn))
            writer.writerow([f"C{idx:09d}", f"{churn:.8f}", f"{uplift:.8f}", f"{clv:.8f}", f"{coupon:.8f}"])


def run_kernel(kernel: Path, input_csv: Path, output_csv: Path, threads: int, project_root: Path) -> float:
    completed = subprocess.run(
        [str(kernel), str(input_csv), str(output_csv), str(threads)],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    match = ELAPSED_RE.search(completed.stderr or "")
    if not match:
        raise RuntimeError(f"cannot parse elapsed_ms from kernel stderr: {completed.stderr}")
    return float(match.group(1))


def run_thread_level(
    kernel: Path,
    input_csv: Path,
    output_dir: Path,
    threads: int,
    rows: int,
    repetitions: int,
    project_root: Path,
) -> dict[str, Any]:
    elapsed_values = []
    for rep in range(repetitions):
        output_csv = output_dir / f"scored_threads_{threads}_rep_{rep + 1}.csv"
        elapsed_values.append(run_kernel(kernel, input_csv, output_csv, threads, project_root))
    mean_ms = statistics.mean(elapsed_values)
    return {
        "threads": threads,
        "rows": rows,
        "repetitions": repetitions,
        "mean_kernel_elapsed_ms": round(mean_ms, 6),
        "std_kernel_elapsed_ms": round(statistics.pstdev(elapsed_values), 6) if len(elapsed_values) > 1 else 0.0,
        "min_kernel_elapsed_ms": round(min(elapsed_values), 6),
        "max_kernel_elapsed_ms": round(max(elapsed_values), 6),
        "throughput_rows_per_s": round(rows / (mean_ms / 1000.0), 6) if mean_ms > 0 else 0.0,
    }


def _plot_line(rows: list[dict[str, Any]], x: str, y: str, title: str, ylabel: str, output: Path) -> None:
    plt.figure(figsize=(8.0, 5.0))
    plt.plot([row[x] for row in rows], [row[y] for row in rows], marker="o", linewidth=2.2)
    plt.title(title, fontweight="bold")
    plt.xlabel(x, fontweight="bold")
    plt.ylabel(ylabel, fontweight="bold")
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(output, dpi=180)
    plt.close()


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    baseline_ms = float(rows[0]["mean_kernel_elapsed_ms"])
    for row in rows:
        speedup = baseline_ms / float(row["mean_kernel_elapsed_ms"]) if float(row["mean_kernel_elapsed_ms"]) > 0 else 0.0
        row["speedup_vs_1_thread"] = round(speedup, 6)
        row["parallel_efficiency"] = round(speedup / int(row["threads"]), 6)

    csv_path = output_dir / "openmp_thread_scaling.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "openmp_thread_scaling.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _plot_line(rows, "threads", "mean_kernel_elapsed_ms", "OpenMP Kernel Elapsed Time vs Threads", "milliseconds", output_dir / "openmp_elapsed_vs_threads.png")
    _plot_line(rows, "threads", "speedup_vs_1_thread", "OpenMP Kernel Speedup vs Threads", "speedup", output_dir / "openmp_speedup_vs_threads.png")
    _plot_line(rows, "threads", "throughput_rows_per_s", "OpenMP Kernel Throughput vs Threads", "rows/s", output_dir / "openmp_throughput_vs_threads.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the C++ OpenMP ROI kernel with multiple thread counts.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--kernel", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("results_distributed") / "openmp_thread_scaling")
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--threads", default="1,2,4,8")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=414)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    kernel = args.kernel.resolve() if args.kernel else project_root / "build" / "openmp_roi"
    if args.rebuild or not kernel.exists():
        kernel = build_kernel(project_root)

    input_csv = output_dir / f"synthetic_roi_features_{args.rows}.csv"
    generate_features_csv(input_csv, args.rows, args.seed)
    rows = [
        run_thread_level(kernel, input_csv, output_dir, level, args.rows, args.repetitions, project_root)
        for level in _parse_levels(args.threads)
    ]
    write_outputs(rows, output_dir)
    print(json.dumps({"output_dir": str(output_dir), "rows": rows}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
