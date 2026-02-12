"""
Tests for system prompt builder.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.core.prompt.builder import PromptBuilder


def test_bootstrap_files_loaded(tmp_path):
    """Test that bootstrap files are loaded."""
    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir()
    
    # Create test bootstrap file
    (bootstrap_dir / "TEACHING_PROTOCOL.md").write_text("# Teaching Protocol\n\nContent here")
    
    builder = PromptBuilder({"bootstrap_dir": str(bootstrap_dir)})
    
    content = builder._load_bootstrap_files("general")
    
    assert "Teaching Protocol" in content
    assert "Content here" in content


def test_bootstrap_truncation_preserves_head_tail(tmp_path):
    """Test that truncation preserves beginning and end."""
    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir()
    
    # Create long file
    long_content = "BEGINNING\n" + "MIDDLE LINE\n" * 1000 + "END"
    (bootstrap_dir / "TEST.md").write_text(long_content)
    
    builder = PromptBuilder({
        "bootstrap_dir": str(bootstrap_dir),
        "max_chars_per_file": 100
    })
    
    content = builder._load_bootstrap_files("general")
    
    # Should have beginning and end
    assert "BEGINNING" in content
    assert "END" in content
    assert "[... content truncated ...]" in content


@pytest.mark.asyncio
async def test_profile_injected_into_prompt():
    """Test that student profile is injected into system prompt."""
    builder = PromptBuilder()
    
    # Mock profile cache
    mock_profile = "# Student Profile\n## Concepts: Raft"
    builder.profile_cache.get_profile = AsyncMock(return_value=mock_profile)
    
    messages = await builder.build("student1", "Raft", "study")
    
    assert len(messages) == 1
    assert "system" == messages[0]["role"]
    assert "Student Profile" in messages[0]["content"]
    assert "Raft" in messages[0]["content"]


@pytest.mark.asyncio
async def test_token_budget_enforced():
    """Test that system prompt respects token budget."""
    builder = PromptBuilder()
    
    # Create very long content
    long_content = "X" * 50000  # Way over 3000 token budget
    
    with patch.object(builder, '_load_bootstrap_files', return_value=long_content):
        with patch.object(builder.profile_cache, 'get_profile', new_callable=AsyncMock, return_value=""):
            messages = await builder.build("student1", None, "general")
            
            # Should be truncated
            from src.shared.tokens import count_tokens
            assert count_tokens(messages[0]["content"]) <= 3000


def test_missing_bootstrap_file_doesnt_crash(tmp_path):
    """Test that missing bootstrap file doesn't crash."""
    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir()
    
    builder = PromptBuilder({"bootstrap_dir": str(bootstrap_dir)})
    
    # Should not crash
    content = builder._load_bootstrap_files("general")
    
    assert "MISSING" in content or len(content) >= 0
