from __future__ import annotations

from typing import Any


def rpc_error(exc: Exception) -> dict[str, Any]:
    """Map internal exceptions to stable JSON-RPC codes without losing messages."""
    if isinstance(exc, KeyError):
        code, kind = -32600, "invalid_request"
    elif isinstance(exc, LookupError):
        code, kind = -32601, "method_not_found"
    elif isinstance(exc, (ValueError, TypeError)):
        code, kind = -32602, "invalid_params"
    elif isinstance(exc, TimeoutError):
        code, kind = -32001, "timeout"
    elif isinstance(exc, PermissionError):
        code, kind = -32003, "permission_denied"
    elif isinstance(exc, FileNotFoundError):
        code, kind = -32004, "not_found"
    else:
        code, kind = -32000, "internal_error"
    return {"code": code, "message": str(exc), "data": {"kind": kind}}
