"""
Entity resolution and deduplication.
Merges entities across chunks using exact match, embedding similarity, and LLM adjudication.
"""

from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
import hashlib

from src.core.indexing.extractor import Entity
from src.shared.embeddings import EmbeddingClient
from src.shared.llm import LLMClient
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ResolvedEntity:
    """Resolved entity after deduplication."""
    canonical_name: str
    type: str
    descriptions: List[str]  # Merged descriptions
    source_chunks: Set[str]  # All source chunk hashes
    aliases: Set[str]  # Alternative names found


class EntityResolver:
    """Resolve and deduplicate entities across chunks."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.embedding_client = EmbeddingClient()
        self.llm = LLMClient(model=settings.llm.extraction_model, temperature=0.0)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.85)
    
    async def resolve(self, entities: List[Entity]) -> List[ResolvedEntity]:
        """
        Resolve entities across chunks with three-tier deduplication.
        
        Args:
            entities: List of entities from all chunks
        
        Returns:
            List of resolved (deduplicated) entities
        """
        if not entities:
            return []
        
        # Tier 1: Exact name match (case-insensitive, whitespace normalized)
        exact_groups = self._tier1_exact_match(entities)
        
        # Tier 2: Embedding similarity
        similarity_groups = await self._tier2_embedding_similarity(exact_groups)
        
        # Tier 3: LLM adjudication for ambiguous cases
        resolved_entities = await self._tier3_llm_adjudication(similarity_groups)
        
        return resolved_entities
    
    def _tier1_exact_match(self, entities: List[Entity]) -> List[List[Entity]]:
        """Tier 1: Group entities by exact name match."""
        groups: Dict[str, List[Entity]] = {}
        
        for entity in entities:
            # Normalize name: lowercase, strip whitespace
            normalized = entity.name.lower().strip()
            
            if normalized not in groups:
                groups[normalized] = []
            groups[normalized].append(entity)
        
        return list(groups.values())
    
    async def _tier2_embedding_similarity(
        self,
        groups: List[List[Entity]]
    ) -> List[List[Entity]]:
        """Tier 2: Merge groups with high embedding similarity."""
        if len(groups) <= 1:
            return groups
        
        # Embed all canonical names
        canonical_names = [group[0].name for group in groups]
        embeddings = await self.embedding_client.embed(canonical_names)
        
        # Build similarity matrix
        merged_groups = []
        processed = set()
        
        for i, group1 in enumerate(groups):
            if i in processed:
                continue
            
            current_group = group1.copy()
            emb1 = embeddings[i]
            
            # Check similarity with remaining groups
            for j, group2 in enumerate(groups[i+1:], start=i+1):
                if j in processed:
                    continue
                
                emb2 = embeddings[j]
                similarity = self.embedding_client.cosine_similarity(emb1, emb2)
                
                if similarity >= self.similarity_threshold:
                    # Merge groups
                    current_group.extend(group2)
                    processed.add(j)
            
            merged_groups.append(current_group)
            processed.add(i)
        
        return merged_groups
    
    async def _tier3_llm_adjudication(
        self,
        groups: List[List[Entity]]
    ) -> List[ResolvedEntity]:
        """Tier 3: LLM adjudication for ambiguous entity pairs."""
        resolved = []
        
        for group in groups:
            if len(group) == 1:
                # Single entity, no merging needed
                entity = group[0]
                resolved.append(ResolvedEntity(
                    canonical_name=entity.name,
                    type=entity.type,
                    descriptions=[entity.description] if entity.description else [],
                    source_chunks={entity.source_chunk_hash} if entity.source_chunk_hash else set(),
                    aliases=set()
                ))
            else:
                # Multiple entities in group - merge them
                merged = await self._merge_entity_group(group)
                resolved.append(merged)
        
        return resolved
    
    async def _merge_entity_group(self, group: List[Entity]) -> ResolvedEntity:
        """Merge a group of entities into one resolved entity."""
        # Check if all entities are truly the same using LLM
        if len(group) > 2:
            # For groups > 2, check pairwise
            should_merge = True
            for i in range(len(group) - 1):
                entity_a = group[i]
                entity_b = group[i + 1]
                
                is_same = await self._llm_check_same_entity(entity_a, entity_b)
                if not is_same:
                    should_merge = False
                    break
            
            if not should_merge:
                # Split group - use first entity as canonical
                # In production, might want more sophisticated splitting
                group = [group[0]]
        
        # Merge: use most descriptive name, concatenate descriptions
        canonical_name = self._select_canonical_name(group)
        descriptions = [e.description for e in group if e.description]
        source_chunks = {e.source_chunk_hash for e in group if e.source_chunk_hash}
        aliases = {e.name for e in group if e.name != canonical_name}
        
        # Use most common type, or first if all different
        types = [e.type for e in group]
        entity_type = max(set(types), key=types.count) if types else group[0].type
        
        return ResolvedEntity(
            canonical_name=canonical_name,
            type=entity_type,
            descriptions=descriptions,
            source_chunks=source_chunks,
            aliases=aliases
        )
    
    async def _llm_check_same_entity(self, entity_a: Entity, entity_b: Entity) -> bool:
        """Use LLM to check if two entities are the same."""
        prompt = f"""Are these two entities the same?

Entity A: {entity_a.name} ({entity_a.description})
Entity B: {entity_b.name} ({entity_b.description})

Respond with only "YES" or "NO" followed by a brief reason."""
        
        try:
            response = await self.llm.get_completion(prompt)
            response_upper = response.strip().upper()
            
            # Check for YES
            return response_upper.startswith("YES")
        
        except Exception as e:
            logger.warning(f"LLM adjudication failed: {str(e)}, defaulting to merge")
            # Default to merging if LLM fails
            return True
    
    def _select_canonical_name(self, entities: List[Entity]) -> str:
        """Select the most descriptive name as canonical."""
        # Prefer longer, more specific names
        # Prefer names without common words like "the", "a"
        scored = []
        
        for entity in entities:
            name = entity.name
            score = len(name)
            
            # Penalize common words
            common_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for'}
            words = name.lower().split()
            score -= sum(1 for w in words if w in common_words)
            
            # Bonus for having description
            if entity.description:
                score += 10
            
            scored.append((score, name))
        
        # Return highest scoring name
        scored.sort(reverse=True)
        return scored[0][1]
