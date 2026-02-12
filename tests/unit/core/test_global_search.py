"""
Tests for global search (community-based map-reduce).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.retrieval.global_search import GlobalSearch, GlobalSearchResult


@pytest.mark.asyncio
async def test_global_search_with_communities():
    """Test that global search produces synthesized answer from community summaries."""
    search = GlobalSearch()
    
    # Mock community loading
    mock_communities = [
        {"id": "community_0", "summary": "Consensus protocols: Raft, Paxos", "node_count": 5},
        {"id": "community_1", "summary": "Data structures: DHT, B-tree", "node_count": 3},
    ]
    
    with patch.object(search, '_load_community_summaries', return_value=mock_communities):
        # Mock LLM for map phase
        search.llm.get_completion = AsyncMock(side_effect=[
            "Raft and Paxos are the main consensus approaches. Relevance: 0.9",
            "NOT_RELEVANT",  # Second community
            "Synthesized: Raft and Paxos are the primary consensus protocols.",  # Reduce
        ])
        
        result = await search.search("What are the main consensus approaches?")
        
        assert isinstance(result, GlobalSearchResult)
        assert result.synthesized_answer  # Non-empty
        assert len(result.communities_used) >= 1


@pytest.mark.asyncio
async def test_global_search_empty_communities():
    """Test that empty communities return graceful response."""
    search = GlobalSearch()
    
    with patch.object(search, '_load_community_summaries', return_value=[]):
        result = await search.search("What are the main themes?")
        
        assert "No community data" in result.synthesized_answer
        assert result.communities_used == []


def test_relevance_score_extraction():
    """Test that relevance score is extracted from response text."""
    search = GlobalSearch()
    
    # With explicit score
    score = search._extract_relevance_score("Some answer. Relevance: 0.85")
    assert score == 0.85
    
    # Without score, long response
    score = search._extract_relevance_score("A long answer about consensus that is relevant")
    assert score == 0.6  # Default for non-empty, non-NOT_RELEVANT
    
    # NOT_RELEVANT response
    score = search._extract_relevance_score("NOT_RELEVANT")
    assert score == 0.3
