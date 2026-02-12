"""
Global search: map-reduce over community summaries.
For "what are the main..." / "summarize..." / "compare all..." queries.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.graph.connection import get_connection
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GlobalSearchResult:
    """Result from global search."""
    synthesized_answer: str
    communities_used: List[str]
    relevance_scores: Dict[str, float]


class GlobalSearch:
    """Global search using community summaries."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.llm = LLMClient(model=settings.llm.reasoning_model, temperature=0.0)
    
    async def search(self, query: str) -> GlobalSearchResult:
        """
        Search using community summaries with map-reduce.
        
        Args:
            query: Global question (e.g., "What are the main consensus approaches?")
        
        Returns:
            GlobalSearchResult with synthesized answer
        """
        # Load community summaries
        communities = await self._load_community_summaries()
        
        if not communities:
            return GlobalSearchResult(
                synthesized_answer="No community data available.",
                communities_used=[],
                relevance_scores={}
            )
        
        # Map phase: generate intermediate answers for each community
        intermediate_results = await self._map_phase(query, communities)
        
        # Filter by relevance
        relevant_results = self._filter_by_relevance(intermediate_results, threshold=0.5)
        
        # Reduce phase: synthesize final answer
        synthesized = await self._reduce_phase(query, relevant_results)
        
        return GlobalSearchResult(
            synthesized_answer=synthesized,
            communities_used=[r["community_id"] for r in relevant_results],
            relevance_scores={r["community_id"]: r["relevance"] for r in relevant_results}
        )
    
    async def _load_community_summaries(self) -> List[Dict[str, Any]]:
        """Load community summaries from Neo4j."""
        connection = get_connection()
        
        communities = []
        
        with connection.session_sync() as session:
            query = """
            MATCH (c:Community)
            WHERE c.summary IS NOT NULL
            RETURN c.id as id, c.summary as summary, c.node_count as node_count
            ORDER BY c.node_count DESC
            LIMIT 20
            """
            result = session.run(query)
            
            for record in result:
                communities.append({
                    "id": record["id"],
                    "summary": record["summary"],
                    "node_count": record.get("node_count", 0)
                })
        
        return communities
    
    async def _map_phase(
        self,
        query: str,
        communities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Map phase: generate intermediate answer for each community."""
        intermediate_results = []
        
        for community in communities:
            prompt = f"""Given this community summary about distributed systems concepts:

{community['summary']}

Question: {query}

Provide a brief answer (2-3 sentences) based on this community's concepts. If not relevant, respond "NOT_RELEVANT".

Also provide a relevance score (0.0 to 1.0) for how well this community answers the question."""
            
            try:
                response = await self.llm.get_completion(prompt, max_tokens=200)
                
                # Extract relevance score (simple heuristic - in production, use structured output)
                relevance = self._extract_relevance_score(response)
                
                if "NOT_RELEVANT" not in response.upper():
                    intermediate_results.append({
                        "community_id": community["id"],
                        "answer": response,
                        "relevance": relevance,
                        "node_count": community["node_count"]
                    })
            except Exception as e:
                logger.warning(f"Map phase failed for community {community['id']}: {str(e)}")
                continue
        
        return intermediate_results
    
    def _filter_by_relevance(
        self,
        results: List[Dict[str, Any]],
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Filter results by relevance score."""
        filtered = [r for r in results if r["relevance"] >= threshold]
        # Sort by relevance
        filtered.sort(key=lambda x: x["relevance"], reverse=True)
        return filtered[:10]  # Top 10
    
    async def _reduce_phase(
        self,
        query: str,
        intermediate_results: List[Dict[str, Any]]
    ) -> str:
        """Reduce phase: synthesize final answer from intermediate results."""
        if not intermediate_results:
            return "I don't have enough information to answer this question comprehensively."
        
        # Combine intermediate answers
        combined_answers = "\n\n".join([
            f"Community {i+1}: {r['answer']}" 
            for i, r in enumerate(intermediate_results)
        ])
        
        prompt = f"""Synthesize a comprehensive answer from these community-based responses:

Question: {query}

Community Answers:
{combined_answers}

Provide a unified, coherent answer that integrates insights from all relevant communities. 
Cite which communities contributed to different aspects of the answer."""
        
        try:
            synthesized = await self.llm.get_completion(prompt, max_tokens=1000)
            return synthesized
        except Exception as e:
            logger.error(f"Reduce phase failed: {str(e)}")
            # Fallback: return first intermediate answer
            return intermediate_results[0]["answer"] if intermediate_results else ""
    
    def _extract_relevance_score(self, response: str) -> float:
        """Extract relevance score from LLM response (heuristic)."""
        import re
        
        # Look for score in response
        score_match = re.search(r'relevance[:\s]+([0-9.]+)', response, re.IGNORECASE)
        if score_match:
            try:
                return float(score_match.group(1))
            except ValueError:
                pass
        
        # Default: estimate from response length and keywords
        if len(response) > 50 and "NOT_RELEVANT" not in response.upper():
            return 0.6  # Moderate relevance
        return 0.3  # Low relevance
