"""
Indexing pipeline orchestrator.
Coordinates: file discovery → ingestion → extraction → resolution → Neo4j storage.
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import hashlib

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk
from src.core.indexing.ingestors.slides import SlidesIngestor
from src.core.indexing.ingestors.paper import PaperIngestor
from src.core.indexing.ingestors.transcript import TranscriptIngestor
from src.core.indexing.ingestors.assignment import AssignmentIngestor
from src.core.indexing.ingestors.discussion import DiscussionIngestor
from src.core.indexing.ingestors.code import CodeIngestor
from src.core.indexing.ingestors.notes import NotesIngestor
from src.core.indexing.extractor import EntityRelationshipExtractor
from src.core.indexing.resolver import EntityResolver
from src.graph.connection import get_connection
from src.graph.queries import CourseQueries
from src.graph.schema import RelationshipType
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class IndexingPipeline:
    """Orchestrates the complete indexing pipeline."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Initialize ingestors
        self.ingestors: List[BaseIngestor] = [
            SlidesIngestor(),
            PaperIngestor(),
            TranscriptIngestor(),
            AssignmentIngestor(),
            DiscussionIngestor(),
            CodeIngestor(),
            NotesIngestor(),
        ]
        
        # Initialize extractor and resolver
        self.extractor = EntityRelationshipExtractor()
        self.resolver = EntityResolver()
        
        # Neo4j connection
        self.neo4j = get_connection()
        
        # Statistics
        self.stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "entities_extracted": 0,
            "relationships_extracted": 0,
            "entities_merged": 0,
            "entities_stored": 0,
        }
    
    async def run(
        self,
        data_dir: Path,
        mode: str = "full"
    ) -> Dict[str, Any]:
        """
        Run the indexing pipeline.
        
        Args:
            data_dir: Directory containing source files
            mode: "full", "incremental", or "staging"
        
        Returns:
            Statistics dictionary
        """
        logger.info(f"Starting indexing pipeline: mode={mode}, data_dir={data_dir}")
        
        # Connect to Neo4j
        await self.neo4j.connect()
        
        # Clear graph if full mode
        if mode == "full":
            await self._clear_graph()
        
        # Discover files
        files = self._discover_files(data_dir, mode)
        logger.info(f"Discovered {len(files)} files to process")
        
        # Process files
        all_entities = []
        all_relationships = []
        processed_hashes = set()
        
        if mode == "incremental":
            processed_hashes = await self._get_processed_hashes()
        
        for file_path in files:
            try:
                # Check if already processed (incremental mode)
                file_hash = self._hash_file(file_path)
                if file_hash in processed_hashes:
                    logger.debug(f"Skipping already processed file: {file_path.name}")
                    continue
                
                # Process file
                result = await self._process_file(file_path)
                
                all_entities.extend(result["entities"])
                all_relationships.extend(result["relationships"])
                
                self.stats["files_processed"] += 1
                self.stats["chunks_created"] += len(result["chunks"])
                self.stats["entities_extracted"] += len(result["entities"])
                self.stats["relationships_extracted"] += len(result["relationships"])
                
                # Store source hash
                await self._store_source_hash(file_path, file_hash)
            
            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {str(e)}")
                continue
        
        # Resolve entities
        logger.info(f"Resolving {len(all_entities)} entities...")
        resolved_entities = await self.resolver.resolve(all_entities)
        self.stats["entities_merged"] = len(all_entities) - len(resolved_entities)
        self.stats["entities_stored"] = len(resolved_entities)
        
        # Store in Neo4j
        logger.info(f"Storing {len(resolved_entities)} resolved entities and {len(all_relationships)} relationships...")
        await self._store_in_neo4j(resolved_entities, all_relationships)
        
        logger.info("Indexing pipeline completed", extra=self.stats)
        return self.stats
    
    def _discover_files(self, data_dir: Path, mode: str) -> List[Path]:
        """Discover files to process."""
        if not data_dir.exists():
            logger.warning(f"Data directory does not exist: {data_dir}")
            return []
        
        files = []
        
        if mode == "staging":
            # Only process staging directory
            staging_dir = Path(settings.indexing.staging_dir)
            if staging_dir.exists():
                files.extend(self._find_files(staging_dir))
        else:
            # Process all files in data directory
            files.extend(self._find_files(data_dir))
        
        return files
    
    def _find_files(self, directory: Path) -> List[Path]:
        """Recursively find all processable files."""
        files = []
        
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                # Check if any ingestor can handle this file
                for ingestor in self.ingestors:
                    if ingestor.can_ingest(file_path):
                        files.append(file_path)
                        break
        
        return files
    
    async def _process_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single file through the pipeline."""
        # Select ingestor
        ingestor = None
        for ing in self.ingestors:
            if ing.can_ingest(file_path):
                ingestor = ing
                break
        
        if not ingestor:
            raise ValueError(f"No ingestor found for file: {file_path}")
        
        # Ingest
        chunks = ingestor.ingest(file_path)
        
        # Extract entities and relationships
        all_entities = []
        all_relationships = []
        
        for chunk in chunks:
            extraction_result = await self.extractor.extract(chunk)
            all_entities.extend(extraction_result.entities)
            all_relationships.extend(extraction_result.relationships)
        
        return {
            "chunks": chunks,
            "entities": all_entities,
            "relationships": all_relationships
        }
    
    async def _store_in_neo4j(
        self,
        resolved_entities: List,
        relationships: List
    ):
        """Store resolved entities and relationships in Neo4j."""
        async with self.neo4j.session() as session:
            # Batch entities (50 per transaction)
            batch_size = 50
            
            for i in range(0, len(resolved_entities), batch_size):
                batch = resolved_entities[i:i + batch_size]
                
                async with session.begin_transaction() as tx:
                    for resolved in batch:
                        # Create concept node
                        query_result = CourseQueries.upsert_concept(
                            name=resolved.canonical_name,
                            description=" | ".join(resolved.descriptions) if resolved.descriptions else "",
                            concept_type=resolved.type
                        )
                        await tx.run(query_result.query, query_result.params)
                    
                    await tx.commit()
            
            # Store relationships
            # Validate allowed relationship types to prevent Cypher injection
            allowed_rel_types = {rt.value for rt in RelationshipType}
            
            for rel in relationships:
                # SECURITY: validate rel.type against schema enum — never interpolate raw
                rel_type_upper = rel.type.strip().upper()
                if rel_type_upper not in allowed_rel_types:
                    logger.warning(f"Skipping unknown relationship type: {rel.type}")
                    continue
                
                # Find source and target entity IDs
                source_query = CourseQueries.find_concept_by_name(rel.source)
                target_query = CourseQueries.find_concept_by_name(rel.target)
                
                async with session.begin_transaction() as tx:
                    source_result = await tx.run(source_query.query, source_query.params)
                    target_result = await tx.run(target_query.query, target_query.params)
                    
                    source_record = await source_result.single()
                    target_record = await target_result.single()
                    
                    if source_record and target_record:
                        # Use APOC to create relationship with dynamic type safely
                        # APOC's apoc.merge.relationship uses parameterized type
                        rel_query = """
                        MATCH (source:Concept {id: $source_id})
                        MATCH (target:Concept {id: $target_id})
                        CALL apoc.merge.relationship(
                            source, $rel_type, {description: $description, created_at: timestamp()},
                            {}, target, {}
                        ) YIELD rel
                        RETURN rel
                        """
                        await tx.run(rel_query, {
                            "source_id": source_record["id"],
                            "target_id": target_record["id"],
                            "rel_type": rel_type_upper,
                            "description": rel.description
                        })
                    
                    await tx.commit()
    
    async def _clear_graph(self):
        """Clear existing graph (full mode only)."""
        logger.warning("Clearing existing graph (full mode)")
        
        async with self.neo4j.session() as session:
            # Delete all nodes and relationships (except SchemaVersion)
            await session.run("MATCH (n) WHERE NOT n:SchemaVersion DETACH DELETE n")
        
        logger.info("Graph cleared")
    
    async def _get_processed_hashes(self) -> Set[str]:
        """Get content hashes of already processed files."""
        hashes = set()
        
        async with self.neo4j.session() as session:
            result = await session.run(
                "MATCH (s:Source) RETURN s.content_hash as hash"
            )
            async for record in result:
                if record["hash"]:
                    hashes.add(record["hash"])
        
        return hashes
    
    async def _store_source_hash(self, file_path: Path, file_hash: str):
        """Store source file hash for incremental detection."""
        async with self.neo4j.session() as session:
            query = """
            MERGE (s:Source {id: $source_id})
            SET s.name = $name,
                s.source_type = $source_type,
                s.content_hash = $content_hash,
                s.updated_at = timestamp()
            ON CREATE SET s.created_at = timestamp()
            """
            await session.run(query, {
                "source_id": file_hash,
                "name": file_path.name,
                "source_type": file_path.suffix,
                "content_hash": file_hash
            })
    
    def _hash_file(self, file_path: Path) -> str:
        """Generate hash of file content."""
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
