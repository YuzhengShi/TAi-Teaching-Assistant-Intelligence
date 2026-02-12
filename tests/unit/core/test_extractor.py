"""
Tests for entity/relationship extraction.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from src.core.indexing.extractor import EntityRelationshipExtractor, Entity, Relationship
from src.core.indexing.ingestors.base import DocumentChunk


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    mock = AsyncMock()
    
    # Default response for Raft paragraph
    mock.get_structured_completion.return_value = {
        "entities": [
            {
                "name": "Raft",
                "type": "PROTOCOL",
                "description": "Consensus algorithm"
            },
            {
                "name": "leader election",
                "type": "ALGORITHM",
                "description": "Process of selecting a leader"
            }
        ],
        "relationships": [
            {
                "source": "Raft",
                "target": "leader election",
                "type": "IMPLEMENTS",
                "description": "Raft implements leader election"
            }
        ]
    }
    
    return mock


@pytest.mark.asyncio
async def test_extract_entities_from_raft_paragraph(mock_llm):
    """Test extraction from known Raft paragraph."""
    chunk = DocumentChunk(
        text="Raft is a consensus protocol that implements leader election for distributed systems.",
        metadata={"source_type": "lecture_slide"}
    )
    
    extractor = EntityRelationshipExtractor()
    extractor.llm = mock_llm
    
    result = await extractor.extract(chunk)
    
    assert len(result.entities) > 0
    assert any(e.name == "Raft" for e in result.entities)
    assert any(e.name == "leader election" for e in result.entities)
    
    assert len(result.relationships) > 0
    assert any(
        r.source == "Raft" and r.target == "leader election" and r.type == "IMPLEMENTS"
        for r in result.relationships
    )


@pytest.mark.asyncio
async def test_validate_entity_types(mock_llm):
    """Test that invalid entity types are rejected."""
    # Mock LLM returning invalid type
    mock_llm.get_structured_completion.return_value = {
        "entities": [
            {
                "name": "Test",
                "type": "INVALID_TYPE",
                "description": "Test entity"
            }
        ],
        "relationships": []
    }
    
    chunk = DocumentChunk(text="Test content")
    extractor = EntityRelationshipExtractor()
    extractor.llm = mock_llm
    
    result = await extractor.extract(chunk)
    
    # Invalid type should be converted to CONCEPT
    assert len(result.entities) > 0
    assert result.entities[0].type == "CONCEPT"


@pytest.mark.asyncio
async def test_json_parse_failure_handling(mock_llm):
    """Test that JSON parse failures are handled gracefully."""
    # Mock LLM returning invalid JSON
    mock_llm.get_structured_completion.side_effect = [
        json.JSONDecodeError("Invalid JSON", "", 0),
        "Some text response"
    ]
    mock_llm.get_completion.return_value = '{"entities": [], "relationships": []}'
    
    chunk = DocumentChunk(text="Test content")
    extractor = EntityRelationshipExtractor()
    extractor.llm = mock_llm
    
    result = await extractor.extract(chunk)
    
    # Should return empty result with error
    assert len(result.extraction_errors) > 0
    assert len(result.entities) == 0  # Or partial results if retry succeeds


@pytest.mark.asyncio
async def test_gleanings_produces_more_entities(mock_llm):
    """Test that gleanings finds additional entities."""
    # First extraction
    mock_llm.get_structured_completion.side_effect = [
        {
            "entities": [{"name": "Raft", "type": "PROTOCOL", "description": "Consensus"}],
            "relationships": []
        },
        {
            "entities": [{"name": "Paxos", "type": "PROTOCOL", "description": "Alternative"}],
            "relationships": [
                {"source": "Raft", "target": "Paxos", "type": "ALTERNATIVE_TO", "description": ""}
            ]
        }
    ]
    
    chunk = DocumentChunk(
        text="Raft is a consensus protocol. Paxos is an alternative."
    )
    extractor = EntityRelationshipExtractor()
    extractor.llm = mock_llm
    
    result = await extractor.extract_with_gleanings(chunk, max_rounds=2)
    
    # Should have entities from both rounds
    assert len(result.entities) >= 2
    assert any(e.name == "Raft" for e in result.entities)
    assert any(e.name == "Paxos" for e in result.entities)
    assert len(result.relationships) > 0


def test_entity_validation():
    """Test entity type validation against schema."""
    extractor = EntityRelationshipExtractor()
    
    # Valid types should pass
    valid_entity = Entity(name="Test", type="CONCEPT", description="Test")
    assert valid_entity.type in extractor.allowed_entity_types
    
    # Invalid types should be caught
    invalid_entities = [
        Entity(name="Test", type="INVALID", description="Test")
    ]
    parsed = extractor._parse_entities(
        [{"name": "Test", "type": "INVALID", "description": "Test"}],
        None
    )
    # Should convert to CONCEPT
    assert parsed[0].type == "CONCEPT"
