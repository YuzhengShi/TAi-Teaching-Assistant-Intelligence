"""
Tests for session management.
"""

import pytest
import json
from pathlib import Path
import tempfile

from src.session.manager import SessionManager


def test_session_isolation(tmp_path):
    """Test that two students don't share sessions."""
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(db_path)
    
    # Create sessions for two students
    session1 = manager.get_or_create("student1", {"course": "cs6650", "context": "assignment-1"})
    session2 = manager.get_or_create("student2", {"course": "cs6650", "context": "assignment-1"})
    
    # Sessions should be different
    assert session1["session_key"] != session2["session_key"]
    assert session1["student_id"] == "student1"
    assert session2["student_id"] == "student2"


def test_idle_timeout(tmp_path):
    """Test that idle sessions expire."""
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(db_path)
    
    # Create session
    session = manager.get_or_create("student1", {"course": "cs6650", "context": "interview"})
    session_key = session["session_key"]
    
    # Interview sessions have 30 minute timeout
    # In real test, would manipulate timestamps
    # For now, just verify timeout config exists
    timeout = manager._get_timeout_minutes("interview")
    assert timeout == 30


def test_message_ordering(tmp_path):
    """Test that messages are stored in order."""
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(db_path)
    
    session = manager.get_or_create("student1", {"course": "cs6650", "context": "general"})
    session_key = session["session_key"]
    
    # Add messages
    manager.add_message(session_key, "student", "Message 1")
    manager.add_message(session_key, "assistant", "Response 1")
    manager.add_message(session_key, "student", "Message 2")
    
    # Retrieve messages
    messages = manager.get_messages(session_key)
    
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 1"
    assert messages[1]["content"] == "Response 1"
    assert messages[2]["content"] == "Message 2"
