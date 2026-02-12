"""
Community detection using Leiden algorithm.
Generates hierarchical community summaries.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import igraph as ig
import leidenalg

from src.graph.connection import get_connection
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Community:
    """Represents a detected community."""
    id: str
    nodes: List[str]  # Entity IDs in this community
    level: int  # Hierarchy level (0 = leaf)
    parent_id: Optional[str] = None
    summary: Optional[str] = None


class CommunityDetector:
    """Detect communities in the knowledge graph."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.resolution = self.config.get("resolution", settings.graph_resolution)
        self.llm = LLMClient(model=settings.llm.extraction_model, temperature=0.0)
    
    async def detect(self) -> List[Community]:
        """
        Detect hierarchical communities in Neo4j graph.
        
        Returns:
            List of communities at all hierarchy levels
        """
        # Export graph from Neo4j to igraph
        graph = await self._export_to_igraph()
        
        if len(graph.vs) == 0:
            logger.warning("Empty graph, no communities to detect")
            return []
        
        # Run Leiden algorithm
        communities = self._run_leiden(graph)
        
        # Generate summaries
        summarized = await self._generate_summaries(communities)
        
        # Store back in Neo4j
        await self._store_communities(summarized)
        
        return summarized
    
    async def _export_to_igraph(self) -> ig.Graph:
        """Export Neo4j graph to igraph format."""
        connection = get_connection()
        await connection.connect()
        
        graph = ig.Graph(directed=True)
        
        async with connection.session() as session:
            # Get all nodes
            result = await session.run(
                "MATCH (n:Concept) RETURN n.id as id, n.name as name, n.type as type"
            )
            
            node_map = {}  # id -> vertex index
            async for record in result:
                node_id = record["id"]
                node_map[node_id] = len(graph.vs)
                graph.add_vertex(name=node_id, label=record.get("name", ""))
            
            # Get all relationships
            rel_result = await session.run(
                "MATCH (a:Concept)-[r]->(b:Concept) "
                "RETURN a.id as source, b.id as target, type(r) as rel_type"
            )
            
            async for record in rel_result:
                source_id = record["source"]
                target_id = record["target"]
                
                if source_id in node_map and target_id in node_map:
                    source_idx = node_map[source_id]
                    target_idx = node_map[target_id]
                    graph.add_edge(source_idx, target_idx)
        
        logger.info(f"Exported graph: {len(graph.vs)} nodes, {len(graph.es)} edges")
        return graph
    
    def _run_leiden(self, graph: ig.Graph) -> List[Community]:
        """Run Leiden community detection algorithm."""
        # Convert to undirected for community detection
        undirected = graph.as_undirected()
        
        # Run Leiden with CPM (Constant Potts Model)
        partition = leidenalg.find_partition(
            undirected,
            leidenalg.CPMVertexPartition,
            resolution_parameter=self.resolution
        )
        
        # Build community hierarchy
        communities = []
        
        for i, community in enumerate(partition):
            node_names = [graph.vs[idx]["name"] for idx in community]
            
            communities.append(Community(
                id=f"community_{i}",
                nodes=node_names,
                level=0,  # Leaf level
                parent_id=None
            ))
        
        logger.info(f"Detected {len(communities)} communities")
        return communities
    
    async def _generate_summaries(self, communities: List[Community]) -> List[Community]:
        """Generate LLM summaries for each community."""
        # Get entity names for each community
        connection = get_connection()
        await connection.connect()
        
        summarized = []
        
        for community in communities:
            # Get entity details from Neo4j
            entity_names = []
            entity_descriptions = []
            
            async with connection.session() as session:
                for node_id in community.nodes[:10]:  # Limit to first 10 for summary
                    query = "MATCH (n:Concept {id: $id}) RETURN n.name as name, n.description as desc"
                    result = await session.run(query, {"id": node_id})
                    record = await result.single()
                    if record:
                        entity_names.append(record["name"])
                        if record.get("desc"):
                            entity_descriptions.append(record["desc"])
            
            # Generate summary
            summary = await self._generate_community_summary(
                entity_names,
                entity_descriptions
            )
            
            community.summary = summary
            summarized.append(community)
        
        return summarized
    
    async def _generate_community_summary(
        self,
        entity_names: List[str],
        descriptions: List[str]
    ) -> str:
        """Generate LLM summary for a community."""
        prompt = f"""Summarize this group of related concepts in distributed systems:

Concepts: {', '.join(entity_names[:10])}

Descriptions: {'; '.join(descriptions[:5])}

Provide:
1. A title (3-5 words)
2. A brief description (1-2 sentences)
3. Key themes
4. Importance rank (1-10)

Format as: Title | Description | Themes | Rank"""
        
        try:
            response = await self.llm.get_completion(prompt, max_tokens=200)
            return response
        except Exception as e:
            logger.warning(f"Summary generation failed: {str(e)}")
            return f"Community with {len(entity_names)} concepts"
    
    async def _store_communities(self, communities: List[Community]):
        """Store communities back in Neo4j."""
        connection = get_connection()
        await connection.connect()
        
        async with connection.session() as session:
            for community in communities:
                # Create community node
                query = """
                MERGE (c:Community {id: $community_id})
                SET c.summary = $summary,
                    c.level = $level,
                    c.node_count = $node_count,
                    c.updated_at = timestamp()
                ON CREATE SET c.created_at = timestamp()
                """
                await session.run(query, {
                    "community_id": community.id,
                    "summary": community.summary,
                    "level": community.level,
                    "node_count": len(community.nodes)
                })
                
                # Create BELONGS_TO relationships
                for node_id in community.nodes:
                    rel_query = """
                    MATCH (n:Concept {id: $node_id})
                    MATCH (c:Community {id: $community_id})
                    MERGE (n)-[r:BELONGS_TO]->(c)
                    SET r.updated_at = timestamp()
                    ON CREATE SET r.created_at = timestamp()
                    """
                    await session.run(rel_query, {
                        "node_id": node_id,
                        "community_id": community.id
                    })
        
        logger.info(f"Stored {len(communities)} communities in Neo4j")
