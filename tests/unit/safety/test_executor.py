"""
Tests for secure executor - CRITICAL: must verify shell=False.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from src.safety.executor import SecureExecutor


def test_shell_false_enforced():
    """CRITICAL TEST: Verify shell=False in all subprocess.run calls."""
    executor = SecureExecutor()
    
    with patch('subprocess.run') as mock_run:
        # Execute a valid command
        executor.execute("go test ./...")
        
        # Verify shell=False was passed
        assert mock_run.called
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("shell") is False, "shell=False MUST be enforced"
        
        # Verify tokens were passed as list
        call_args = mock_run.call_args[0]
        assert isinstance(call_args[0], list), "Command must be passed as list, not string"


def test_dangerous_commands_blocked():
    """Test that dangerous commands are blocked."""
    executor = SecureExecutor()
    
    dangerous_commands = [
        "rm -rf /",
        "rm -rf ../",
        "chmod 777 /etc/passwd",
        "dd if=/dev/zero of=/dev/sda",
        "nc -l 1234",
        "$(whoami)",
        "`rm -rf /`",
    ]
    
    for cmd in dangerous_commands:
        validation = executor.validate_command(cmd)
        assert validation["valid"] is False, f"Command should be blocked: {cmd}"


def test_allowlisted_commands_pass():
    """Test that allowlisted commands pass validation."""
    executor = SecureExecutor()
    
    allowed_commands = [
        "go test ./...",
        "go build",
        "python3 script.py",
        "docker ps",
        "docker logs container_id",
        "aws s3 ls",
        "terraform plan",
    ]
    
    for cmd in allowed_commands:
        validation = executor.validate_command(cmd)
        assert validation["valid"] is True, f"Command should be allowed: {cmd}"


def test_path_traversal_blocked():
    """Test that path traversal attempts are blocked."""
    executor = SecureExecutor()
    
    traversal_commands = [
        "../etc/passwd",
        "..\\windows\\system32",
        "../../../etc/passwd",
    ]
    
    for cmd in traversal_commands:
        validation = executor.validate_command(f"cat {cmd}")
        assert validation["valid"] is False, f"Path traversal should be blocked: {cmd}"


def test_command_substitution_blocked():
    """Test that command substitution is blocked."""
    executor = SecureExecutor()
    
    substitution_commands = [
        "$(rm -rf /)",
        "`whoami`",
        "$(cat /etc/passwd)",
    ]
    
    for cmd in substitution_commands:
        validation = executor.validate_command(cmd)
        assert validation["valid"] is False, f"Command substitution should be blocked: {cmd}"


def test_resource_limits_set():
    """Test that resource limits are set via preexec_fn."""
    executor = SecureExecutor()
    
    with patch('subprocess.run') as mock_run:
        executor.execute("go test")
        
        # Verify preexec_fn was provided
        call_kwargs = mock_run.call_args[1]
        assert "preexec_fn" in call_kwargs, "Resource limits must be set via preexec_fn"
        assert call_kwargs["preexec_fn"] is not None
