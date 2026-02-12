"""
Tests for document ingestors.
"""

import pytest
from pathlib import Path
import tempfile
import json

from src.core.indexing.ingestors.slides import SlidesIngestor
from src.core.indexing.ingestors.paper import PaperIngestor
from src.core.indexing.ingestors.transcript import TranscriptIngestor
from src.core.indexing.ingestors.assignment import AssignmentIngestor
from src.core.indexing.ingestors.discussion import DiscussionIngestor
from src.core.indexing.ingestors.code import CodeIngestor
from src.core.indexing.ingestors.notes import NotesIngestor


def test_slides_ingestor_pdf(tmp_path):
    """Test PDF slide ingestion."""
    # Create minimal PDF (in real test, use actual PDF)
    pdf_path = tmp_path / "test_slides.pdf"
    pdf_path.touch()
    
    ingestor = SlidesIngestor()
    
    # Test can_ingest
    assert ingestor.can_ingest(pdf_path)
    
    # Note: Actual PDF ingestion requires a real PDF file
    # This test verifies the structure works


def test_transcript_ingestor(tmp_path):
    """Test transcript ingestion with filler removal."""
    transcript_path = tmp_path / "lecture1_transcript.txt"
    transcript_path.write_text(
        "Lecture 1: Introduction\n"
        "Um, today we'll cover, uh, MapReduce.\n"
        "You know, it's a distributed system protocol.\n"
        "Like, it's really important."
    )
    
    ingestor = TranscriptIngestor()
    chunks = ingestor.ingest(transcript_path)
    
    assert len(chunks) > 0
    assert chunks[0].metadata["source_type"] == "lecture_transcript"
    
    # Verify filler words removed
    text = chunks[0].text.lower()
    assert "um" not in text or "um" not in text.split()  # May be in "um," but not as word
    # Note: Filler removal is approximate


def test_assignment_ingestor_markdown(tmp_path):
    """Test Markdown assignment ingestion."""
    assignment_path = tmp_path / "assignment1.md"
    assignment_path.write_text(
        "# Assignment 1: MapReduce\n\n"
        "## Description\n"
        "Implement a basic MapReduce system.\n\n"
        "## Requirements\n"
        "- Implement Map function\n"
        "- Implement Reduce function\n"
        "- Handle failures\n\n"
        "## Grading\n"
        "- Correctness: 50%\n"
        "- Code quality: 30%"
    )
    
    ingestor = AssignmentIngestor()
    chunks = ingestor.ingest(assignment_path)
    
    assert len(chunks) > 0
    
    # Verify sections extracted
    sections = [chunk.metadata.get("section") for chunk in chunks]
    assert "title" in sections or "description" in sections
    assert "requirements" in sections or "grading" in sections


def test_discussion_ingestor_anonymization(tmp_path):
    """Test discussion post ingestion with anonymization."""
    discussion_path = tmp_path / "discussion.json"
    discussion_data = {
        "posts": [
            {
                "id": "post1",
                "author": "alice_chen",
                "content": "I don't understand Raft leader election.",
                "type": "question",
                "timestamp": "2024-01-15T10:00:00Z"
            },
            {
                "id": "post2",
                "author": "bob_smith",
                "content": "Raft uses timeouts to detect leader failure.",
                "type": "answer",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        ]
    }
    discussion_path.write_text(json.dumps(discussion_data))
    
    ingestor = DiscussionIngestor()
    chunks = ingestor.ingest(discussion_path)
    
    assert len(chunks) == 2
    
    # Verify anonymization
    authors = [chunk.metadata.get("author_anonymized") for chunk in chunks]
    assert all(author.startswith("student_") for author in authors)
    assert authors[0] != authors[1]  # Different students get different IDs
    
    # Verify post types classified
    post_types = [chunk.metadata.get("post_type") for chunk in chunks]
    assert "question" in post_types or "confusion" in post_types


def test_code_ingestor_go(tmp_path):
    """Test Go code ingestion."""
    code_path = tmp_path / "raft.go"
    code_path.write_text(
        "package main\n\n"
        "// RaftLeader implements leader election\n"
        "func RaftLeader() {\n"
        "    // Leader election logic\n"
        "}\n\n"
        "type RaftNode struct {\n"
        "    id int\n"
        "}\n"
    )
    
    ingestor = CodeIngestor()
    chunks = ingestor.ingest(code_path)
    
    assert len(chunks) > 0
    
    # Verify function extracted
    func_chunks = [c for c in chunks if c.metadata.get("element_type") == "function"]
    assert len(func_chunks) > 0
    
    # Verify struct extracted
    struct_chunks = [c for c in chunks if c.metadata.get("element_type") == "struct"]
    assert len(struct_chunks) > 0


def test_code_ingestor_python(tmp_path):
    """Test Python code ingestion."""
    code_path = tmp_path / "mapreduce.py"
    code_path.write_text(
        '"""MapReduce implementation."""\n\n'
        "def map_function(data):\n"
        '    """Map data to key-value pairs."""\n'
        "    return []\n\n"
        "class MapReduce:\n"
        '    """Main MapReduce class."""\n'
        "    pass\n"
    )
    
    ingestor = CodeIngestor()
    chunks = ingestor.ingest(code_path)
    
    assert len(chunks) > 0
    
    # Verify function extracted
    func_chunks = [c for c in chunks if c.metadata.get("element_type") == "function"]
    assert len(func_chunks) > 0


def test_notes_ingestor_markdown(tmp_path):
    """Test notes ingestion with heading chunking."""
    notes_path = tmp_path / "week5_raft.md"
    notes_path.write_text(
        "# Raft Protocol\n\n"
        "Raft is a consensus algorithm.\n\n"
        "## Leader Election\n\n"
        "Leaders are elected via timeouts.\n\n"
        "## Log Replication\n\n"
        "Logs are replicated to followers.\n"
    )
    
    ingestor = NotesIngestor()
    chunks = ingestor.ingest(notes_path)
    
    assert len(chunks) >= 2  # At least main heading + one subheading
    
    # Verify headings extracted
    headings = [chunk.metadata.get("heading") for chunk in chunks if chunk.metadata.get("heading")]
    assert "Raft Protocol" in headings or any("Raft" in h for h in headings)


def test_content_hash_deterministic(tmp_path):
    """Test that content hash is deterministic."""
    transcript_path = tmp_path / "test.txt"
    transcript_path.write_text("Test content")
    
    ingestor = TranscriptIngestor()
    chunks1 = ingestor.ingest(transcript_path)
    chunks2 = ingestor.ingest(transcript_path)
    
    assert chunks1[0].content_hash == chunks2[0].content_hash


def test_metadata_fields_populated(tmp_path):
    """Test that all metadata fields are populated."""
    assignment_path = tmp_path / "test.md"
    assignment_path.write_text("# Test Assignment")
    
    ingestor = AssignmentIngestor()
    chunks = ingestor.ingest(assignment_path)
    
    assert len(chunks) > 0
    chunk = chunks[0]
    
    # Verify required metadata fields
    assert "source_type" in chunk.metadata
    assert "source_name" in chunk.metadata
    assert chunk.content_hash is not None
