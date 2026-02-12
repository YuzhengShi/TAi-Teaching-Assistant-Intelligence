"""
Secure code executor with shell=False and command validation.
Cross-platform compatible.
"""

import subprocess
import shlex
import re
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path
import tempfile

from src.shared.exceptions import SecurityViolationError
from src.shared.logging import get_logger

logger = get_logger(__name__)

_IS_WINDOWS = sys.platform == "win32"


class SecureExecutor:
    """Secure command execution with validation and resource limits."""
    
    # Allowlist: commands that are allowed
    ALLOWLIST = [
        "go", "python3", "python", "docker", "aws", "terraform", "locust"
    ]
    
    # Denylist patterns: commands that are blocked
    DENYLIST_PATTERNS = [
        r'rm\s+-rf',       # Dangerous deletion
        r'chmod\s+[0-7]{3,4}',  # Permission changes
        r'chown',          # Ownership changes
        r'\bdd\b',         # Disk operations
        r'\bnc\b|\bnetcat\b',  # Network tools
        r'\$\(',           # Command substitution $()
        r'`[^`]+`',        # Command substitution backticks
        r'\.\./',          # Path traversal
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.access_tier = self.config.get("access_tier", "read_only")
    
    def validate_command(self, command: str) -> Dict[str, Any]:
        """
        Validate command against allowlist and denylist.
        
        Returns:
            ValidationResult dict
        """
        # Parse command
        try:
            tokens = shlex.split(command)
        except ValueError as e:
            return {
                "valid": False,
                "error": f"Invalid command syntax: {str(e)}"
            }
        
        if not tokens:
            return {"valid": False, "error": "Empty command"}
        
        command_name = tokens[0]
        command_base = Path(command_name).name  # Get basename
        
        # Check allowlist
        if command_base not in self.ALLOWLIST:
            return {
                "valid": False,
                "error": f"Command '{command_base}' not in allowlist",
                "allowed_commands": self.ALLOWLIST
            }
        
        # Check denylist patterns
        for pattern in self.DENYLIST_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "valid": False,
                    "error": f"Command matches blocked pattern: {pattern}"
                }
        
        # Check path traversal in all tokens
        for token in tokens:
            if '../' in token or '..\\' in token:
                return {
                    "valid": False,
                    "error": "Path traversal detected"
                }
        
        return {"valid": True, "command": command, "tokens": tokens}
    
    def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Execute command securely.
        
        Args:
            command: Command to execute
            timeout: Execution timeout in seconds
            cwd: Working directory
        
        Returns:
            ExecutionResult dict
        
        Raises:
            SecurityViolationError if command is invalid
        """
        # Validate command
        validation = self.validate_command(command)
        if not validation["valid"]:
            raise SecurityViolationError(validation["error"])
        
        tokens = validation["tokens"]
        
        # Create temporary sandbox directory
        sandbox_dir = cwd or Path(tempfile.mkdtemp(prefix="tai_sandbox_"))
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            run_kwargs: Dict[str, Any] = {
                "capture_output": True,
                "timeout": timeout,
                "cwd": str(sandbox_dir),
                "text": True,
            }
            
            # Set resource limits on Unix only
            if not _IS_WINDOWS:
                import resource
                
                def set_limits():
                    # CPU time limit
                    resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
                    # Memory limit (512MB)
                    resource.setrlimit(
                        resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024)
                    )
                    # File size limit (100MB)
                    resource.setrlimit(
                        resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024)
                    )
                
                run_kwargs["preexec_fn"] = set_limits
            
            # Execute with shell=False (CRITICAL SECURITY REQUIREMENT)
            process = subprocess.run(
                tokens,         # Pass as list, not string
                shell=False,    # NEVER shell=True
                **run_kwargs
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "return_code": process.returncode,
                "command": command
            }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "command": command
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command
            }
        finally:
            # Cleanup sandbox (in production, might want to keep for debugging)
            pass
