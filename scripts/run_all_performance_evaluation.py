from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> None:
    print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all project performance experiments in a reproducible sequence.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--local-api-base-url", default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("results_distributed") / "all_experiments")
    parser.add_argument("--api-concurrency-levels", default="1,2,4,8")
    parser.add_argument("--api-requests-per-level", type=int, default=12)
    parser.add_argument("--openmp-rows", type=int, default=200_000)
    parser.add_argument("--openmp-threads", default="1,2,4,8")
    parser.add_argument("--openmp-repetitions", type=int, default=3)
    parser.add_argument("--comparison-concurrency", type=int, default=8)
    parser.add_argument("--comparison-requests", type=int, default=24)
    parser.add_argument("--skip-distributed-comparison", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    out = args.output_dir if args.output_dir.is_absolute() else project_root / args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            "scripts/benchmark_api_scaling.py",
            "--api-base-url",
            args.api_base_url,
            "--concurrency-levels",
            args.api_concurrency_levels,
            "--requests-per-level",
            str(args.api_requests_per_level),
            "--output-dir",
            str(out / "api_scaling"),
        ],
        project_root,
    )

    run(
        [
            sys.executable,
            "scripts/benchmark_openmp_threads.py",
            "--rows",
            str(args.openmp_rows),
            "--threads",
            args.openmp_threads,
            "--repetitions",
            str(args.openmp_repetitions),
            "--rebuild",
            "--output-dir",
            str(out / "openmp_thread_scaling"),
        ],
        project_root,
    )

    if not args.skip_distributed_comparison:
        command = [
            sys.executable,
            "scripts/benchmark_distributed_on_off.py",
            "--distributed-url",
            args.api_base_url,
            "--concurrency",
            str(args.comparison_concurrency),
            "--requests",
            str(args.comparison_requests),
            "--output-dir",
            str(out / "distributed_on_off"),
        ]
        if args.local_api_base_url:
            command.extend(["--local-url", args.local_api_base_url])
        run(command, project_root)

    print(f"\nAll requested experiments completed. Results are under: {out}")


if __name__ == "__main__":
    main()
