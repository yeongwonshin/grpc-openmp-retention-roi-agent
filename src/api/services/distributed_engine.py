from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.distributed.client import (
    distributed_enabled,
    materialize_feature_stage_from_events,
    score_roi_candidates,
)

LOGGER = logging.getLogger(__name__)


def attach_distributed_roi_scores(candidates: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replace ROI/profit columns with gRPC/OpenMP scores when enabled.

    The original pandas path remains the fallback so the dashboard keeps working
    if the worker is unavailable during local development.
    """
    if candidates.empty or not distributed_enabled():
        return candidates, {"enabled": distributed_enabled(), "used": False, "reason": "disabled_or_empty"}

    try:
        scored, metrics = score_roi_candidates(candidates, top_n=len(candidates))
    except Exception as exc:  # keep the platform available under worker failures
        LOGGER.warning("distributed ROI scoring failed; falling back to local scoring: %s", exc)
        return candidates, {"enabled": True, "used": False, "fallback": True, "error": str(exc)}

    if scored.empty:
        return candidates, {"enabled": True, "used": False, "reason": "empty_worker_response"}

    out = candidates.copy()
    scored = scored[["customer_id", "expected_incremental_profit", "expected_roi"]].copy()
    out["customer_id"] = out["customer_id"].astype(str)
    scored["customer_id"] = scored["customer_id"].astype(str)
    out = out.drop(columns=["expected_incremental_profit", "expected_roi"], errors="ignore").merge(
        scored,
        on="customer_id",
        how="left",
    )
    out["expected_incremental_profit"] = pd.to_numeric(out["expected_incremental_profit"], errors="coerce").fillna(0.0)
    out["expected_roi"] = pd.to_numeric(out["expected_roi"], errors="coerce").fillna(0.0)
    out["expected_revenue"] = out["expected_incremental_profit"] + pd.to_numeric(out.get("coupon_cost", 0.0), errors="coerce").fillna(0.0)
    out["distributed_scoring_engine"] = str(metrics.get("parallel_kernel", "grpc-openmp"))
    return out, {"enabled": True, "used": True, **metrics}


def materialize_uploaded_distributed_features(data_dir: Path, result_dir: Path) -> dict[str, Any]:
    events_path = data_dir / "events.csv"
    output_path = result_dir / "distributed_customer_features.csv"
    try:
        return materialize_feature_stage_from_events(events_path, output_path)
    except Exception as exc:
        LOGGER.warning("distributed feature materialization failed: %s", exc)
        return {"enabled": distributed_enabled(), "used": False, "fallback": True, "error": str(exc)}
