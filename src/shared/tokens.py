"""
Token counting and truncation utilities using tiktoken.
"""

from typing import Optional
import tiktoken

from src.shared.config import settings


def get_encoding(model: Optional[str] = None) -> tiktoken.Encoding:
    """
    Get tiktoken encoding for a model.
    
    Args:
        model: Model name (e.g., "gpt-4", "gpt-3.5-turbo")
               If None, uses default from settings
    
    Returns:
        tiktoken Encoding object
    """
    model = model or settings.llm.default_model
    
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return encoding


def count_tokens(text: str, model: Optional[str] = None) -> int:
    """
    Count tokens in text.
    
    Args:
        text: Text to count
        model: Model name for encoding selection
    
    Returns:
        Number of tokens
    """
    encoding = get_encoding(model)
    return len(encoding.encode(text))


def truncate_to_tokens(
    text: str,
    max_tokens: int,
    model: Optional[str] = None,
    suffix: str = "..."
) -> str:
    """
    Truncate text to maximum token count.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        model: Model name for encoding selection
        suffix: Suffix to append if truncated
    
    Returns:
        Truncated text
    """
    encoding = get_encoding(model)
    tokens = encoding.encode(text)
    
    if len(tokens) <= max_tokens:
        return text
    
    # Truncate and decode
    truncated_tokens = tokens[:max_tokens]
    truncated_text = encoding.decode(truncated_tokens)
    
    # Remove partial tokens at the end if suffix is added
    if suffix:
        # Reserve space for suffix
        suffix_tokens = count_tokens(suffix, model)
        if max_tokens > suffix_tokens:
            truncated_tokens = tokens[:max_tokens - suffix_tokens]
            truncated_text = encoding.decode(truncated_tokens) + suffix
        else:
            truncated_text = suffix
    
    return truncated_text


def estimate_tokens(text: str) -> int:
    """
    Quick token estimation (4 chars per token approximation).
    Use for rough estimates when exact count is expensive.
    
    Args:
        text: Text to estimate
    
    Returns:
        Estimated token count
    """
    return len(text) // 4
