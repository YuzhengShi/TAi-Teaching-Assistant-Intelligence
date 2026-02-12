"""
Pytest fixtures for TAi tests.
"""

import pytest
import sqlite3
from pathlib import Path
from typing import Generator, Dict, Any
import json
from unittest.mock import AsyncMock, MagicMock

# Try to import testcontainers, but skip if unavailable
try:
    from testcontainers.neo4j import Neo4jContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False


@pytest.fixture(scope="session")
def neo4j_container():
    """Neo4j test container fixture."""
    if not HAS_TESTCONTAINERS:
        pytest.skip("testcontainers not available")
    
    with Neo4jContainer("neo4j:5.15-community") as container:
        yield container


@pytest.fixture
def neo4j_driver(neo4j_container):
    """Neo4j driver fixture."""
    if not HAS_TESTCONTAINERS:
        # Return mock driver for tests that don't need real Neo4j
        return MagicMock()
    
    from neo4j import GraphDatabase
    
    uri = neo4j_container.get_connection_url()
    driver = GraphDatabase.driver(uri, auth=("neo4j", neo4j_container.password))
    
    yield driver
    
    driver.close()


@pytest.fixture
def in_memory_db():
    """SQLite in-memory database fixture."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    yield conn
    conn.close()


@pytest.fixture
def mock_llm():
    """Mock LLM client that returns canned JSON."""
    mock = AsyncMock()
    
    def set_response(response_text: str):
        """Set the response text for the mock."""
        mock.get_completion.return_value = response_text
        mock.get_structured_completion.return_value = json.loads(response_text)
    
    # Default response
    mock.get_completion.return_value = '{"entities": [], "relationships": []}'
    mock.get_structured_completion.return_value = {"entities": [], "relationships": []}
    mock.set_response = set_response
    
    return mock


@pytest.fixture
def mock_embedding():
    """Mock embedding client."""
    mock = AsyncMock()
    
    # Return dummy embeddings (1536 dimensions)
    dummy_embedding = [0.1] * 1536
    mock.embed.return_value = dummy_embedding
    mock.cosine_similarity.return_value = 0.85
    
    return mock


@pytest.fixture
def test_data_dir(tmp_path):
    """Temporary test data directory."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_slide_pdf(test_data_dir):
    """Create a minimal test PDF fixture."""
    # This would create an actual PDF in a real implementation
    # For now, return path that test can check exists
    pdf_path = test_data_dir / "sample_slides.pdf"
    # In real tests, you'd use a library to create a minimal PDF
    pdf_path.touch()
    return pdf_path


@pytest.fixture
def sample_paper_pdf(test_data_dir):
    """Create a minimal test paper PDF fixture."""
    pdf_path = test_data_dir / "sample_paper.pdf"
    pdf_path.touch()
    return pdf_path


@pytest.fixture
def sample_transcript(test_data_dir):
    """Create a minimal test transcript fixture."""
    transcript_path = test_data_dir / "sample_transcript.txt"
    transcript_path.write_text(
        "Lecture 1: Introduction to Distributed Systems\n"
        "Today we'll cover MapReduce and consensus protocols.\n"
        "Let's start with the basics."
    )
    return transcript_path


@pytest.fixture
def sample_assignment(test_data_dir):
    """Create a minimal test assignment fixture."""
    assignment_path = test_data_dir / "sample_assignment.md"
    assignment_path.write_text(
        "# Assignment 1: MapReduce Implementation\n\n"
        "## Requirements\n"
        "- Implement Map and Reduce functions\n"
        "- Handle failure scenarios\n\n"
        "## Grading\n"
        "- Correctness: 50%\n"
        "- Code quality: 30%\n"
        "- Testing: 20%"
    )
    return assignment_path


@pytest.fixture
def sample_discussion(test_data_dir):
    """Create a minimal test discussion fixture."""
    discussion_path = test_data_dir / "sample_discussion.json"
    discussion_data = {
        "posts": [
            {
                "id": "post1",
                "author": "student_123",
                "content": "I don't understand how Raft handles leader failure.",
                "type": "question",
                "timestamp": "2024-01-15T10:00:00Z"
            },
            {
                "id": "post2",
                "author": "student_456",
                "content": "Raft uses a timeout mechanism to detect leader failure.",
                "type": "answer",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        ]
    }
    discussion_path.write_text(json.dumps(discussion_data, indent=2))
    return discussion_path


@pytest.fixture
def sample_code_file(test_data_dir):
    """Create a minimal test code file fixture."""
    code_path = test_data_dir / "sample_code.go"
    code_path.write_text(
        "package main\n\n"
        "// RaftLeader implements leader election in Raft protocol\n"
        "func RaftLeader() {\n"
        "    // Leader election logic\n"
        "}\n"
    )
    return code_path
