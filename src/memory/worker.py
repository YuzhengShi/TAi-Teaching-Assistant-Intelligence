"""
Async WAL → Neo4j graph worker with circuit breaker.
"""

import asyncio
import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from src.memory.store import SafeMemoryStore
from src.graph.connection import get_connection
from src.graph.queries import StudentQueries, MisconceptionQueries
from src.shared.config import settings
from src.shared.exceptions import CircuitBreakerOpenError, GraphConnectionError
from src.shared.logging import get_logger

logger = get_logger(__name__)


class CircuitBreaker:
    """Circuit breaker for Neo4j operations."""
    
    def __init__(self, failure_threshold: int = 3, reset_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
    
    def can_proceed(self) -> bool:
        """Check if operation can proceed."""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # Check if reset time has passed
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.reset_seconds:
                    self.state = "HALF_OPEN"
                    return True
            return False
        
        if self.state == "HALF_OPEN":
            return True
        
        return False
    
    def raise_if_open(self):
        """Raise exception if circuit is open."""
        if not self.can_proceed():
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. Wait {self.reset_seconds} seconds before retry."
            )


class GraphSyncWorker:
    """Background worker that syncs WAL facts to Neo4j graph."""
    
    def __init__(self, memory_store: SafeMemoryStore, config: Optional[Dict] = None):
        self.memory_store = memory_store
        self.config = config or {}
        self.batch_size = self.config.get("batch_size", 100)
        
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            reset_seconds=settings.circuit_breaker_reset_seconds
        )
        
        self.processed_ids = set()  # Track processed fact IDs for idempotency
        self.metrics = {
            "successful_writes": 0,
            "duplicate_skips": 0,
            "failed_writes": 0,
            "circuit_opens": 0
        }
        
        self.neo4j = get_connection()
        self.running = False
    
    async def run_forever(self, interval: float = 1.0):
        """Run worker continuously."""
        self.running = True
        logger.info("Graph sync worker started")
        
        while self.running:
            try:
                await self.process_batch()
            except Exception as e:
                logger.error(f"Worker error: {str(e)}")
            
            await asyncio.sleep(interval)
    
    def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("Graph sync worker stopped")
    
    async def process_batch(self, batch_size: Optional[int] = None):
        """Process a batch of unsynced facts."""
        batch_size = batch_size or self.batch_size
        
        # Check circuit breaker
        self.circuit_breaker.raise_if_open()
        
        # Get unsynced facts
        facts = self.memory_store.get_unsynced_facts(limit=batch_size)
        
        if not facts:
            return
        
        # Process each fact
        for fact in facts:
            fact_id = fact["id"]
            
            # Check idempotency
            if fact_id in self.processed_ids:
                self.metrics["duplicate_skips"] += 1
                continue
            
            try:
                # Sync to graph
                await self._sync_fact_to_graph(fact)
                
                # Mark as synced
                self.memory_store.mark_fact_synced(fact_id)
                self.processed_ids.add(fact_id)
                self.metrics["successful_writes"] += 1
                
                # Record success
                self.circuit_breaker.record_success()
            
            except Exception as e:
                logger.error(f"Failed to sync fact {fact_id}: {str(e)}")
                self.metrics["failed_writes"] += 1
                self.circuit_breaker.record_failure()
                
                # If circuit opens, stop processing this batch
                if not self.circuit_breaker.can_proceed():
                    self.metrics["circuit_opens"] += 1
                    break
    
    async def _sync_fact_to_graph(self, fact: Dict[str, Any]):
        """Sync a single fact to Neo4j graph."""
        student_id = fact["student_id"]
        fact_text = fact["fact_text"]
        fact_type = fact["fact_type"]
        confidence = fact["confidence_score"]
        
        # Parse fact to extract concept
        # Simplified: assume fact_text contains concept name
        # In production, would use more sophisticated parsing
        concept_name = self._extract_concept_name(fact_text)
        
        if not concept_name:
            return
        
        # Generate concept ID
        concept_id = hashlib.sha256(concept_name.lower().encode()).hexdigest()[:16]
        
        with self.neo4j.session_sync() as session:
            # Upsert concept
            from src.graph.queries import CourseQueries
            concept_query = CourseQueries.upsert_concept(
                name=concept_name,
                description=fact_text,
                concept_type="CONCEPT"
            )
            session.run(concept_query.query, concept_query.params)
            
            # Create UNDERSTANDS relationship
            if fact_type == "MASTERED":
                # Determine context scope from fact text
                context_scope = "theoretical"  # Default
                if "code" in fact_text.lower() or "implement" in fact_text.lower():
                    context_scope = "implementation"
                elif "debug" in fact_text.lower():
                    context_scope = "debugging"
                
                understands_query = StudentQueries.create_understanding_relationship(
                    student_id=student_id,
                    concept_id=concept_id,
                    confidence=confidence,
                    context_scope=context_scope,
                    demonstrated_via="socratic_dialogue"  # Default
                )
                session.run(understands_query.query, understands_query.params)
    
    def _extract_concept_name(self, fact_text: str) -> Optional[str]:
        """Extract concept name from fact text (simplified)."""
        # Look for pattern: "MASTERED: ConceptName" or "STRUGGLING: ConceptName"
        import re
        match = re.search(r'(MASTERED|STRUGGLING|REVIEWED):\s*([^(\n]+)', fact_text)
        if match:
            return match.group(2).strip()
        
        # Fallback: first few words
        words = fact_text.split()[:3]
        return " ".join(words) if words else None
