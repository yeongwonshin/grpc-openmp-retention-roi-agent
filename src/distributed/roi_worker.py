from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import tempfile
from concurrent import futures
from pathlib import Path
from time import perf_counter
from typing import Any

import grpc
import numpy as np
import pandas as pd

from src.distributed.grpc_json import unary_json_handler

LOGGER = logging.getLogger("retention_roi.roi_worker")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KERNEL = PROJECT_ROOT / "build" / "openmp_roi"


def _fallback_numpy(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    retained_value = df["uplift_score"] * df["churn_probability"] * df["clv"]
    risk_penalty = 0.08 * df["churn_probability"] * df["coupon_cost"]
    df["expected_incremental_profit"] = retained_value - df["coupon_cost"] - risk_penalty
    df["expected_roi"] = np.where(df["coupon_cost"] > 0, df["expected_incremental_profit"] / df["coupon_cost"], 0.0)
    return df


def score_roi(payload: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    threads = int(payload.get("threads", 4))
    kernel = Path(payload.get("kernel_path") or DEFAULT_KERNEL)
    features = pd.DataFrame(payload.get("features", []))
    required = ["customer_id", "churn_probability", "uplift_score", "clv", "coupon_cost"]
    missing = [c for c in required if c not in features.columns]
    if missing:
        raise ValueError(f"features missing required columns: {missing}")
    features = features[required].copy()

    kernel_used = "numpy-fallback"
    if kernel.exists() and shutil.which(str(kernel)):
        with tempfile.TemporaryDirectory(prefix="retention_roi_omp_") as tmp:
            tmpdir = Path(tmp)
            in_csv = tmpdir / "features.csv"
            out_csv = tmpdir / "scored.csv"
            features.to_csv(in_csv, index=False)
            subprocess.run([str(kernel), str(in_csv), str(out_csv), str(threads)], check=True, capture_output=True, text=True)
            scored = pd.read_csv(out_csv)
            kernel_used = "openmp-cpp"
    elif kernel.exists():
        with tempfile.TemporaryDirectory(prefix="retention_roi_omp_") as tmp:
            tmpdir = Path(tmp)
            in_csv = tmpdir / "features.csv"
            out_csv = tmpdir / "scored.csv"
            features.to_csv(in_csv, index=False)
            subprocess.run([str(kernel), str(in_csv), str(out_csv), str(threads)], check=True, capture_output=True, text=True)
            scored = pd.read_csv(out_csv)
            kernel_used = "openmp-cpp"
    else:
        scored = _fallback_numpy(features)

    scored = scored.sort_values("expected_roi", ascending=False).reset_index(drop=True)
    elapsed_ms = (perf_counter() - started) * 1000.0
    return {
        "ok": True,
        "stage": "roi_worker",
        "rows_in": int(len(features)),
        "rows_out": int(len(scored)),
        "elapsed_ms": elapsed_ms,
        "threads": threads,
        "parallel_kernel": kernel_used,
        "top_customers": scored.head(int(payload.get("top_n", 20))).to_dict(orient="records"),
        "scored_customers": scored.to_dict(orient="records"),
    }


def serve(host: str = "0.0.0.0", port: int = 50052, max_workers: int = 4) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    handler = grpc.method_handlers_generic_handler(
        "retention_roi.RoiService",
        {"ScoreRoi": unary_json_handler(score_roi)},
    )
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    LOGGER.info("ROI worker listening on %s:%s", host, port)
    server.wait_for_termination()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the gRPC ROI scoring worker backed by an OpenMP kernel.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50052)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(args.host, args.port, args.max_workers)
