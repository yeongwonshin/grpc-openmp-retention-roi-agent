from __future__ import annotations

import argparse
import logging
from concurrent import futures
from time import perf_counter
from typing import Any

import grpc
import numpy as np
import pandas as pd

from src.distributed.grpc_json import unary_json_handler

LOGGER = logging.getLogger("retention_roi.feature_worker")


def _normalize_events(events: list[dict[str, Any]]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["customer_id", "amount", "event_type", "timestamp"])
    df = pd.DataFrame(events)
    if "customer_id" not in df.columns:
        raise ValueError("events must contain customer_id")
    df["amount"] = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)
    df["event_type"] = df.get("event_type", "visit").astype(str).str.lower()
    return df


def extract_features(payload: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    df = _normalize_events(payload.get("events", []))
    if df.empty:
        return {"ok": True, "stage": "feature_worker", "features": [], "rows_in": 0, "rows_out": 0, "elapsed_ms": 0.0}

    grouped = df.groupby("customer_id", sort=False)
    features = grouped.agg(
        frequency=("event_type", "size"),
        monetary=("amount", "sum"),
        avg_order_value=("amount", "mean"),
    ).reset_index()

    purchase_counts = df["event_type"].eq("purchase").groupby(df["customer_id"]).sum().rename("purchase_count")
    support_counts = df["event_type"].str.contains("support|cancel|refund|complaint", regex=True).groupby(df["customer_id"]).sum().rename("support_count")
    features = features.merge(purchase_counts, on="customer_id", how="left").merge(support_counts, on="customer_id", how="left")
    features[["purchase_count", "support_count"]] = features[["purchase_count", "support_count"]].fillna(0)

    # Lightweight retention signals used by the downstream OpenMP ROI kernel.
    freq = features["frequency"].to_numpy(dtype=float)
    monetary = features["monetary"].to_numpy(dtype=float)
    support = features["support_count"].to_numpy(dtype=float)
    churn = 1.0 / (1.0 + np.exp(-(0.55 * support - 0.035 * freq - 0.0007 * monetary + 0.8)))
    uplift = np.clip(0.02 + 0.22 * churn + 0.015 * np.log1p(freq), 0.01, 0.35)
    clv = np.clip(25.0 + 1.8 * monetary + 8.0 * freq, 20.0, None)
    coupon_cost = np.clip(4.0 + 0.015 * clv + 2.0 * churn, 3.0, 75.0)

    features["churn_probability"] = churn
    features["uplift_score"] = uplift
    features["clv"] = clv
    features["coupon_cost"] = coupon_cost

    elapsed_ms = (perf_counter() - started) * 1000.0
    return {
        "ok": True,
        "stage": "feature_worker",
        "rows_in": int(len(df)),
        "rows_out": int(len(features)),
        "elapsed_ms": elapsed_ms,
        "serialization": "json-over-grpc",
        "features": features.to_dict(orient="records"),
    }


def serve(host: str = "0.0.0.0", port: int = 50051, max_workers: int = 4) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    handler = grpc.method_handlers_generic_handler(
        "retention_roi.FeatureService",
        {"ExtractFeatures": unary_json_handler(extract_features)},
    )
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    LOGGER.info("Feature worker listening on %s:%s", host, port)
    server.wait_for_termination()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the gRPC feature extraction worker.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(args.host, args.port, args.max_workers)
