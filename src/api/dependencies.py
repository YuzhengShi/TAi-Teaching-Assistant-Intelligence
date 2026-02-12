"""
FastAPI dependency injection for TAi services.
"""

from typing import Annotated, Optional

from fastapi import Request

from src.core.pipeline import TAiPipeline
from src.memory.store import SafeMemoryStore
from src.memory.worker import GraphSyncWorker
from src.session.manager import SessionManager


def get_pipeline(request: Request) -> TAiPipeline:
    """Get TAiPipeline singleton from lifespan state."""
    return request.app.state.pipeline


def get_memory_store(request: Request) -> SafeMemoryStore:
    """Get SafeMemoryStore singleton from lifespan state."""
    return request.app.state.memory_store


def get_session_manager(request: Request) -> SessionManager:
    """Get SessionManager singleton from lifespan state."""
    return request.app.state.session_manager


def get_worker(request: Request) -> Optional["GraphSyncWorker"]:
    """Get GraphSyncWorker from lifespan state (may be None if not started)."""
    return getattr(request.app.state, "graph_sync_worker", None)


PipelineDep = Annotated[TAiPipeline, "TAiPipeline from app state"]
MemoryStoreDep = Annotated[SafeMemoryStore, "SafeMemoryStore from app state"]
SessionManagerDep = Annotated[SessionManager, "SessionManager from app state"]
WorkerDep = Annotated[Optional[GraphSyncWorker], "GraphSyncWorker from app state"]
