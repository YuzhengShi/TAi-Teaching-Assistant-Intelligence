"""
Tests for memory flush engine.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.memory.flush import MemoryFlushEngine
from src.memory.store import SafeMemoryStore


@pytest.mark.asyncio
async def test_flush_extracts_structured_events():
    """Test that flush produces structured learning events."""
    store = SafeMemoryStore()
    engine = MemoryFlushEngine(store)
    
    # Mock LLM response
    mock_response = {
        "learning_events": [
            {
                "concept_name": "Raft",
                "event_type": "MASTERED",
                "confidence": 0.8,
                "evidence_type": "socratic_dialogue",
                "context_scope": "theoretical",
                "evidence": {"text": "Student explained correctly"}
            }
        ]
    }
    
    engine.llm.get_structured_completion = AsyncMock(return_value=mock_response)
    
    # Grant consent
    with store._get_connection() as conn:
        conn.execute(
            "INSERT INTO students (id, anonymized_id, consent_granted) VALUES (?, ?, 1)",
            ("test_student", "anon_123")
        )
        conn.commit()
    
    session = {
        "student_id": "test_student",
        "messages": [
            {"role": "student", "content": "Raft uses leader election"},
            {"role": "assistant", "content": "Correct!"}
        ],
        "last_activity": "2024-01-15T10:00:00Z"
    }
    
    events = await engine.flush(session)
    
    assert len(events) == 1
    assert events[0].concept_name == "Raft"
    assert events[0].event_type == "MASTERED"
    assert events[0].confidence == 0.8


@pytest.mark.asyncio
async def test_flush_llm_failure_doesnt_block():
    """Test that LLM failure doesn't block compaction."""
    store = SafeMemoryStore()
    engine = MemoryFlushEngine(store)
    
    # Mock LLM failure
    engine.llm.get_structured_completion = AsyncMock(side_effect=Exception("LLM error"))
    
    session = {
        "student_id": "test_student",
        "messages": [{"role": "student", "content": "Test"}],
        "last_activity": "2024-01-15T10:00:00Z"
    }
    
    # Should not raise exception
    events = await engine.flush(session)
    
    # Should return empty list, not crash
    assert events == []


def test_flush_threshold_check():
    """Test that flush triggers at correct threshold."""
    store = SafeMemoryStore()
    engine = MemoryFlushEngine(store, {"flush_threshold": 1000})
    
    # Session below threshold
    session_small = {
        "messages": [{"content": "Short message"}]
    }
    assert not engine.should_flush(session_small)
    
    # Session above threshold
    session_large = {
        "messages": [{"content": "X" * 10000}]  # Large message
    }
    assert engine.should_flush(session_large)
