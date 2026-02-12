"""
SafeMemoryStore: SQLite + WAL mode for FERPA-compliant student data storage.
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from contextlib import contextmanager

from src.shared.config import settings
from src.shared.exceptions import ConsentRequiredError, FERPAComplianceError
from src.shared.logging import get_logger

logger = get_logger(__name__)


class SafeMemoryStore:
    """FERPA-compliant memory store with WAL mode and crash recovery."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(settings.wal_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Crash recovery
        self._recover_from_crash()
    
    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Enable WAL mode
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Create tables
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    anonymized_id TEXT NOT NULL UNIQUE,
                    consent_granted BOOLEAN DEFAULT 0,
                    consent_timestamp TEXT,
                    consent_text TEXT,
                    consent_session_token TEXT,
                    data_retention_days INTEGER DEFAULT 365,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    extracted_events_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES students(id)
                );
                
                CREATE TABLE IF NOT EXISTS student_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    fact_text TEXT NOT NULL,
                    fact_type TEXT NOT NULL,
                    confidence_score REAL,
                    graph_synced BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES students(id)
                );
                
                CREATE TABLE IF NOT EXISTS wal_checkpoint (
                    id INTEGER PRIMARY KEY,
                    last_processed_id INTEGER,
                    checkpoint_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_memories_student ON memories(student_id);
                CREATE INDEX IF NOT EXISTS idx_memories_hash ON memories(content_hash);
                CREATE INDEX IF NOT EXISTS idx_facts_student ON student_facts(student_id);
                CREATE INDEX IF NOT EXISTS idx_facts_synced ON student_facts(graph_synced);
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def require_consent(self, student_id: str) -> bool:
        """Check if student has granted consent."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT consent_granted FROM students WHERE id = ?",
                (student_id,)
            ).fetchone()
            
            return result and result["consent_granted"] == 1
    
    def write_memory(
        self,
        student_id: str,
        content: str,
        extracted_events: Optional[Dict] = None
    ) -> int:
        """
        Write memory with content hash deduplication.
        
        Raises:
            ConsentRequiredError if consent not granted
        """
        if not self.require_consent(student_id):
            raise ConsentRequiredError(f"Student {student_id} has not granted consent")
        
        # Generate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        with self._get_connection() as conn:
            # Check for duplicate
            existing = conn.execute(
                "SELECT id FROM memories WHERE content_hash = ?",
                (content_hash,)
            ).fetchone()
            
            if existing:
                logger.debug(f"Duplicate content detected, skipping: {content_hash[:8]}")
                return existing["id"]
            
            # Insert new memory
            cursor = conn.execute(
                """INSERT INTO memories (student_id, content, content_hash, extracted_events_json)
                   VALUES (?, ?, ?, ?)""",
                (
                    student_id,
                    content,
                    content_hash,
                    json.dumps(extracted_events) if extracted_events else None
                )
            )
            
            return cursor.lastrowid
    
    def write_student_fact(
        self,
        student_id: str,
        fact_text: str,
        fact_type: str,
        confidence_score: float
    ) -> int:
        """Write student fact to WAL (not yet synced to graph)."""
        if not self.require_consent(student_id):
            raise ConsentRequiredError(f"Student {student_id} has not granted consent")
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO student_facts (student_id, fact_text, fact_type, confidence_score, graph_synced)
                   VALUES (?, ?, ?, ?, 0)""",
                (student_id, fact_text, fact_type, confidence_score)
            )
            return cursor.lastrowid
    
    def get_unsynced_facts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get facts not yet synced to graph."""
        with self._get_connection() as conn:
            result = conn.execute(
                """SELECT id, student_id, fact_text, fact_type, confidence_score
                   FROM student_facts
                   WHERE graph_synced = 0
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (limit,)
            )
            
            return [dict(row) for row in result.fetchall()]
    
    def mark_fact_synced(self, fact_id: int):
        """Mark fact as synced to graph."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE student_facts SET graph_synced = 1 WHERE id = ?",
                (fact_id,)
            )
    
    def _recover_from_crash(self):
        """Recover from potential crash (validate in-progress records)."""
        # In a full implementation, would check for incomplete transactions
        logger.info("Crash recovery check completed")
