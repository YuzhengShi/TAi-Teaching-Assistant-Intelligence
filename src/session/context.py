"""
Context window manager for TAi sessions.
Manages token budget allocation across system prompt, retrieval, and history.
"""

from typing import List, Dict, Any, Optional

from src.shared.tokens import count_tokens, truncate_to_tokens
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


# Token budget allocation
BUDGET = {
    "system_prompt": 3000,
    "student_profile": 1000,
    "retrieval_context": 4000,
    "conversation_history": 8000,
    "current_turn": 500,
    "response_reserve": 4000,
}


class ContextManager:
    """Manages context window for LLM calls."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.total_budget = self.config.get("total_budget", 20000)
        self.budget = {**BUDGET, **(self.config.get("budget", {}))}
    
    def build_context(
        self,
        session: Dict[str, Any],
        retrieval_results: List[Dict[str, Any]],
        student_profile: str,
        system_prompt: str
    ) -> List[Dict[str, str]]:
        """
        Assemble full LLM context within token budget.
        
        Args:
            session: Session with messages
            retrieval_results: Retrieved context items
            student_profile: Markdown student profile
            system_prompt: Base system prompt
        
        Returns:
            List of message dicts for LLM
        """
        messages = []
        
        # System prompt (truncate if needed)
        system_content = self._build_system_content(
            system_prompt, student_profile, retrieval_results
        )
        messages.append({"role": "system", "content": system_content})
        
        # Conversation history (prune old retrieval results)
        history = session.get("messages", [])
        pruned_history = self._prune_history(
            history,
            max_tokens=self.budget["conversation_history"]
        )
        messages.extend(pruned_history)
        
        return messages
    
    def _build_system_content(
        self,
        base_prompt: str,
        profile: str,
        retrieval_results: List[Dict[str, Any]]
    ) -> str:
        """Build system content within budget."""
        parts = [base_prompt]
        remaining = self.budget["system_prompt"]
        
        # Add profile
        if profile:
            profile_truncated = truncate_to_tokens(
                profile, self.budget["student_profile"]
            )
            parts.append(f"\n## Student Profile\n{profile_truncated}")
        
        # Add retrieval context
        if retrieval_results:
            retrieval_texts = []
            retrieval_budget = self.budget["retrieval_context"]
            current_tokens = 0
            
            for result in retrieval_results:
                text = result.get("text", "")
                tokens = count_tokens(text)
                
                if current_tokens + tokens > retrieval_budget:
                    # Truncate last item
                    remaining_budget = retrieval_budget - current_tokens
                    if remaining_budget > 100:
                        text = truncate_to_tokens(text, remaining_budget)
                        retrieval_texts.append(text)
                    break
                
                retrieval_texts.append(text)
                current_tokens += tokens
            
            if retrieval_texts:
                parts.append(
                    "\n## Relevant Course Content\n" + "\n\n".join(retrieval_texts)
                )
        
        full = "\n\n".join(parts)
        
        # Final truncation if over total system budget
        max_system = self.budget["system_prompt"] + self.budget["student_profile"] + self.budget["retrieval_context"]
        if count_tokens(full) > max_system:
            full = truncate_to_tokens(full, max_system)
        
        return full
    
    def _prune_history(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """
        Prune conversation history to fit budget.
        Strategy: keep recent messages, prune old retrieval results.
        """
        if not messages:
            return []
        
        # Work backwards from most recent
        pruned = []
        total_tokens = 0
        
        for msg in reversed(messages):
            content = msg.get("content", "")
            role = msg.get("role", "user")
            tokens = count_tokens(content)
            
            if total_tokens + tokens > max_tokens:
                # Try truncation for the last fitting message
                remaining = max_tokens - total_tokens
                if remaining > 100:
                    content = truncate_to_tokens(content, remaining)
                    pruned.append({"role": role, "content": content})
                break
            
            pruned.append({"role": role, "content": content})
            total_tokens += tokens
        
        # Reverse to restore chronological order
        pruned.reverse()
        return pruned
