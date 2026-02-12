"""
Local search: entity-seeded neighborhood retrieval.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.graph.connection import get_connection
from src.graph.queries import CourseQueries
from src.shared.embeddings import EmbeddingClient
from src.shared.tokens import count_tokens, truncate_to_tokens
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """Single retrieval result."""
    text: str
    score: float
    source: str
    entities_involved: List[str]
    metadata: Dict[str, Any] = None


class LocalSearch:
    """Local entity-seeded neighborhood search."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.embedding_client = EmbeddingClient()
        self.top_k = self.config.get("top_k", settings.retrieval.top_k)
        self.max_tokens = self.config.get("max_tokens", settings.retrieval.max_context_tokens)
    
    async def search(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        Search for relevant entities and expand their graph neighborhood.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            List of RetrievalResult objects
        """
        top_k = top_k or self.top_k
        
        # Embed query
        query_embedding = await self.embedding_client.embed(query)
        
        # Find matching entities (simplified - in production, use vector index)
        matched_entities = await self._find_matching_entities(query, query_embedding)
        
        # Expand neighborhood for each matched entity
        results = []
        total_tokens = 0
        
        for entity_id, entity_name, similarity_score in matched_entities[:top_k]:
            # Get neighborhood
            neighborhood = await self._get_entity_neighborhood(entity_id)
            
            # Build result text
            result_text = self._build_result_text(entity_name, neighborhood)
            result_tokens = count_tokens(result_text)
            
            # Check token budget
            if total_tokens + result_tokens > self.max_tokens:
                # Truncate if needed
                remaining_tokens = self.max_tokens - total_tokens
                if remaining_tokens > 100:  # Only if meaningful space left
                    result_text = truncate_to_tokens(result_text, remaining_tokens)
                else:
                    break
            
            results.append(RetrievalResult(
                text=result_text,
                score=similarity_score,
                source=neighborhood.get("source", "unknown"),
                entities_involved=[entity_name] + neighborhood.get("related_entities", []),
                metadata=neighborhood
            ))
            
            total_tokens += count_tokens(result_text)
        
        return results
    
    async def _find_matching_entities(
        self,
        query: str,
        query_embedding: List[float]
    ) -> List[tuple[str, str, float]]:
        """Find entities matching the query using embedding similarity."""
        connection = get_connection()
        await connection.connect()
        
        matches = []
        
        async with connection.session() as session:
            # Get all concepts (in production, use vector index)
            result = await session.run(
                "MATCH (c:Concept) RETURN c.id as id, c.name as name, c.description as description LIMIT 100"
            )
            
            async for record in result:
                entity_name = record["name"]
                entity_desc = record.get("description", "")
                
                # Embed entity name + description
                entity_text = f"{entity_name} {entity_desc}"
                entity_embedding = await self.embedding_client.embed(entity_text)
                
                # Calculate similarity
                similarity = self.embedding_client.cosine_similarity(
                    query_embedding,
                    entity_embedding
                )
                
                if similarity > 0.5:  # Threshold
                    matches.append((record["id"], entity_name, similarity))
        
        # Sort by similarity
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches
    
    async def _get_entity_neighborhood(self, entity_id: str) -> Dict[str, Any]:
        """Get graph neighborhood of an entity (1-2 hops)."""
        connection = get_connection()
        await connection.connect()
        
        neighborhood = {
            "entity_id": entity_id,
            "related_entities": [],
            "relationships": [],
            "source": "graph"
        }
        
        async with connection.session() as session:
            # Get entity details
            query_result = CourseQueries.find_concept_by_name("")  # We'll query by ID instead
            query = "MATCH (c:Concept {id: $entity_id}) RETURN c.name as name, c.description as description"
            result = await session.run(query, {"entity_id": entity_id})
            record = await result.single()
            
            if record:
                neighborhood["entity_name"] = record["name"]
                neighborhood["entity_description"] = record.get("description", "")
            
            # Get 1-hop neighbors
            neighbor_query = """
            MATCH (c:Concept {id: $entity_id})-[r]-(related:Concept)
            RETURN related.name as name, type(r) as rel_type, r.description as rel_desc
            LIMIT 10
            """
            neighbor_result = await session.run(neighbor_query, {"entity_id": entity_id})
            
            async for neighbor_record in neighbor_result:
                neighborhood["related_entities"].append(neighbor_record["name"])
                neighborhood["relationships"].append({
                    "type": neighbor_record["rel_type"],
                    "description": neighbor_record.get("rel_desc", "")
                })
        
        return neighborhood
    
    def _build_result_text(self, entity_name: str, neighborhood: Dict[str, Any]) -> str:
        """Build formatted result text from neighborhood."""
        parts = []
        
        # Entity description
        if neighborhood.get("entity_description"):
            parts.append(f"**{entity_name}**: {neighborhood['entity_description']}")
        
        # Relationships
        if neighborhood.get("relationships"):
            parts.append("\n**Related concepts:**")
            for rel in neighborhood["relationships"][:5]:  # Top 5
                parts.append(f"- {rel['type']}: {rel.get('description', '')}")
        
        # Related entities
        if neighborhood.get("related_entities"):
            parts.append(f"\n**See also:** {', '.join(neighborhood['related_entities'][:5])}")
        
        return "\n".join(parts)
