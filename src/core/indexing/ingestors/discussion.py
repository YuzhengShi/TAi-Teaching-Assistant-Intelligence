"""
Ingestor for discussion board posts (JSON export).
Anonymizes student names and classifies post types.
"""

from pathlib import Path
from typing import List, Dict, Any
import json
import re
import hashlib

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk


class DiscussionIngestor(BaseIngestor):
    """Ingest discussion board posts with anonymization."""
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is JSON."""
        return path.suffix.lower() == '.json'
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest discussion posts with anonymization."""
        chunks = []
        
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            source_name = path.stem
            
            # Handle different JSON structures
            posts = data.get('posts', [])
            if not posts and isinstance(data, list):
                posts = data
            
            # Anonymize student IDs
            student_map = {}  # original_id -> anonymized_id
            
            for post in posts:
                # Extract post data
                post_id = post.get('id', '')
                author = post.get('author', '')
                content = post.get('content', '')
                post_type = self._classify_post(content)
                timestamp = post.get('timestamp', '')
                thread_id = post.get('thread_id', '')
                
                # Anonymize author
                if author and author not in student_map:
                    # Create deterministic anonymized ID
                    anonymized = hashlib.sha256(author.encode()).hexdigest()[:8]
                    student_map[author] = f"student_{anonymized}"
                
                anonymized_author = student_map.get(author, "anonymous")
                
                # Create chunk
                chunk_text = f"[{post_type.upper()}] {content}"
                
                chunk = self._create_chunk(
                    text=chunk_text,
                    source_type="discussion_post",
                    source_name=source_name,
                    post_id=post_id,
                    author_anonymized=anonymized_author,
                    post_type=post_type,
                    timestamp=timestamp,
                    thread_id=thread_id
                )
                chunks.append(chunk)
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {str(e)}") from e
        except Exception as e:
            raise ValueError(f"Failed to ingest discussion {path}: {str(e)}") from e
        
        return chunks
    
    def _classify_post(self, content: str) -> str:
        """Classify post type: question, answer, confusion, insight."""
        content_lower = content.lower()
        
        # Question indicators
        if any(word in content_lower for word in ['?', 'how', 'what', 'why', 'when', 'where', 'can someone', 'does anyone']):
            return "question"
        
        # Confusion indicators
        if any(phrase in content_lower for phrase in [
            "don't understand", "confused", "unclear", "not sure",
            "doesn't make sense", "stuck", "help"
        ]):
            return "confusion"
        
        # Insight indicators
        if any(phrase in content_lower for phrase in [
            "i think", "my understanding", "note that", "important",
            "key point", "realize", "insight"
        ]):
            return "insight"
        
        # Answer indicators
        if any(phrase in content_lower for phrase in [
            "the answer", "solution", "you can", "try this",
            "according to", "the way to"
        ]):
            return "answer"
        
        # Default
        return "general"
