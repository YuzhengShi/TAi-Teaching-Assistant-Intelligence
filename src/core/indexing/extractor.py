"""
Entity and relationship extraction from document chunks.
Uses LLM with schema-constrained prompts.
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import yaml

from src.core.indexing.ingestors.base import DocumentChunk
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.exceptions import ExtractionError
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Entity:
    """Extracted entity."""
    name: str
    type: str
    description: str
    source_chunk_hash: Optional[str] = None


@dataclass
class Relationship:
    """Extracted relationship."""
    source: str
    target: str
    type: str
    description: str
    source_chunk_hash: Optional[str] = None


@dataclass
class ExtractionResult:
    """Result of entity/relationship extraction."""
    entities: List[Entity]
    relationships: List[Relationship]
    raw_response: Optional[str] = None
    extraction_errors: List[str] = None
    
    def __post_init__(self):
        if self.extraction_errors is None:
            self.extraction_errors = []


class EntityRelationshipExtractor:
    """Extract entities and relationships from document chunks."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Load schema
        schema_path = settings.indexing.data_dir.parent / "config" / "schema.yaml"
        if not schema_path.exists():
            schema_path = Path("config/schema.yaml")
        
        with open(schema_path, "r") as f:
            schema_data = yaml.safe_load(f)
        
        self.allowed_entity_types = set(schema_data.get("entity_types", []))
        self.allowed_relationship_types = set(schema_data.get("relationship_types", []))
        
        # Load extraction prompt
        prompt_path = Path("config/prompts/extraction.md")
        if prompt_path.exists():
            self.base_prompt = prompt_path.read_text()
        else:
            # Fallback prompt
            self.base_prompt = self._default_prompt()
        
        # Initialize LLM client
        model = self.config.get("model", settings.llm.extraction_model)
        self.llm = LLMClient(model=model, temperature=0.0)
    
    def _default_prompt(self) -> str:
        """Default extraction prompt if file not found."""
        return """Extract entities and relationships from the text. Return JSON with "entities" and "relationships" arrays."""
    
    async def extract(self, chunk: DocumentChunk) -> ExtractionResult:
        """
        Extract entities and relationships from a document chunk.
        
        Args:
            chunk: DocumentChunk to extract from
        
        Returns:
            ExtractionResult with entities and relationships
        """
        # Build prompt
        prompt = self.base_prompt.replace("{chunk_text}", chunk.text)
        
        # Define JSON schema for structured output
        schema = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "type", "description"]
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["source", "target", "type", "description"]
                    }
                }
            },
            "required": ["entities", "relationships"]
        }
        
        try:
            # Get structured completion
            response = await self.llm.get_structured_completion(
                prompt=prompt,
                schema=schema,
                system_prompt="You are a distributed systems expert extracting structured knowledge."
            )
            
            # Parse and validate
            entities = self._parse_entities(response.get("entities", []), chunk.content_hash)
            relationships = self._parse_relationships(
                response.get("relationships", []),
                chunk.content_hash
            )
            
            return ExtractionResult(
                entities=entities,
                relationships=relationships,
                raw_response=json.dumps(response)
            )
        
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failure for chunk {chunk.content_hash}: {str(e)}")
            # Retry once with text completion
            try:
                text_response = await self.llm.get_completion(prompt)
                # Try to extract JSON from text
                response = self._extract_json_from_text(text_response)
                entities = self._parse_entities(response.get("entities", []), chunk.content_hash)
                relationships = self._parse_relationships(
                    response.get("relationships", []),
                    chunk.content_hash
                )
                return ExtractionResult(
                    entities=entities,
                    relationships=relationships,
                    raw_response=text_response,
                    extraction_errors=[f"Initial JSON parse failed, retried: {str(e)}"]
                )
            except Exception as retry_error:
                logger.error(f"Extraction failed after retry: {str(retry_error)}")
                return ExtractionResult(
                    entities=[],
                    relationships=[],
                    raw_response=text_response if 'text_response' in locals() else None,
                    extraction_errors=[str(e), str(retry_error)]
                )
        
        except Exception as e:
            logger.error(f"Extraction error for chunk {chunk.content_hash}: {str(e)}")
            return ExtractionResult(
                entities=[],
                relationships=[],
                extraction_errors=[str(e)]
            )
    
    async def extract_with_gleanings(
        self,
        chunk: DocumentChunk,
        max_rounds: int = 2
    ) -> ExtractionResult:
        """
        Multi-turn extraction with gleanings (re-extraction to find missed entities).
        
        Args:
            chunk: DocumentChunk to extract from
            max_rounds: Maximum number of extraction rounds
        
        Returns:
            Merged ExtractionResult from all rounds
        """
        all_entities = []
        all_relationships = []
        all_errors = []
        
        # First extraction
        result = await self.extract(chunk)
        all_entities.extend(result.entities)
        all_relationships.extend(result.relationships)
        all_errors.extend(result.extraction_errors)
        
        # Gleanings rounds
        for round_num in range(1, max_rounds):
            # Check if we found new entities
            if not result.entities and not result.relationships:
                break
            
            # Re-prompt asking for additional entities
            gleaning_prompt = f"""
            Previous extraction found:
            Entities: {len(result.entities)}
            Relationships: {len(result.relationships)}
            
            Re-read the text and find any additional entities or relationships that were missed:
            
            {chunk.text}
            
            Return JSON with any additional entities and relationships not found in the previous extraction.
            """
            
            try:
                gleaning_result = await self.extract(chunk)
                # Merge results
                all_entities.extend(gleaning_result.entities)
                all_relationships.extend(gleaning_result.relationships)
                all_errors.extend(gleaning_result.extraction_errors)
                
                # If no new entities found, stop
                if not gleaning_result.entities and not gleaning_result.relationships:
                    break
            
            except Exception as e:
                logger.warning(f"Gleaning round {round_num} failed: {str(e)}")
                all_errors.append(f"Gleaning round {round_num}: {str(e)}")
                break
        
        # Deduplicate entities and relationships
        unique_entities = self._deduplicate_entities(all_entities)
        unique_relationships = self._deduplicate_relationships(all_relationships)
        
        return ExtractionResult(
            entities=unique_entities,
            relationships=unique_relationships,
            extraction_errors=all_errors
        )
    
    def _parse_entities(
        self,
        entities_data: List[Dict[str, Any]],
        chunk_hash: Optional[str]
    ) -> List[Entity]:
        """Parse and validate entities."""
        entities = []
        
        for entity_data in entities_data:
            name = entity_data.get("name", "").strip()
            entity_type = entity_data.get("type", "").strip().upper()
            description = entity_data.get("description", "").strip()
            
            if not name:
                continue
            
            # Validate entity type
            if entity_type not in self.allowed_entity_types:
                logger.warning(f"Invalid entity type: {entity_type}, using CONCEPT")
                entity_type = "CONCEPT"
            
            entities.append(Entity(
                name=name,
                type=entity_type,
                description=description,
                source_chunk_hash=chunk_hash
            ))
        
        return entities
    
    def _parse_relationships(
        self,
        relationships_data: List[Dict[str, Any]],
        chunk_hash: Optional[str]
    ) -> List[Relationship]:
        """Parse and validate relationships."""
        relationships = []
        
        for rel_data in relationships_data:
            source = rel_data.get("source", "").strip()
            target = rel_data.get("target", "").strip()
            rel_type = rel_data.get("type", "").strip().upper()
            description = rel_data.get("description", "").strip()
            
            if not source or not target:
                continue
            
            # Validate relationship type
            if rel_type not in self.allowed_relationship_types:
                logger.warning(f"Invalid relationship type: {rel_type}, skipping")
                continue
            
            relationships.append(Relationship(
                source=source,
                target=target,
                type=rel_type,
                description=description,
                source_chunk_hash=chunk_hash
            ))
        
        return relationships
    
    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text response (handles markdown code fences)."""
        # Remove markdown code fences
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end]
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end]
        
        # Find JSON object
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        
        raise json.JSONDecodeError("No JSON found in text", text, 0)
    
    def _deduplicate_entities(self, entities: List[Entity]) -> List[Entity]:
        """Remove duplicate entities (same name and type)."""
        seen = set()
        unique = []
        
        for entity in entities:
            key = (entity.name.lower(), entity.type)
            if key not in seen:
                seen.add(key)
                unique.append(entity)
        
        return unique
    
    def _deduplicate_relationships(self, relationships: List[Relationship]) -> List[Relationship]:
        """Remove duplicate relationships."""
        seen = set()
        unique = []
        
        for rel in relationships:
            key = (rel.source.lower(), rel.target.lower(), rel.type)
            if key not in seen:
                seen.add(key)
                unique.append(rel)
        
        return unique
