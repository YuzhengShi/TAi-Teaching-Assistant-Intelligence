"""
Ingestor for lecture transcripts.
Removes filler words and segments by topic/timestamp.
"""

from pathlib import Path
from typing import List
import re

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk


class TranscriptIngestor(BaseIngestor):
    """Ingest lecture transcripts with filler word removal."""
    
    # Common filler words to remove
    FILLER_WORDS = {
        'um', 'uh', 'er', 'ah', 'like', 'you know', 'actually',
        'basically', 'literally', 'sort of', 'kind of', 'I mean'
    }
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is text or SRT."""
        suffix = path.suffix.lower()
        return suffix in ['.txt', '.srt', '.transcript']
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest transcript with filler removal and topic segmentation."""
        chunks = []
        
        try:
            text = path.read_text(encoding='utf-8')
            source_name = path.stem
            
            # Remove filler words
            cleaned_text = self._remove_fillers(text)
            
            # Segment by topic markers or timestamps
            segments = self._segment_transcript(cleaned_text)
            
            # Extract lecture number from filename or content
            lecture_num = self._extract_lecture_number(source_name, text)
            
            for segment_num, segment_text in enumerate(segments):
                if segment_text.strip():
                    chunk = self._create_chunk(
                        text=segment_text.strip(),
                        source_type="lecture_transcript",
                        source_name=source_name,
                        lecture_number=lecture_num,
                        segment_number=segment_num + 1,
                        total_segments=len(segments)
                    )
                    chunks.append(chunk)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest transcript {path}: {str(e)}") from e
        
        return chunks
    
    def _remove_fillers(self, text: str) -> str:
        """Remove filler words from transcript."""
        words = text.split()
        cleaned_words = []
        
        for word in words:
            # Remove punctuation for comparison
            word_clean = re.sub(r'[^\w\s]', '', word.lower())
            if word_clean not in self.FILLER_WORDS:
                cleaned_words.append(word)
        
        return ' '.join(cleaned_words)
    
    def _segment_transcript(self, text: str) -> List[str]:
        """Segment transcript by topic markers or timestamps."""
        segments = []
        
        # Try to detect timestamps (HH:MM:SS or MM:SS)
        timestamp_pattern = r'\d{1,2}:\d{2}(?::\d{2})?'
        
        # Try to detect topic markers
        topic_markers = [
            r'^\s*(Next|Now|Moving on|Let\'s talk about|Topic|Section)',
            r'^\s*\d+\.',  # Numbered topics
        ]
        
        lines = text.split('\n')
        current_segment = []
        
        for line in lines:
            # Check for timestamp
            if re.search(timestamp_pattern, line):
                # Save current segment if it has content
                if current_segment:
                    segments.append('\n'.join(current_segment))
                    current_segment = []
                # Skip timestamp line
                continue
            
            # Check for topic marker
            is_topic_marker = False
            for pattern in topic_markers:
                if re.match(pattern, line, re.IGNORECASE):
                    # Save current segment
                    if current_segment:
                        segments.append('\n'.join(current_segment))
                        current_segment = []
                    is_topic_marker = True
                    break
            
            if not is_topic_marker:
                current_segment.append(line)
        
        # Add final segment
        if current_segment:
            segments.append('\n'.join(current_segment))
        
        # If no segments found, split by paragraphs
        if not segments:
            segments = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        return segments
    
    def _extract_lecture_number(self, filename: str, text: str) -> int:
        """Extract lecture number from filename or text."""
        # Try filename first
        match = re.search(r'lecture[_\s]?(\d+)', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Try text content
        match = re.search(r'lecture[_\s]?(\d+)', text[:500], re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Default to 1
        return 1
