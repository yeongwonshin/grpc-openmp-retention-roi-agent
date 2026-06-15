from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from src.distributed.grpc_json import call_json

FEATURE_METHOD = "/retention_roi.FeatureService/ExtractFeatures"
ROI_METHOD = "/retention_roi.RoiService/ScoreRoi"


def distributed_enabled() -> bool:
    return os.getenv("RETENTION_DISTRIBUTED_ENGINE", "on").strip().lower() in {"1", "true", "yes", "on", "distributed"}


def feature_worker_address() -> str:
    return os.getenv("RETENTION_FEATURE_WORKER_ADDRESS", "feature-worker:50051")


def roi_worker_address() -> str:
    return os.getenv("RETENTION_ROI_WORKER_ADDRESS", "roi-worker:50052")


def openmp_threads() -> int:
    raw = os.getenv("RETENTION_OPENMP_THREADS", "4")
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def grpc_timeout_seconds() -> float:
    raw = os.getenv("RETENTION_GRPC_TIMEOUT_SECONDS", "180")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 180.0


def extract_customer_features(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run uploaded/customer events through the gRPC feature stage.

    The dashboard upload path uses this as a platform feature, not only as a
    benchmark helper.  It keeps the existing ingestion pipeline intact and adds a
    distributed feature materialization stage when workers are available.
    """
    if events.empty:
        return pd.DataFrame(), {"ok": True, "stage": "feature_worker", "rows_in": 0, "rows_out": 0}

    payload = {"events": events.to_dict(orient="records")}
    response = call_json(feature_worker_address(), FEATURE_METHOD, payload, timeout=grpc_timeout_seconds())
    if not response.get("ok", False):
        raise RuntimeError(response.get("error") or "feature worker failed")
    return pd.DataFrame(response.get("features", [])), response


def score_roi_candidates(candidates: pd.DataFrame, *, top_n: int | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score ROI candidates through the gRPC ROI worker and OpenMP kernel."""
    required = ["customer_id", "churn_probability", "uplift_score", "clv", "coupon_cost"]
    missing = [column for column in required if column not in candidates.columns]
    if missing:
        raise ValueError(f"distributed ROI scoring missing columns: {missing}")

    features = candidates[required].copy()
    for column in ["churn_probability", "uplift_score", "clv", "coupon_cost"]:
        features[column] = pd.to_numeric(features[column], errors="coerce").fillna(0.0)

    payload = {
        "features": features.to_dict(orient="records"),
        "threads": openmp_threads(),
        "top_n": int(top_n or min(len(features), 100)),
    }
    started = perf_counter()
    response = call_json(roi_worker_address(), ROI_METHOD, payload, timeout=grpc_timeout_seconds())
    response["client_elapsed_ms"] = (perf_counter() - started) * 1000.0
    if not response.get("ok", False):
        raise RuntimeError(response.get("error") or "ROI worker failed")

    scored = pd.DataFrame(response.get("scored_customers", []))
    return scored, response


def materialize_feature_stage_from_events(events_path: Path, output_path: Path) -> dict[str, Any]:
    """Persist distributed feature-worker output for uploaded datasets."""
    if not distributed_enabled() or not events_path.exists():
        return {"enabled": distributed_enabled(), "skipped": True, "reason": "disabled_or_missing_events"}
    events = pd.read_csv(events_path)
    features, metrics = extract_customer_features(events)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    return {
        "enabled": True,
        "skipped": False,
        "output_path": str(output_path),
        "rows_in": int(metrics.get("rows_in", len(events))),
        "rows_out": int(metrics.get("rows_out", len(features))),
        "elapsed_ms": float(metrics.get("elapsed_ms", 0.0)),
        "middleware": "gRPC",
    }
