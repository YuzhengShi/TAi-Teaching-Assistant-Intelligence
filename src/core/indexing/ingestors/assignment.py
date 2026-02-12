"""
Ingestor for assignment specifications (PDF/Markdown).
Extracts requirements, grading criteria, and target concepts.
"""

from pathlib import Path
from typing import List, Dict, Any
import re
import fitz  # PyMuPDF

from src.core.indexing.ingestors.base import BaseIngestor, DocumentChunk


class AssignmentIngestor(BaseIngestor):
    """Ingest assignment specifications."""
    
    def can_ingest(self, path: Path) -> bool:
        """Check if file is PDF or Markdown."""
        suffix = path.suffix.lower()
        return suffix in ['.pdf', '.md', '.markdown']
    
    def ingest(self, path: Path) -> List[DocumentChunk]:
        """Ingest assignment spec."""
        suffix = path.suffix.lower()
        
        if suffix == '.pdf':
            return self._ingest_pdf(path)
        else:
            return self._ingest_markdown(path)
    
    def _ingest_pdf(self, path: Path) -> List[DocumentChunk]:
        """Ingest PDF assignment."""
        chunks = []
        
        try:
            doc = fitz.open(path)
            source_name = path.stem
            
            # Extract full text
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            doc.close()
            
            # Extract structured information
            assignment_data = self._extract_assignment_structure(full_text)
            
            # Create chunks for each section
            if assignment_data.get('title'):
                chunk = self._create_chunk(
                    text=f"Title: {assignment_data['title']}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="title"
                )
                chunks.append(chunk)
            
            if assignment_data.get('description'):
                chunk = self._create_chunk(
                    text=f"Description:\n{assignment_data['description']}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="description"
                )
                chunks.append(chunk)
            
            if assignment_data.get('requirements'):
                requirements_text = "\n".join(f"- {req}" for req in assignment_data['requirements'])
                chunk = self._create_chunk(
                    text=f"Requirements:\n{requirements_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="requirements"
                )
                chunks.append(chunk)
            
            if assignment_data.get('grading_criteria'):
                criteria_text = "\n".join(f"- {criterion}" for criterion in assignment_data['grading_criteria'])
                chunk = self._create_chunk(
                    text=f"Grading Criteria:\n{criteria_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="grading"
                )
                chunks.append(chunk)
            
            if assignment_data.get('target_concepts'):
                concepts_text = ", ".join(assignment_data['target_concepts'])
                chunk = self._create_chunk(
                    text=f"Target Concepts: {concepts_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="concepts"
                )
                chunks.append(chunk)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest PDF assignment {path}: {str(e)}") from e
        
        return chunks
    
    def _ingest_markdown(self, path: Path) -> List[DocumentChunk]:
        """Ingest Markdown assignment."""
        chunks = []
        
        try:
            text = path.read_text(encoding='utf-8')
            source_name = path.stem
            
            # Extract structured information
            assignment_data = self._extract_assignment_structure(text)
            
            # Create chunks similar to PDF
            if assignment_data.get('title'):
                chunk = self._create_chunk(
                    text=f"Title: {assignment_data['title']}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="title"
                )
                chunks.append(chunk)
            
            if assignment_data.get('description'):
                chunk = self._create_chunk(
                    text=f"Description:\n{assignment_data['description']}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="description"
                )
                chunks.append(chunk)
            
            if assignment_data.get('requirements'):
                requirements_text = "\n".join(f"- {req}" for req in assignment_data['requirements'])
                chunk = self._create_chunk(
                    text=f"Requirements:\n{requirements_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="requirements"
                )
                chunks.append(chunk)
            
            if assignment_data.get('grading_criteria'):
                criteria_text = "\n".join(f"- {criterion}" for criterion in assignment_data['grading_criteria'])
                chunk = self._create_chunk(
                    text=f"Grading Criteria:\n{criteria_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="grading"
                )
                chunks.append(chunk)
            
            if assignment_data.get('target_concepts'):
                concepts_text = ", ".join(assignment_data['target_concepts'])
                chunk = self._create_chunk(
                    text=f"Target Concepts: {concepts_text}",
                    source_type="assignment_spec",
                    source_name=source_name,
                    section="concepts"
                )
                chunks.append(chunk)
        
        except Exception as e:
            raise ValueError(f"Failed to ingest Markdown assignment {path}: {str(e)}") from e
        
        return chunks
    
    def _extract_assignment_structure(self, text: str) -> Dict[str, Any]:
        """Extract structured information from assignment text."""
        data = {
            'title': None,
            'description': None,
            'requirements': [],
            'grading_criteria': [],
            'target_concepts': []
        }
        
        lines = text.split('\n')
        
        # Extract title (usually first line or after #)
        for line in lines[:10]:
            if line.strip().startswith('#'):
                data['title'] = line.strip().lstrip('#').strip()
                break
            elif line.strip() and not data['title']:
                data['title'] = line.strip()
                break
        
        # Extract requirements section
        in_requirements = False
        for line in lines:
            if re.search(r'requirement|must|should|need to', line, re.IGNORECASE):
                in_requirements = True
                continue
            if in_requirements:
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    req = re.sub(r'^[-*]\s*', '', line.strip())
                    if req:
                        data['requirements'].append(req)
                elif line.strip() and not line.strip().startswith('#'):
                    data['requirements'].append(line.strip())
                elif line.strip().startswith('#'):
                    in_requirements = False
        
        # Extract grading criteria
        in_grading = False
        for line in lines:
            if re.search(r'grading|rubric|criteria|evaluation', line, re.IGNORECASE):
                in_grading = True
                continue
            if in_grading:
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    criterion = re.sub(r'^[-*]\s*', '', line.strip())
                    if criterion:
                        data['grading_criteria'].append(criterion)
                elif line.strip() and not line.strip().startswith('#'):
                    data['grading_criteria'].append(line.strip())
                elif line.strip().startswith('#'):
                    in_grading = False
        
        # Extract target concepts (look for concept names)
        concept_keywords = ['MapReduce', 'Raft', 'Paxos', 'DHT', 'consensus', 'distributed']
        for line in lines:
            for keyword in concept_keywords:
                if keyword.lower() in line.lower() and keyword not in data['target_concepts']:
                    data['target_concepts'].append(keyword)
        
        # Extract description (text between title and requirements)
        description_lines = []
        found_title = False
        for line in lines:
            if data['title'] and data['title'] in line:
                found_title = True
                continue
            if found_title and not any(keyword in line.lower() for keyword in ['requirement', 'grading', 'rubric']):
                if line.strip():
                    description_lines.append(line.strip())
            elif found_title and any(keyword in line.lower() for keyword in ['requirement', 'grading']):
                break
        
        if description_lines:
            data['description'] = ' '.join(description_lines)
        
        return data
