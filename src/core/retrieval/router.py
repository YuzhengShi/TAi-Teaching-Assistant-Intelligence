"""
Query router: classifies query type and selects retrieval strategy.
"""

from typing import Literal, List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

from src.core.retrieval.local_search import LocalSearch
from src.core.retrieval.global_search import GlobalSearch
from src.core.retrieval.hybrid_search import HybridSearch

from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class SearchStrategy(str, Enum):
    """Available search strategies."""
    LOCAL = "local"
    GLOBAL = "global"
    PREREQUISITE = "prerequisite"
    HYBRID = "hybrid"


@dataclass
class RoutingResult:
    """Query routing result."""
    strategy: SearchStrategy
    entities: List[str]  # Extracted entity names
    query_type: str  # "global", "local", "prerequisite", "code", "relationship"


class QueryRouter:
    """Route queries to appropriate retrieval strategy."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.llm = LLMClient(model=settings.llm.extraction_model, temperature=0.0)
    
    async def route(self, query: str) -> RoutingResult:
        """
        Classify query and extract entities.
        
        Args:
            query: Student query
        
        Returns:
            RoutingResult with strategy and extracted entities
        """
        # Use keyword heuristics first (faster)
        strategy, query_type = self._heuristic_classify(query)
        
        # Extract entities
        entities = self._extract_entities_keywords(query)
        
        # Use LLM for ambiguous cases
        if strategy == SearchStrategy.LOCAL and not entities:
            # Try LLM extraction
            entities = await self._llm_extract_entities(query)
        
        return RoutingResult(
            strategy=strategy,
            entities=entities,
            query_type=query_type
        )
    
    def get_search_instance(self, strategy: SearchStrategy):
        """Get appropriate search instance for strategy."""
        if strategy == SearchStrategy.GLOBAL:
            return GlobalSearch()
        elif strategy == SearchStrategy.HYBRID:
            return HybridSearch()
        else:
            return LocalSearch()
    
    def _heuristic_classify(self, query: str) -> tuple[SearchStrategy, str]:
        """Classify query using keyword heuristics."""
        query_lower = query.lower()
        
        # Global questions
        global_keywords = ["what are the main", "summarize", "compare all", "overview", "themes"]
        if any(keyword in query_lower for keyword in global_keywords):
            return SearchStrategy.GLOBAL, "global"
        
        # Prerequisite questions
        prerequisite_keywords = ["what before", "prerequisite", "need to know", "what do i need"]
        if any(keyword in query_lower for keyword in prerequisite_keywords):
            return SearchStrategy.PREREQUISITE, "prerequisite"
        
        # Code questions
        code_keywords = ["implement", "code", "debug", "write", "function", "algorithm"]
        if any(keyword in query_lower for keyword in code_keywords):
            return SearchStrategy.HYBRID, "code"
        
        # Relationship questions
        relationship_keywords = ["how does", "relate", "compare", "difference between"]
        if any(keyword in query_lower for keyword in relationship_keywords):
            return SearchStrategy.LOCAL, "relationship"
        
        # Default: local search
        return SearchStrategy.LOCAL, "local"
    
    def _extract_entities_keywords(self, query: str) -> List[str]:
        """Extract entity names using keyword matching."""
        # Common entity names in CS6650
        known_entities = [
            "Raft", "Paxos", "MapReduce", "DHT", "consensus", "CAP theorem",
            "leader election", "log replication", "distributed hash table"
        ]
        
        found = []
        query_lower = query.lower()
        
        for entity in known_entities:
            if entity.lower() in query_lower:
                found.append(entity)
        
        return found
    
    async def _llm_extract_entities(self, query: str) -> List[str]:
        """Use LLM to extract entity names from query."""
        prompt = f"""Extract entity/concept names from this query about distributed systems:

Query: {query}

Return a JSON array of entity names found in the query. If none found, return empty array []."""
        
        try:
            schema = {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["entities"]
            }
            
            response = await self.llm.get_structured_completion(prompt, schema)
            return response.get("entities", [])
        
        except Exception as e:
            logger.warning(f"LLM entity extraction failed: {str(e)}")
            return []
