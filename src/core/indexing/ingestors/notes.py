"""
Ingestor for professor's written notes (Markdown/text).
Chunks by heading structure.
"""

from pathlib import Path
from typing import List
import re

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk


class NotesIngestor(BaseIngestor):
    """Ingest professor notes with heading-based chunking."""
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is Markdown or text."""
        suffix = path.suffix.lower()
        return suffix in ['.md', '.markdown', '.txt', '.notes']
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest notes with heading-based chunking."""
        chunks = []
        
        try:
            text = path.read_text(encoding='utf-8')
            source_name = path.stem
            
            # Extract topic and week from filename or content
            topic = self._extract_topic(source_name, text)
            week = self._extract_week(source_name, text)
            
            # Chunk by headings
            sections = self._chunk_by_headings(text)
            
            for section_num, (heading, content) in enumerate(sections):
                if content.strip():
                    chunk_text = f"{heading}\n\n{content}" if heading else content
                    
                    chunk = self._create_chunk(
                        text=chunk_text.strip(),
                        source_type="professor_notes",
                        source_name=source_name,
                        topic=topic,
                        week=week,
                        section_number=section_num + 1,
                        heading=heading,
                        total_sections=len(sections)
                    )
                    chunks.append(chunk)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest notes {path}: {str(e)}") from e
        
        return chunks
    
    def _chunk_by_headings(self, text: str) -> List[tuple[str, str]]:
        """Chunk text by markdown headings."""
        sections = []
        lines = text.split('\n')
        
        current_heading = ""
        current_content = []
        
        for line in lines:
            # Check for markdown heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                # Save previous section
                if current_content:
                    sections.append((current_heading, '\n'.join(current_content)))
                
                # Start new section
                current_heading = heading_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Add final section
        if current_content:
            sections.append((current_heading, '\n'.join(current_content)))
        
        return sections
    
    def _extract_topic(self, filename: str, text: str) -> str:
        """Extract topic from filename or text."""
        # Try filename first
        topics = ['mapreduce', 'raft', 'paxos', 'dht', 'consensus', 'distributed']
        for topic in topics:
            if topic.lower() in filename.lower():
                return topic.capitalize()
        
        # Try text content
        for topic in topics:
            if topic.lower() in text[:500].lower():
                return topic.capitalize()
        
        return "General"
    
    def _extract_week(self, filename: str, text: str) -> int:
        """Extract week number from filename or text."""
        # Try filename
        match = re.search(r'week[_\s]?(\d+)', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Try text
        match = re.search(r'week[_\s]?(\d+)', text[:500], re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        return 0
