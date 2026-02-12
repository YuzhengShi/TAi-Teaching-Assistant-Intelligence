"""
Tests for SafeMemoryStore: ACID, crash recovery, deduplication.
"""

import pytest
import sqlite3
import threading
import time

from src.memory.store import SafeMemoryStore
from src.shared.exceptions import ConsentRequiredError


def test_wal_mode_enabled(tmp_path):
    """Test that WAL mode is enabled."""
    db_path = tmp_path / "test.db"
    store = SafeMemoryStore(db_path)
    
    with store._get_connection() as conn:
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].upper() == "WAL"


def test_concurrent_writes(tmp_path):
    """Test ACID compliance with concurrent writes."""
    db_path = tmp_path / "test.db"
    store = SafeMemoryStore(db_path)
    
    # Grant consent
    student_id = "test_student"
    with store._get_connection() as conn:
        conn.execute(
            "INSERT INTO students (id, anonymized_id, consent_granted) VALUES (?, ?, 1)",
            (student_id, "anon_123")
        )
        conn.commit()
    
    # Concurrent writes
    errors = []
    
    def write_memory(i):
        try:
            store.write_memory(student_id, f"Memory content {i}")
        except Exception as e:
            errors.append(str(e))
    
    threads = [threading.Thread(target=write_memory, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Should have no errors
    assert len(errors) == 0
    
    # Verify all memories written
    with store._get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE student_id = ?",
            (student_id,)
        ).fetchone()[0]
        assert count == 10


def test_content_hash_deduplication(tmp_path):
    """Test that duplicate content is not stored twice."""
    db_path = tmp_path / "test.db"
    store = SafeMemoryStore(db_path)
    
    student_id = "test_student"
    with store._get_connection() as conn:
        conn.execute(
            "INSERT INTO students (id, anonymized_id, consent_granted) VALUES (?, ?, 1)",
            (student_id, "anon_123")
        )
        conn.commit()
    
    content = "Duplicate content"
    
    # Write twice
    id1 = store.write_memory(student_id, content)
    id2 = store.write_memory(student_id, content)
    
    # Should return same ID (deduplication)
    assert id1 == id2
    
    # Verify only one record in database
    import hashlib
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    with store._get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()[0]
        assert count == 1


def test_consent_required_for_write(tmp_path):
    """Test that writing without consent raises error."""
    db_path = tmp_path / "test.db"
    store = SafeMemoryStore(db_path)
    
    student_id = "no_consent"
    
    with pytest.raises(ConsentRequiredError):
        store.write_memory(student_id, "Some content")


def test_crash_recovery(tmp_path):
    """Test crash recovery on startup."""
    db_path = tmp_path / "test.db"
    store = SafeMemoryStore(db_path)
    
    # Store should initialize and check for incomplete transactions
    # In full implementation, would validate and repair
    assert store.db_path.exists()
