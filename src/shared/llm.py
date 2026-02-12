"""
LLM client abstraction supporting OpenAI and Anthropic.
Provides async completion with structured JSON output support.
"""

import json
from typing import Optional, Dict, Any, List, Literal
from enum import Enum

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from src.shared.config import settings
from src.shared.exceptions import TAiError


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMError(TAiError):
    """Base error for LLM operations."""
    pass


class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2000
    ):
        self.provider = provider or settings.llm.provider
        self.model = model or settings.llm.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Initialize provider client
        if self.provider == LLMProvider.OPENAI:
            api_key = api_key or settings.llm.openai_api_key
            if not api_key:
                raise LLMError("OpenAI API key not configured")
            self.client = AsyncOpenAI(api_key=api_key)
        elif self.provider == LLMProvider.ANTHROPIC:
            api_key = api_key or settings.llm.anthropic_api_key
            if not api_key:
                raise LLMError("Anthropic API key not configured")
            self.client = AsyncAnthropic(api_key=api_key)
        else:
            raise LLMError(f"Unsupported provider: {self.provider}")
    
    async def get_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Get text completion from LLM.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            response_format: For structured output (OpenAI) or JSON schema (Anthropic)
            **kwargs: Additional provider-specific parameters
        
        Returns:
            Completion text
        """
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens
        
        try:
            if self.provider == LLMProvider.OPENAI:
                return await self._openai_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    **kwargs
                )
            elif self.provider == LLMProvider.ANTHROPIC:
                return await self._anthropic_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    **kwargs
                )
        except Exception as e:
            raise LLMError(f"LLM completion failed: {str(e)}") from e
    
    async def _openai_completion(
        self,
        prompt: str,
        system_prompt: Optional[str],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict[str, Any]],
        **kwargs
    ) -> str:
        """OpenAI-specific completion."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        completion_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        # Add response format for structured output
        if response_format:
            completion_kwargs["response_format"] = response_format
        
        response = await self.client.chat.completions.create(**completion_kwargs)
        return response.choices[0].message.content or ""
    
    async def _anthropic_completion(
        self,
        prompt: str,
        system_prompt: Optional[str],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict[str, Any]],
        **kwargs
    ) -> str:
        """Anthropic-specific completion."""
        # Anthropic uses system parameter, not system message
        completion_kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }
        
        if system_prompt:
            completion_kwargs["system"] = system_prompt
        
        # For structured output, add JSON schema to system prompt
        if response_format and system_prompt:
            schema = response_format.get("schema", {})
            if schema:
                json_schema_instruction = f"\n\nYou must respond with valid JSON matching this schema: {json.dumps(schema, indent=2)}"
                completion_kwargs["system"] = system_prompt + json_schema_instruction
        
        completion_kwargs["messages"] = [{"role": "user", "content": prompt}]
        
        response = await self.client.messages.create(**completion_kwargs)
        return response.content[0].text
    
    async def get_structured_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get structured JSON completion.
        
        Args:
            prompt: User prompt
            schema: JSON schema for response
            system_prompt: Optional system prompt
            model: Override default model
            **kwargs: Additional parameters
        
        Returns:
            Parsed JSON response as dict
        """
        if self.provider == LLMProvider.OPENAI:
            # OpenAI structured output
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": schema,
                    "strict": True
                }
            }
        else:
            # Anthropic uses schema in system prompt
            response_format = {"schema": schema}
        
        response_text = await self.get_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            response_format=response_format,
            **kwargs
        )
        
        # Parse JSON response
        try:
            # Remove markdown code fences if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse JSON response: {str(e)}\nResponse: {response_text[:200]}") from e


# Convenience function
async def get_completion(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> str:
    """Get LLM completion using default settings."""
    client = LLMClient()
    return await client.get_completion(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        **kwargs
    )
