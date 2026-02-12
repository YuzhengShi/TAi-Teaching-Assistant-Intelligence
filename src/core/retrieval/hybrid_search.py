"""
Hybrid search: combines vector similarity and graph relevance.
"""

from typing import List, Dict, Any, Optional
import asyncio

from src.core.retrieval.local_search import LocalSearch, RetrievalResult
from src.shared.embeddings import EmbeddingClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class HybridSearch:
    """Hybrid search combining graph and vector methods."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.local_search = LocalSearch()
        self.embedding_client = EmbeddingClient()
        self.graph_weight = self.config.get("graph_weight", settings.retrieval.hybrid_graph_weight)
        self.vector_weight = self.config.get("vector_weight", settings.retrieval.hybrid_vector_weight)
    
    async def search(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """
        Run local (graph) and vector search in parallel, then merge.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            Merged and re-ranked results
        """
        # Run both searches in parallel
        graph_task = self.local_search.search(query, top_k=top_k * 2)
        vector_task = self._vector_search(query, top_k=top_k * 2)
        
        graph_results, vector_results = await asyncio.gather(graph_task, vector_task)
        
        # Merge and deduplicate
        merged = self._merge_results(graph_results, vector_results)
        
        # Re-rank by hybrid score
        reranked = self._rerank(merged)
        
        return reranked[:top_k]
    
    async def _vector_search(self, query: str, top_k: int) -> List[RetrievalResult]:
        """Vector similarity search (simplified - in production, use vector DB)."""
        # Embed query
        query_embedding = await self.embedding_client.embed(query)
        
        # In production, this would query a vector database
        # For now, return empty results (would be implemented with actual vector store)
        return []
    
    def _merge_results(
        self,
        graph_results: List[RetrievalResult],
        vector_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """Merge results and deduplicate by entity."""
        # Group by entity
        entity_map: Dict[str, RetrievalResult] = {}
        
        # Add graph results
        for result in graph_results:
            # Use first entity as key
            if result.entities_involved:
                key = result.entities_involved[0].lower()
                if key not in entity_map:
                    entity_map[key] = result
                else:
                    # Merge: combine text, take higher score
                    existing = entity_map[key]
                    if result.score > existing.score:
                        entity_map[key] = result
        
        # Add vector results (if any)
        for result in vector_results:
            if result.entities_involved:
                key = result.entities_involved[0].lower()
                if key in entity_map:
                    # Merge scores
                    existing = entity_map[key]
                    existing.score = (existing.score * self.graph_weight + 
                                    result.score * self.vector_weight)
                else:
                    entity_map[key] = result
        
        return list(entity_map.values())
    
    def _rerank(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """Re-rank results by hybrid score."""
        # Results already have scores from merge
        # Sort by score descending
        return sorted(results, key=lambda r: r.score, reverse=True)
