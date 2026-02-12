"""
Health check endpoint.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import get_memory_store, get_worker
from src.graph.connection import get_connection
from src.memory.store import SafeMemoryStore
from src.memory.worker import GraphSyncWorker

router = APIRouter(tags=["health"])

# Track startup time for uptime
_start_time: Optional[float] = None


def set_start_time(t: float):
    """Set application start time."""
    global _start_time
    _start_time = t


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    neo4j_connected: bool
    wal_backlog_depth: int
    circuit_breaker_state: str
    uptime_seconds: float


@router.get("/health", response_model=HealthResponse)
async def health_check(
    memory_store: SafeMemoryStore = Depends(get_memory_store),
    worker: Optional[GraphSyncWorker] = Depends(get_worker),
):
    """
    Service health check.
    Returns status, Neo4j connection, WAL backlog, circuit breaker state, uptime.
    """
    import time

    # Neo4j connection status
    connection = get_connection()
    neo4j_connected = False
    try:
        neo4j_connected = await connection.health_check()
    except Exception:
        pass

    # WAL backlog (unsynced facts count)
    unsynced = memory_store.get_unsynced_facts(limit=10000)
    wal_backlog_depth = len(unsynced)

    # Circuit breaker state from worker
    circuit_breaker_state = "UNKNOWN"
    if worker:
        circuit_breaker_state = worker.circuit_breaker.state

    # Uptime
    uptime_seconds = 0.0
    if _start_time:
        uptime_seconds = round(time.time() - _start_time, 2)

    return HealthResponse(
        status="healthy" if neo4j_connected else "degraded",
        neo4j_connected=neo4j_connected,
        wal_backlog_depth=wal_backlog_depth,
        circuit_breaker_state=circuit_breaker_state,
        uptime_seconds=uptime_seconds,
    )
