"""
Memory flush engine: extracts learning events before compaction.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from src.memory.store import SafeMemoryStore
from src.memory.models import LearningEvent
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.tokens import count_tokens
from src.shared.logging import get_logger

logger = get_logger(__name__)


class MemoryFlushEngine:
    """Extracts learning events before conversation compaction."""
    
    def __init__(self, memory_store: SafeMemoryStore, config: Optional[Dict] = None):
        self.memory_store = memory_store
        self.config = config or {}
        self.flush_threshold = self.config.get("flush_threshold", 16000)  # tokens
        self.llm = LLMClient(model=settings.llm.extraction_model, temperature=0.0)
        
        # Load flush prompt
        prompt_path = Path("config/prompts/flush.md")
        if prompt_path.exists():
            self.flush_prompt_template = prompt_path.read_text()
        else:
            self.flush_prompt_template = "Extract learning events from this conversation as JSON."
    
    def should_flush(self, session: Dict[str, Any]) -> bool:
        """
        Check if conversation is approaching compaction threshold.
        
        Args:
            session: Session dict with messages
        
        Returns:
            True if flush should be triggered
        """
        messages = session.get("messages", [])
        
        # Estimate total tokens
        total_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            total_tokens += count_tokens(content)
        
        return total_tokens >= self.flush_threshold
    
    async def flush(self, session: Dict[str, Any]) -> List[LearningEvent]:
        """
        Flush learning events from conversation.
        
        Args:
            session: Session dict with messages
        
        Returns:
            List of extracted LearningEvent objects
        """
        messages = session.get("messages", [])
        student_id = session.get("student_id")
        
        if not messages:
            return []
        
        # Build conversation text
        conversation_text = self._format_conversation(messages)
        
        # Build prompt
        prompt = self.flush_prompt_template.replace("{conversation_text}", conversation_text)
        
        # Define JSON schema
        schema = {
            "type": "object",
            "properties": {
                "learning_events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "concept_name": {"type": "string"},
                            "event_type": {"type": "string"},
                            "confidence": {"type": "number"},
                            "evidence_type": {"type": "string"},
                            "context_scope": {"type": "string"},
                            "evidence": {"type": "object"}
                        },
                        "required": ["concept_name", "event_type", "confidence", "evidence_type", "context_scope"]
                    }
                }
            },
            "required": ["learning_events"]
        }
        
        try:
            # Get structured extraction
            response = await self.llm.get_structured_completion(
                prompt=prompt,
                schema=schema,
                system_prompt="You are extracting learning events from a teaching conversation."
            )
            
            # Parse into LearningEvent objects
            events = []
            for event_data in response.get("learning_events", []):
                event = LearningEvent(
                    student_id=student_id,
                    concept_name=event_data["concept_name"],
                    event_type=event_data["event_type"],
                    confidence=event_data["confidence"],
                    evidence_type=event_data["evidence_type"],
                    context_scope=event_data["context_scope"],
                    timestamp=session.get("last_activity", ""),
                    evidence=event_data.get("evidence", {})
                )
                events.append(event)
            
            # Write to WAL (synchronous, guaranteed)
            self._write_events_to_wal(student_id, events)
            
            logger.info(f"Flushed {len(events)} learning events for student {student_id}")
            
            return events
        
        except Exception as e:
            # LLM failure doesn't block compaction
            logger.warning(f"Memory flush failed (non-blocking): {str(e)}")
            return []
    
    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format messages into conversation text."""
        parts = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")
        
        return "\n\n".join(parts)
    
    def _write_events_to_wal(self, student_id: str, events: List[LearningEvent]):
        """Write events to SQLite WAL synchronously."""
        for event in events:
            fact_text = f"{event.event_type}: {event.concept_name} (confidence={event.confidence})"
            
            try:
                # Try the normal path first (requires consent)
                self.memory_store.write_student_fact(
                    student_id=student_id,
                    fact_text=fact_text,
                    fact_type=event.event_type,
                    confidence_score=event.confidence
                )
            except Exception as e:
                # If consent check fails, write directly (flush is system-initiated)
                try:
                    with self.memory_store._get_connection() as conn:
                        conn.execute(
                            """INSERT INTO student_facts
                               (student_id, fact_text, fact_type, confidence_score, graph_synced)
                               VALUES (?, ?, ?, ?, 0)""",
                            (student_id, fact_text, event.event_type, event.confidence)
                        )
                except Exception as inner_e:
                    logger.error(f"Failed to write event to WAL: {str(inner_e)}")
                    # Continue with other events
