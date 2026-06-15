from __future__ import annotations

import json
from typing import Any, Callable

import grpc


def dumps_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def loads_json(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def unary_json_handler(func: Callable[[dict[str, Any]], dict[str, Any]]) -> grpc.RpcMethodHandler:
    def _handler(request: bytes, context: grpc.ServicerContext) -> bytes:
        try:
            return dumps_json(func(loads_json(request)))
        except Exception as exc:  # pragma: no cover - defensive boundary for RPC callers
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return dumps_json({"ok": False, "error": str(exc)})

    return grpc.unary_unary_rpc_method_handler(
        _handler,
        request_deserializer=lambda x: x,
        response_serializer=lambda x: x,
    )


def call_json(address: str, method: str, payload: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    with grpc.insecure_channel(address) as channel:
        stub = channel.unary_unary(
            method,
            request_serializer=dumps_json,
            response_deserializer=loads_json,
        )
        return stub(payload, timeout=timeout)
