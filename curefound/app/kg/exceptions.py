"""KG-domain exception subclasses. All inherit AppError so they get the
consistent `{error, message, details}` envelope from the central handler."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError, InvalidInput, KGNotLoadedError, NodeNotFound


class UnknownNodeId(NodeNotFound):
    code = "unknown_node_id"


class MalformedNodeId(InvalidInput):
    code = "malformed_node_id"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


__all__ = [
    "AppError",
    "KGNotLoadedError",
    "MalformedNodeId",
    "NodeNotFound",
    "UnknownNodeId",
]
