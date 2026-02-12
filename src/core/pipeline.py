"""
Main TAi pipeline: end-to-end query processing.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from src.core.retrieval.router import QueryRouter, SearchStrategy
from src.core.retrieval.local_search import LocalSearch, RetrievalResult
from src.core.retrieval.global_search import GlobalSearch
from src.core.retrieval.hybrid_search import HybridSearch
from src.core.retrieval.context_builder import ContextBuilder
from src.memory.store import SafeMemoryStore
from src.safety.consent import ConsentManager
from src.session.manager import SessionManager
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.exceptions import ConsentRequiredError
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TAiResponse:
    """Response from TAi pipeline."""
    answer: str
    citations: List[str]
    confidence: float
    misconception_detected: bool
    retrieval_strategy_used: str


class TAiPipeline:
    """Main pipeline that wires everything together."""
    
    def __init__(self):
        self.memory_store = SafeMemoryStore()
        self.consent_manager = ConsentManager(self.memory_store)
        self.session_manager = SessionManager()
        self.router = QueryRouter()
        self.local_search = LocalSearch()
        self.global_search = GlobalSearch()
        self.hybrid_search = HybridSearch()
        self.context_builder = ContextBuilder()
        self.llm = LLMClient()
    
    async def ask(
        self,
        student_id: str,
        question: str,
        context_type: str = "general"
    ) -> TAiResponse:
        """
        Process student question through complete pipeline.
        
        Args:
            student_id: Student identifier
            question: Student's question
            context_type: Session context (e.g., "assignment-3", "lecture-mapreduce")
        
        Returns:
            TAiResponse with answer and metadata
        """
        # Check consent
        if not self.consent_manager.has_consent(student_id):
            raise ConsentRequiredError(f"Student {student_id} must grant consent first")
        
        # Get or create session
        session = self.session_manager.get_or_create(
            student_id,
            {"course": "cs6650", "context": context_type}
        )
        
        # Route query
        routing = await self.router.route(question)
        
        # Retrieve context based on routed strategy
        retrieval_results: List[RetrievalResult] = []
        if routing.strategy == SearchStrategy.GLOBAL:
            global_result = await self.global_search.search(question)
            # Wrap global result as a RetrievalResult for context builder
            if global_result.synthesized_answer:
                retrieval_results = [RetrievalResult(
                    text=global_result.synthesized_answer,
                    score=1.0,
                    source="community_summaries",
                    entities_involved=[]
                )]
        elif routing.strategy == SearchStrategy.HYBRID:
            retrieval_results = await self.hybrid_search.search(question)
        else:
            # LOCAL and PREREQUISITE both use local search
            retrieval_results = await self.local_search.search(question)
        
        # Build context
        context = self.context_builder.build(retrieval_results)
        
        # Build system prompt with retrieval context
        system_prompt = self._build_system_prompt(student_id, context_type, context)
        
        # Generate response
        answer = await self.llm.get_completion(
            prompt=question,
            system_prompt=system_prompt
        )
        
        # Extract citations
        citations = [r.source for r in retrieval_results]
        
        # Add to session
        self.session_manager.add_message(session["session_key"], "student", question)
        self.session_manager.add_message(session["session_key"], "assistant", answer)
        
        # Check for misconceptions (simplified for now)
        misconception_detected = False  # Would call misconception detector
        
        # Calculate confidence from retrieval scores
        confidence = 0.5  # default
        if retrieval_results:
            confidence = sum(r.score for r in retrieval_results) / len(retrieval_results)
        
        return TAiResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            misconception_detected=misconception_detected,
            retrieval_strategy_used=routing.strategy.value
        )
    
    def _build_system_prompt(
        self, student_id: str, context_type: str, retrieval_context: str = ""
    ) -> str:
        """Build system prompt with student context."""
        base = """You are a teaching assistant for CS6650: Distributed Systems.
Answer questions clearly, cite sources, and help students understand concepts.
Use the Socratic method — guide students to discover answers rather than giving them directly.
Never provide assignment answers directly."""
        
        if retrieval_context:
            base += f"\n\n## Relevant Course Content\n{retrieval_context}"
        
        return base
