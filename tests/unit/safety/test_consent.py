"""
Tests for consent system with exact match validation.
"""

import pytest

from src.safety.consent import ConsentManager
from src.memory.store import SafeMemoryStore


def test_exact_consent_phrases_pass():
    """Test that exact consent phrases are accepted."""
    store = SafeMemoryStore()
    manager = ConsentManager(store)
    
    session_token = "token123"
    student_id = "test_student"
    
    # These should pass
    for phrase in ["I CONSENT", "I AGREE", "YES I CONSENT"]:
        result = manager.grant_consent(student_id, phrase, session_token)
        assert result["success"] is True


def test_case_insensitive_but_exact():
    """Test that case doesn't matter but exact phrase does."""
    store = SafeMemoryStore()
    manager = ConsentManager(store)
    
    session_token = "token123"
    student_id = "test_student2"
    
    # Case variations should work
    result = manager.grant_consent(student_id, "i consent", session_token)
    assert result["success"] is True
    
    result = manager.grant_consent(student_id, "I consent", session_token)
    assert result["success"] is True


def test_substring_matching_rejected():
    """Test that substring matches are rejected."""
    store = SafeMemoryStore()
    manager = ConsentManager(store)
    
    session_token = "token123"
    student_id = "test_student3"
    
    # These should FAIL (substring matching would pass, but we use exact match)
    invalid_phrases = [
        "I DO NOT CONSENT but I CONSENT",
        "I CONSENT to everything",
        "CONSENT",
        "I agree to terms",
        "YES",
    ]
    
    for phrase in invalid_phrases:
        with pytest.raises(Exception):  # Should raise ConsentRequiredError
            manager.grant_consent(student_id, phrase, session_token)


def test_session_token_binding():
    """Test that session tokens prevent replay attacks."""
    store = SafeMemoryStore()
    manager = ConsentManager(store)
    
    student_id = "test_student4"
    valid_token = "valid_token_123"
    invalid_token = "invalid_token_456"
    
    # First grant with valid token
    result = manager.grant_consent(student_id, "I CONSENT", valid_token)
    assert result["success"] is True
    
    # Try to reuse token from different session (should fail)
    manager.session_tokens.clear()  # Simulate new session
    with pytest.raises(Exception):  # Should raise SecurityViolationError
        manager.grant_consent(student_id, "I CONSENT", valid_token)


def test_consent_required_check():
    """Test that operations require consent."""
    store = SafeMemoryStore()
    manager = ConsentManager(store)
    
    student_id = "no_consent_student"
    
    # Should require consent
    requirement = manager.require_consent(student_id)
    assert requirement["required"] is True
    assert requirement["has_consent"] is False
