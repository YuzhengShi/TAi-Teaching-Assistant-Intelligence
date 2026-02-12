"""
Base ingestor interface and DocumentChunk dataclass.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib


@dataclass
class DocumentChunk:
    """Represents a chunk of a document with metadata."""
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: Optional[str] = None
    
    def __post_init__(self):
        """Generate content hash if not provided."""
        if self.content_hash is None:
            self.content_hash = self._generate_hash()
    
    def _generate_hash(self) -> str:
        """Generate SHA-256 hash of text and key metadata."""
        hash_input = f"{self.text}:{self.metadata.get('source_name', '')}:{self.metadata.get('page', 0)}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "metadata": self.metadata,
            "content_hash": self.content_hash
        }


class BaseIngestor(ABC):
    """Abstract base class for document ingestors."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
    
    @abstractmethod
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """
        Ingest a document and return chunks.
        
        Args:
            path: Path to document file
        
        Returns:
            List of DocumentChunk objects
        """
        pass
    
    def can_ingest(self, path: Path) -> bool:
        """
        Check if this ingestor can handle the given file.
        
        Args:
            path: Path to file
        
        Returns:
            True if ingestor can handle this file type
        """
        return False
    
    def _create_chunk(
        self,
        text: str,
        source_type: str,
        source_name: str,
        **metadata
    ) -> DocumentChunk:
        """Helper to create a DocumentChunk with standard metadata."""
        chunk_metadata = {
            "source_type": source_type,
            "source_name": source_name,
            **metadata
        }
        return DocumentChunk(text=text, metadata=chunk_metadata)
