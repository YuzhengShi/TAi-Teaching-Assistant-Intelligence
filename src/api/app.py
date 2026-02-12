"""
TAi FastAPI application.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.core.pipeline import TAiPipeline
from src.graph.schema import ensure_schema
from src.memory.worker import GraphSyncWorker
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)

# Will be set in lifespan
_graph_sync_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    global _graph_sync_task

    # Startup
    logger.info("Starting TAi API")

    # Initialize pipeline (creates memory_store, session_manager, etc.)
    pipeline = TAiPipeline()
    app.state.pipeline = pipeline
    app.state.memory_store = pipeline.memory_store
    app.state.session_manager = pipeline.session_manager

    # Run schema migration
    try:
        await ensure_schema()
    except Exception as e:
        logger.warning("Schema migration failed (Neo4j may be unavailable): %s", e)

    # Start GraphSyncWorker background task
    worker = GraphSyncWorker(pipeline.memory_store)
    app.state.graph_sync_worker = worker
    _graph_sync_task = asyncio.create_task(worker.run_forever(interval=1.0))

    # Track uptime
    health.set_start_time(time.time())

    logger.info("TAi API ready")
    yield

    # Shutdown
    logger.info("Shutting down TAi API")
    if worker:
        worker.stop()
    if _graph_sync_task and not _graph_sync_task.done():
        _graph_sync_task.cancel()
        try:
            await _graph_sync_task
        except asyncio.CancelledError:
            pass
    logger.info("TAi API stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="TAi",
        description="Teaching Assistant Intelligence - GraphRAG-based distributed systems education",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    cors_origins = getattr(settings.api, "cors_origins", ["http://localhost:3000"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting (after CORS so CORS headers applied first)
    app.add_middleware(RateLimitMiddleware)

    # Routes
    app.include_router(health.router)

    # Root endpoint (rate limited, for liveness)
    @app.get("/")
    async def root():
        return {"service": "tai", "status": "running"}

    return app


app = create_app()


def main():
    """CLI entry point for uvicorn."""
    import uvicorn

    host = getattr(settings.api, "host", "0.0.0.0")
    port = getattr(settings.api, "port", 8000)
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
