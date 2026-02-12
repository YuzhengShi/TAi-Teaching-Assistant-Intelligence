"""
Neo4j connection management with pooling and retry logic.
"""

import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, TransientError

from src.shared.config import settings
from src.shared.exceptions import GraphConnectionError
from src.shared.logging import get_logger

logger = get_logger(__name__)


class Neo4jConnection:
    """Neo4j connection manager with retry logic."""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.uri = uri or settings.neo4j.uri
        self.user = user or settings.neo4j.user
        self.password = password or settings.neo4j.password
        
        self._driver: Optional[AsyncGraphDatabase] = None
        self._sync_driver: Optional[GraphDatabase] = None
    
    async def connect(self):
        """Initialize async driver."""
        if self._driver is None:
            try:
                self._driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                    max_connection_lifetime=settings.neo4j.max_connection_lifetime,
                    max_connection_pool_size=settings.neo4j.max_connection_pool_size
                )
                # Verify connectivity
                await self._driver.verify_connectivity()
                logger.info("Neo4j async driver connected", extra={"uri": self.uri})
            except Exception as e:
                raise GraphConnectionError(f"Failed to connect to Neo4j: {str(e)}") from e
    
    def connect_sync(self):
        """Initialize sync driver (for migrations)."""
        if self._sync_driver is None:
            try:
                self._sync_driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                    max_connection_lifetime=settings.neo4j.max_connection_lifetime,
                    max_connection_pool_size=settings.neo4j.max_connection_pool_size
                )
                # Verify connectivity
                self._sync_driver.verify_connectivity()
                logger.info("Neo4j sync driver connected", extra={"uri": self.uri})
            except Exception as e:
                raise GraphConnectionError(f"Failed to connect to Neo4j: {str(e)}") from e
    
    @asynccontextmanager
    async def session(self, **kwargs):
        """Get async session with automatic retry on transient errors."""
        if self._driver is None:
            await self.connect()
        
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                async with self._driver.session(**kwargs) as session:
                    yield session
                    return
            except (ServiceUnavailable, TransientError) as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Transient error, retrying ({attempt + 1}/{max_retries}): {str(e)}"
                    )
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    raise GraphConnectionError(f"Failed after {max_retries} retries: {str(e)}") from e
            except Exception as e:
                raise GraphConnectionError(f"Unexpected error: {str(e)}") from e
    
    def session_sync(self, **kwargs):
        """Get sync session."""
        if self._sync_driver is None:
            self.connect_sync()
        
        return self._sync_driver.session(**kwargs)
    
    async def health_check(self) -> bool:
        """Check if Neo4j is healthy."""
        try:
            if self._driver is None:
                await self.connect()
            
            async with self.session() as session:
                result = await session.run("RETURN 1 as health")
                record = await result.single()
                return record is not None and record["health"] == 1
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False
    
    async def close(self):
        """Close async driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j async driver closed")
    
    def close_sync(self):
        """Close sync driver."""
        if self._sync_driver:
            self._sync_driver.close()
            self._sync_driver = None
            logger.info("Neo4j sync driver closed")


# Global connection instance
_connection: Optional[Neo4jConnection] = None


def get_connection() -> Neo4jConnection:
    """Get or create global Neo4j connection."""
    global _connection
    if _connection is None:
        _connection = Neo4jConnection()
    return _connection
