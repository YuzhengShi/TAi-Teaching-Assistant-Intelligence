"""
Emergent misconception discovery from student interactions.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import json

from src.graph.connection import get_connection
from src.graph.queries import MisconceptionQueries, CourseQueries
from src.memory.store import SafeMemoryStore
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class MisconceptionDetector:
    """Detect misconceptions using graph-based LLM classification."""
    
    def __init__(self, memory_store: SafeMemoryStore, config: Optional[Dict] = None):
        self.memory_store = memory_store
        self.config = config or {}
        self.llm = LLMClient(model=settings.llm.extraction_model, temperature=0.0)
        self.confirmation_threshold = self.config.get("confirmation_threshold", 3)
        
        # Load classification prompt
        prompt_path = Path("config/prompts/misconception_check.md")
        if prompt_path.exists():
            self.classification_prompt_template = prompt_path.read_text()
        else:
            self.classification_prompt_template = "Classify misconception in student statement."
    
    async def check(
        self,
        student_statement: str,
        topic: str
    ) -> Dict[str, Any]:
        """
        Check student statement for misconceptions.
        
        Args:
            student_statement: What the student said
            topic: Topic/concept being discussed
        
        Returns:
            Classification result with misconception info
        """
        # Query graph for confirmed misconceptions
        known_misconceptions = await self._get_known_misconceptions(topic)
        
        # Build prompt
        prompt = self.classification_prompt_template.replace(
            "{student_statement}", student_statement
        ).replace(
            "{topic}", topic
        ).replace(
            "{known_misconceptions}", json.dumps(known_misconceptions, indent=2)
        )
        
        # Define JSON schema
        schema = {
            "type": "object",
            "properties": {
                "holds_known_misconception": {"type": "boolean"},
                "matched_misconception": {"type": ["string", "null"]},
                "is_identifying_not_holding": {"type": "boolean"},
                "is_new_candidate": {"type": "boolean"},
                "new_candidate_description": {"type": ["string", "null"]},
                "contradicts_concept": {"type": ["string", "null"]}
            },
            "required": ["holds_known_misconception", "is_identifying_not_holding", "is_new_candidate"]
        }
        
        try:
            # Classify
            result = await self.llm.get_structured_completion(prompt, schema)
            
            # If new candidate and student is HOLDING (not identifying), write to WAL
            if result.get("is_new_candidate") and not result.get("is_identifying_not_holding"):
                self._write_candidate_to_wal(
                    description=result.get("new_candidate_description", ""),
                    contradicts=result.get("contradicts_concept", topic),
                    topic=topic
                )
            
            return result
        
        except Exception as e:
            logger.error(f"Misconception classification failed: {str(e)}")
            return {
                "holds_known_misconception": False,
                "matched_misconception": None,
                "is_identifying_not_holding": False,
                "is_new_candidate": False,
                "error": str(e)
            }
    
    async def _get_known_misconceptions(self, topic: str) -> List[Dict[str, Any]]:
        """Get confirmed misconceptions for topic from graph."""
        connection = get_connection()
        
        misconceptions = []
        
        with connection.session_sync() as session:
            # Find concept by topic name
            concept_query = CourseQueries.find_concept_by_name(topic)
            result = session.run(concept_query.query, concept_query.params)
            record = result.single()
            
            if record:
                concept_id = record["id"]
                
                # Get misconceptions for this concept
                mis_query = MisconceptionQueries.get_confirmed_misconceptions_for_concept(concept_id)
                mis_result = session.run(mis_query.query, mis_query.params)
                
                for mis_record in mis_result:
                    misconceptions.append({
                        "description": mis_record["description"],
                        "frequency": mis_record.get("frequency", 0)
                    })
        
        return misconceptions
    
    def _write_candidate_to_wal(
        self,
        description: str,
        contradicts: str,
        topic: str
    ):
        """Write candidate misconception to WAL (sync, non-blocking)."""
        fact_text = f"CANDIDATE_MISCONCEPTION: {description} (contradicts: {contradicts})"
        
        # Write directly to SQLite bypassing consent check for system-level facts
        try:
            with self.memory_store._get_connection() as conn:
                # Ensure system user exists
                conn.execute(
                    """INSERT OR IGNORE INTO students (id, anonymized_id, consent_granted)
                       VALUES ('system', 'system_internal', 1)"""
                )
                conn.execute(
                    """INSERT INTO student_facts (student_id, fact_text, fact_type, confidence_score, graph_synced)
                       VALUES (?, ?, ?, ?, 0)""",
                    ("system", fact_text, "CANDIDATE_MISCONCEPTION", 0.5)
                )
        except Exception as e:
            logger.error(f"Failed to write misconception candidate to WAL: {str(e)}")
    
    async def get_pending_review(self, min_frequency: int = 3) -> List[Dict[str, Any]]:
        """Get misconception candidates pending professor review."""
        connection = get_connection()
        
        with connection.session_sync() as session:
            query_result = MisconceptionQueries.get_pending_review_candidates(min_frequency)
            result = session.run(query_result.query, query_result.params)
            
            candidates = []
            for record in result:
                candidates.append({
                    "id": record["id"],
                    "description": record["description"],
                    "frequency": record["frequency"],
                    "first_seen": record.get("first_seen"),
                    "related_concepts": record.get("related_concepts", [])
                })
            
            return candidates
