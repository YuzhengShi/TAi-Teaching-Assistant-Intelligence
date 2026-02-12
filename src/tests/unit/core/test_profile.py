"""
Tests for student profile generation and caching.
"""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.profile.generator import ProfileGenerator
from src.core.profile.cache import ProfileCache


@pytest.mark.asyncio
async def test_profile_generated_from_graph(neo4j_driver):
    """Test that profile is generated from graph queries."""
    generator = ProfileGenerator()
    
    # Mock Neo4j response
    mock_record = MagicMock()
    mock_record.__getitem__.side_effect = lambda key: {
        "student_id": "test_student",
        "understandings": [
            {"concept_name": "Raft", "confidence": 0.8, "context_scope": "theoretical"}
        ],
        "gaps": [],
        "misconceptions": []
    }.get(key, [])
    mock_record.get = lambda key, default=None: {
        "student_id": "test_student",
        "understandings": [
            {"concept_name": "Raft", "confidence": 0.8, "context_scope": "theoretical"}
        ],
        "gaps": [],
        "misconceptions": []
    }.get(key, default)
    
    with patch.object(generator.neo4j, 'session') as mock_session:
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        mock_session.return_value.__enter__.return_value.run.return_value = mock_result
        
        profile = await generator.generate("test_student", topic="Raft", session_type="study")
        
        assert "Raft" in profile
        assert "confidence" in profile.lower() or "0.8" in profile


@pytest.mark.asyncio
async def test_cache_hit_prevents_graph_query():
    """Test that cache hit prevents redundant graph queries."""
    cache = ProfileCache()
    generator = ProfileGenerator()
    
    # Mock generator to track calls
    call_count = 0
    
    async def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return "# Test Profile"
    
    generator.generate = mock_generate
    cache.generator = generator
    
    # First call - should generate
    profile1 = await cache.get_profile("student1", "Raft", "study")
    assert call_count == 1
    
    # Second call - should hit cache
    profile2 = await cache.get_profile("student1", "Raft", "study")
    assert call_count == 1  # No additional call
    assert profile1 == profile2


def test_cache_invalidation():
    """Test that cache invalidation clears student profiles."""
    cache = ProfileCache()
    
    # Populate cache
    cache.l1_cache["student1:Raft:study"] = ("# Profile", time.time())
    
    # Invalidate
    cache.invalidate("student1")
    
    # Cache should be cleared
    assert "student1:Raft:study" not in cache.l1_cache


@pytest.mark.asyncio
async def test_profile_varies_by_session_type():
    """Test that different session types produce different profiles."""
    generator = ProfileGenerator()
    
    # Mock data
    data = {
        "understandings": [
            {"concept_name": "Raft", "confidence": 0.8, "context_scope": "verbal"}
        ],
        "gaps": [{"concept_name": "Paxos"}],
        "misconceptions": []
    }
    
    # Interview profile should focus on verbal
    interview_profile = generator._format_interview_profile(data)
    assert "Verbal" in interview_profile or "verbal" in interview_profile.lower()
    
    # Study profile should focus on gaps
    study_profile = generator._format_study_profile(data)
    assert "Paxos" in study_profile or "gap" in study_profile.lower()
