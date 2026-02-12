"""
Tests for entity resolution.
"""

import pytest
from unittest.mock import AsyncMock

from src.core.indexing.resolver import EntityResolver, ResolvedEntity
from src.core.indexing.extractor import Entity


@pytest.fixture
def mock_embedding():
    """Mock embedding client."""
    mock = AsyncMock()
    
    # Mock cosine similarity
    def cosine_sim(vec1, vec2):
        # Simulate: "Raft" and "Raft consensus" are similar
        if "raft" in str(vec1).lower() and "raft" in str(vec2).lower():
            return 0.90
        # "Raft" and "Paxos" are different
        if "raft" in str(vec1).lower() and "paxos" in str(vec2).lower():
            return 0.30
        return 0.50
    
    mock.cosine_similarity = cosine_sim
    mock.embed.return_value = [[0.1] * 1536]  # Dummy embedding
    
    return mock


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    mock = AsyncMock()
    # Default: entities are the same
    mock.get_completion.return_value = "YES - These refer to the same concept."
    return mock


@pytest.mark.asyncio
async def test_exact_match_handles_case_and_whitespace(mock_embedding, mock_llm):
    """Test that exact match handles case and whitespace variations."""
    entities = [
        Entity(name="Raft", type="PROTOCOL", description="Consensus algorithm"),
        Entity(name="RAFT", type="PROTOCOL", description="Consensus protocol"),
        Entity(name="  Raft  ", type="PROTOCOL", description="Distributed consensus"),
    ]
    
    resolver = EntityResolver()
    resolver.embedding_client = mock_embedding
    resolver.llm = mock_llm
    
    resolved = await resolver.resolve(entities)
    
    # Should merge all three into one
    assert len(resolved) == 1
    assert resolved[0].canonical_name.lower() == "raft"
    assert len(resolved[0].descriptions) == 3


@pytest.mark.asyncio
async def test_embedding_tier_catches_similar_names(mock_embedding, mock_llm):
    """Test that embedding similarity catches 'Raft consensus' ≈ 'Raft protocol'."""
    # Mock embedding to return high similarity for Raft variants
    async def mock_embed(texts):
        # Return same embedding for Raft variants, different for Paxos
        embeddings = []
        for text in texts:
            if "raft" in text.lower():
                embeddings.append([0.9] * 1536)
            else:
                embeddings.append([0.1] * 1536)
        return embeddings if len(texts) > 1 else embeddings[0]
    
    mock_embedding.embed = mock_embed
    
    entities = [
        Entity(name="Raft", type="PROTOCOL", description="Consensus"),
        Entity(name="Raft consensus algorithm", type="PROTOCOL", description="Consensus protocol"),
        Entity(name="Paxos", type="PROTOCOL", description="Alternative consensus"),
    ]
    
    resolver = EntityResolver()
    resolver.embedding_client = mock_embedding
    resolver.llm = mock_llm
    
    resolved = await resolver.resolve(entities)
    
    # Raft variants should merge, Paxos should remain separate
    raft_entities = [r for r in resolved if "raft" in r.canonical_name.lower()]
    paxos_entities = [r for r in resolved if "paxos" in r.canonical_name.lower()]
    
    assert len(raft_entities) == 1
    assert len(paxos_entities) == 1
    assert raft_entities[0].canonical_name != paxos_entities[0].canonical_name


@pytest.mark.asyncio
async def test_llm_tier_resolves_brewer_cap_theorem(mock_embedding, mock_llm):
    """Test that LLM tier resolves 'Brewer's theorem' ≈ 'CAP theorem'."""
    # Mock LLM to say these are the same
    mock_llm.get_completion.return_value = "YES - Brewer's theorem is the same as CAP theorem."
    
    entities = [
        Entity(name="Brewer's theorem", type="THEOREM", description="CAP theorem"),
        Entity(name="CAP theorem", type="THEOREM", description="Consistency, Availability, Partition tolerance"),
        Entity(name="Brewer's CAP theorem", type="THEOREM", description="Distributed systems theorem"),
    ]
    
    resolver = EntityResolver()
    resolver.embedding_client = mock_embedding
    resolver.llm = mock_llm
    
    resolved = await resolver.resolve(entities)
    
    # Should merge into one
    assert len(resolved) == 1
    # Canonical name should be one of the variants
    assert "cap" in resolved[0].canonical_name.lower() or "brewer" in resolved[0].canonical_name.lower()


@pytest.mark.asyncio
async def test_non_matches_preserved(mock_embedding, mock_llm):
    """Test that non-matching entities remain separate."""
    # Mock LLM to say Raft and Paxos are different
    def llm_response(prompt):
        if "Raft" in prompt and "Paxos" in prompt:
            return "NO - Raft and Paxos are different consensus protocols."
        return "YES - These are the same."
    
    mock_llm.get_completion.side_effect = lambda p: llm_response(p)
    
    entities = [
        Entity(name="Raft", type="PROTOCOL", description="Consensus"),
        Entity(name="Paxos", type="PROTOCOL", description="Consensus"),
    ]
    
    resolver = EntityResolver()
    resolver.embedding_client = mock_embedding
    resolver.llm = mock_llm
    
    resolved = await resolver.resolve(entities)
    
    # Should remain separate
    assert len(resolved) == 2
    names = {r.canonical_name for r in resolved}
    assert "Raft" in names or any("raft" in n.lower() for n in names)
    assert "Paxos" in names or any("paxos" in n.lower() for n in names)


def test_merged_entities_track_source_chunks():
    """Test that merged entities track all source chunk references."""
    # This would be tested in integration, but verify structure
    resolved = ResolvedEntity(
        canonical_name="Raft",
        type="PROTOCOL",
        descriptions=["Consensus algorithm"],
        source_chunks={"hash1", "hash2", "hash3"},
        aliases={"Raft protocol", "Raft consensus"}
    )
    
    assert len(resolved.source_chunks) == 3
    assert "hash1" in resolved.source_chunks
    assert len(resolved.aliases) == 2
