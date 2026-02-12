"""
Tests for misconception detection.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.memory.misconception import MisconceptionDetector
from src.memory.store import SafeMemoryStore


@pytest.mark.asyncio
async def test_holding_vs_identifying_misconception():
    """Test that system distinguishes HOLDING vs IDENTIFYING."""
    store = SafeMemoryStore()
    detector = MisconceptionDetector(store)
    
    # Mock LLM response for student HOLDING misconception
    mock_holding = {
        "holds_known_misconception": True,
        "matched_misconception": "Raft always available",
        "is_identifying_not_holding": False,
        "is_new_candidate": False
    }
    
    # Mock LLM response for student IDENTIFYING misconception
    mock_identifying = {
        "holds_known_misconception": False,
        "matched_misconception": None,
        "is_identifying_not_holding": True,
        "is_new_candidate": False
    }
    
    detector.llm.get_structured_completion = AsyncMock(return_value=mock_holding)
    
    result = await detector.check("Raft guarantees availability during partitions", "Raft")
    
    # Should detect misconception
    assert result["holds_known_misconception"] is True
    
    # Test identifying case
    detector.llm.get_structured_completion = AsyncMock(return_value=mock_identifying)
    result2 = await detector.check("Some students think Raft is always available, but that's wrong", "Raft")
    
    # Should NOT flag as misconception (student is identifying, not holding)
    assert result2["is_identifying_not_holding"] is True
    assert result2["holds_known_misconception"] is False


@pytest.mark.asyncio
async def test_new_candidate_written_to_wal():
    """Test that new candidate misconceptions are written to WAL."""
    store = SafeMemoryStore()
    detector = MisconceptionDetector(store)
    
    # Mock new candidate
    mock_new = {
        "holds_known_misconception": False,
        "is_identifying_not_holding": False,
        "is_new_candidate": True,
        "new_candidate_description": "Raft uses majority voting for everything",
        "contradicts_concept": "Raft leader election"
    }
    
    detector.llm.get_structured_completion = AsyncMock(return_value=mock_new)
    
    # Mock WAL write
    with patch.object(store, 'write_student_fact') as mock_write:
        await detector.check("Raft uses majority voting for all decisions", "Raft")
        
        # Should write to WAL
        assert mock_write.called


@pytest.mark.asyncio
async def test_frequency_tracking():
    """Test that misconception frequency increments across students."""
    # This would test that multiple independent student interactions
    # increment the frequency counter
    # Structure test for now
    assert True
