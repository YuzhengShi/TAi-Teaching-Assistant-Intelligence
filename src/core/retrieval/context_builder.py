"""
Build formatted context from retrieval results.
Respects token budget and includes source citations.
"""

from typing import List, Optional, Dict
from dataclasses import dataclass

from src.core.retrieval.local_search import RetrievalResult
from src.shared.tokens import count_tokens, truncate_to_tokens
from src.shared.config import settings


class ContextBuilder:
    """Build LLM context from retrieval results."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.token_budget = self.config.get("token_budget", settings.retrieval.max_context_tokens)
    
    def build(
        self,
        results: List[RetrievalResult],
        token_budget: Optional[int] = None
    ) -> str:
        """
        Assemble retrieval results into formatted context string.
        
        Args:
            results: List of RetrievalResult objects
            token_budget: Override default token budget
        
        Returns:
            Formatted context string with citations
        """
        token_budget = token_budget or self.token_budget
        
        context_parts = []
        total_tokens = 0
        
        # Sort by score (highest first)
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        
        for i, result in enumerate(sorted_results):
            # Format result with citation
            formatted = self._format_result(result, citation_num=i + 1)
            result_tokens = count_tokens(formatted)
            
            # Check if adding this result would exceed budget
            if total_tokens + result_tokens > token_budget:
                # Try to truncate this result
                remaining = token_budget - total_tokens
                if remaining > 100:  # Only if meaningful space
                    formatted = truncate_to_tokens(formatted, remaining)
                    context_parts.append(formatted)
                break
            
            context_parts.append(formatted)
            total_tokens += result_tokens
        
        return "\n\n".join(context_parts)
    
    def _format_result(self, result: RetrievalResult, citation_num: int) -> str:
        """Format a single result with citation."""
        parts = [f"[Source {citation_num}: {result.source}]"]
        parts.append(result.text)
        
        if result.entities_involved:
            parts.append(f"\nEntities: {', '.join(result.entities_involved[:5])}")
        
        return "\n".join(parts)
