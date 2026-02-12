"""
System prompt builder: assembles bootstrap files + dynamic profile + tools.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from src.core.profile.cache import ProfileCache
from src.shared.tokens import count_tokens, truncate_to_tokens
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class PromptBuilder:
    """Build system prompts from bootstrap files and dynamic content."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.bootstrap_dir = Path(self.config.get("bootstrap_dir", "config/bootstrap"))
        self.max_chars_per_file = self.config.get("max_chars_per_file", 20000)
        
        self.profile_cache = ProfileCache()
        
        # Bootstrap files to load
        self.bootstrap_files = [
            "TEACHING_PROTOCOL.md",
            "TA_PERSONA.md",
            "TOOLS.md",
            "REVIEW_SCHEDULE.md",
            "INTERVIEW_PERSONA.md"  # Only for interview sessions
        ]
    
    async def build(
        self,
        student_id: str,
        topic: Optional[str],
        session_type: str,
        retrieval_context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Build complete system prompt.
        
        Returns:
            List of message dicts for LLM
        """
        system_parts = []
        
        # Load bootstrap files
        bootstrap_text = self._load_bootstrap_files(session_type)
        system_parts.append(bootstrap_text)
        
        # Generate/cache student profile
        profile = await self.profile_cache.get_profile(student_id, topic, session_type)
        if profile:
            system_parts.append(f"\n## Student Profile\n{profile}")
        
        # Add retrieval context if provided
        if retrieval_context:
            system_parts.append(f"\n## Relevant Course Content\n{retrieval_context}")
        
        # Combine and enforce token budget
        full_system = "\n\n".join(system_parts)
        
        # Token budget: ~3000 tokens for system prompt
        max_system_tokens = 3000
        if count_tokens(full_system) > max_system_tokens:
            full_system = truncate_to_tokens(
                full_system,
                max_system_tokens,
                suffix="\n\n[System prompt truncated]"
            )
        
        return [
            {"role": "system", "content": full_system}
        ]
    
    def _load_bootstrap_files(self, session_type: str) -> str:
        """Load bootstrap files with truncation."""
        parts = []
        
        # Filter files based on session type
        files_to_load = self.bootstrap_files.copy()
        if session_type != "interview":
            files_to_load = [f for f in files_to_load if f != "INTERVIEW_PERSONA.md"]
        
        for filename in files_to_load:
            filepath = self.bootstrap_dir / filename
            
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                
                # Truncate if too long (preserve head and tail)
                if len(content) > self.max_chars_per_file:
                    head_chars = self.max_chars_per_file // 2
                    tail_chars = self.max_chars_per_file - head_chars - 50  # Reserve for truncation marker
                    
                    truncated = (
                        content[:head_chars] +
                        "\n\n[... content truncated ...]\n\n" +
                        content[-tail_chars:]
                    )
                    status = "TRUNCATED"
                else:
                    truncated = content
                    status = "OK"
                
                parts.append(f"### {filename} [{status}]\n{truncated}")
            else:
                logger.warning(f"Bootstrap file not found: {filepath}")
                parts.append(f"### {filename} [MISSING]\nFile not found.")
        
        return "\n\n".join(parts)
