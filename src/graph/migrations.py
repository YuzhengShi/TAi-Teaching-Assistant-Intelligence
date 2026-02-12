"""
Graph schema migrations and versioning.
"""

from src.graph.schema import ensure_schema, ensure_schema_sync, SCHEMA_VERSION
from src.shared.logging import get_logger

logger = get_logger(__name__)


async def migrate():
    """Run async schema migration."""
    await ensure_schema()


def migrate_sync():
    """Run synchronous schema migration (for CLI)."""
    ensure_schema_sync()


if __name__ == "__main__":
    # CLI entry point
    migrate_sync()
