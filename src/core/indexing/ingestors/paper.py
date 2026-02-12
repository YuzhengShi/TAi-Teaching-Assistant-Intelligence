"""
Ingestor for research papers (PDF).
Uses section-boundary chunking with overlap.
"""

from pathlib import Path
from typing import List
import fitz  # PyMuPDF
import re

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk
from src.shared.config import settings
from src.shared.tokens import count_tokens


class PaperIngestor(BaseIngestor):
    """Ingest research papers with section-aware chunking."""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.chunk_size = self.config.get("chunk_size", settings.indexing.chunk_size)
        self.chunk_overlap = self.config.get("chunk_overlap", settings.indexing.chunk_overlap)
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is PDF."""
        return path.suffix.lower() == '.pdf'
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest paper with section-boundary chunking."""
        chunks = []
        
        try:
            doc = fitz.open(path)
            source_name = path.stem
            
            # Extract full text
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            doc.close()
            
            # Identify sections
            sections = self._identify_sections(full_text)
            
            # Chunk each section with overlap
            for section_name, section_text in sections:
                section_chunks = self._chunk_with_overlap(
                    section_text,
                    source_name,
                    section_name
                )
                chunks.extend(section_chunks)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest paper {path}: {str(e)}") from e
        
        return chunks
    
    def _identify_sections(self, text: str) -> List[tuple[str, str]]:
        """Identify paper sections (Abstract, Introduction, etc.)."""
        # Common section patterns
        section_patterns = [
            r'^\s*(Abstract|Introduction|Background|Related Work|Methodology|Methods|'
            r'Implementation|Results|Discussion|Conclusion|References|Bibliography)',
            r'^\s*\d+\.\s+[A-Z][a-z]+',  # Numbered sections
            r'^\s*[A-Z][A-Z\s]+$',  # ALL CAPS headings
        ]
        
        lines = text.split('\n')
        sections = []
        current_section = "Introduction"
        current_text = []
        
        for line in lines:
            # Check if this line is a section header
            is_header = False
            for pattern in section_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    # Save previous section
                    if current_text:
                        sections.append((current_section, '\n'.join(current_text)))
                    
                    # Start new section
                    current_section = line.strip()
                    current_text = []
                    is_header = True
                    break
            
            if not is_header:
                current_text.append(line)
        
        # Add final section
        if current_text:
            sections.append((current_section, '\n'.join(current_text)))
        
        return sections
    
    def _chunk_with_overlap(
        self,
        text: str,
        source_name: str,
        section_name: str
    ) -> List[DocumentChunk]:
        """Chunk text with overlap between chunks."""
        chunks = []
        
        # Split into sentences for better chunking
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_chunk = []
        current_tokens = 0
        chunk_num = 0
        
        for sentence in sentences:
            sentence_tokens = count_tokens(sentence)
            
            # If adding this sentence would exceed chunk size
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = ' '.join(current_chunk)
                chunk = self._create_chunk(
                    text=chunk_text,
                    source_type="research_paper",
                    source_name=source_name,
                    section=section_name,
                    chunk_number=chunk_num
                )
                chunks.append(chunk)
                chunk_num += 1
                
                # Start new chunk with overlap (last N sentences)
                overlap_sentences = int(len(current_chunk) * 0.2)  # 20% overlap
                current_chunk = current_chunk[-overlap_sentences:] + [sentence]
                current_tokens = sum(count_tokens(s) for s in current_chunk)
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunk = self._create_chunk(
                text=chunk_text,
                source_type="research_paper",
                source_name=source_name,
                section=section_name,
                chunk_number=chunk_num
            )
            chunks.append(chunk)
        
        return chunks
