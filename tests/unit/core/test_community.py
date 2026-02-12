"""
Tests for community detection and summarization.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import igraph as ig

from src.core.indexing.community import CommunityDetector, Community


def test_leiden_produces_communities():
    """Test that Leiden algorithm produces communities from a small graph."""
    detector = CommunityDetector()
    
    # Create a small test graph (10 nodes, 15 edges)
    graph = ig.Graph(directed=True)
    
    # Two clusters of nodes
    for i in range(10):
        graph.add_vertex(name=f"concept_{i}", label=f"Concept {i}")
    
    # Cluster 1: nodes 0-4 densely connected
    for i in range(5):
        for j in range(i + 1, 5):
            graph.add_edge(i, j)
    
    # Cluster 2: nodes 5-9 densely connected
    for i in range(5, 10):
        for j in range(i + 1, 10):
            graph.add_edge(i, j)
    
    # One bridge edge between clusters
    graph.add_edge(4, 5)
    
    communities = detector._run_leiden(graph)
    
    # Should find at least 2 communities
    assert len(communities) >= 2
    
    # All nodes should be assigned
    all_nodes = set()
    for community in communities:
        all_nodes.update(community.nodes)
    assert len(all_nodes) == 10


@pytest.mark.asyncio
async def test_community_summaries_non_empty():
    """Test that community summaries are non-empty strings."""
    detector = CommunityDetector()
    
    # Mock LLM
    detector.llm.get_completion = AsyncMock(
        return_value="Consensus Protocols | Covers Raft and Paxos | Themes: fault tolerance | Rank: 8"
    )
    
    communities = [
        Community(id="c1", nodes=["n1", "n2"], level=0),
        Community(id="c2", nodes=["n3", "n4"], level=0),
    ]
    
    # Mock Neo4j queries
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda self, key: {"name": "Raft", "desc": "Consensus protocol"}.get(key, "")
    mock_record.get = lambda key, default=None: {"name": "Raft", "desc": "Consensus protocol"}.get(key, default)
    
    mock_result = MagicMock()
    mock_result.single.return_value = mock_record
    
    mock_session = MagicMock()
    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('src.core.indexing.community.get_connection') as mock_conn:
        mock_connection = MagicMock()
        mock_connection.connect = AsyncMock()
        mock_connection.session.return_value = mock_session
        mock_conn.return_value = mock_connection
        
        summarized = await detector._generate_summaries(communities)
    
    for community in summarized:
        assert community.summary is not None
        assert len(community.summary) > 0
