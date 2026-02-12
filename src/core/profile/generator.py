"""
Dynamic student profile generation from knowledge graph.
"""

from typing import Dict, Any, Optional
from pathlib import Path

from src.graph.connection import get_connection
from src.graph.queries import ProfileQueries
from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class ProfileGenerator:
    """Generate personalized student profiles from graph data."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.neo4j = get_connection()
    
    async def generate(
        self,
        student_id: str,
        topic: Optional[str] = None,
        session_type: str = "general"
    ) -> str:
        """
        Generate student profile in markdown format.
        
        Args:
            student_id: Student identifier
            topic: Optional topic/concept for focused profile
            session_type: Type of session (study, interview, assignment)
        
        Returns:
            Markdown-formatted profile
        """
        # Get profile data from graph
        profile_data = await self._get_profile_data(student_id, topic)
        
        # Format based on session type
        if session_type == "interview":
            return self._format_interview_profile(profile_data)
        elif session_type == "study":
            return self._format_study_profile(profile_data)
        elif session_type == "assignment":
            return self._format_assignment_profile(profile_data, topic)
        else:
            return self._format_general_profile(profile_data)
    
    async def _get_profile_data(
        self,
        student_id: str,
        topic: Optional[str]
    ) -> Dict[str, Any]:
        """Get profile data from graph."""
        # Find topic concept ID if provided
        topic_concept_id = None
        if topic:
            with self.neo4j.session_sync() as session:
                from src.graph.queries import CourseQueries
                query = CourseQueries.find_concept_by_name(topic)
                result = session.run(query.query, query.params)
                record = result.single()
                if record:
                    topic_concept_id = record["id"]
        
        # Get comprehensive profile data
        with self.neo4j.session_sync() as session:
            query_result = ProfileQueries.get_student_profile_data(student_id, topic_concept_id)
            result = session.run(query_result.query, query_result.params)
            record = result.single()
            
            if record:
                return {
                    "student_id": record["student_id"],
                    "understandings": record.get("understandings", []),
                    "gaps": record.get("gaps", []),
                    "misconceptions": record.get("misconceptions", [])
                }
        
        return {
            "student_id": student_id,
            "understandings": [],
            "gaps": [],
            "misconceptions": []
        }
    
    def _format_general_profile(self, data: Dict[str, Any]) -> str:
        """Format general-purpose profile."""
        parts = ["# Student Profile\n"]
        
        # Understandings
        if data.get("understandings"):
            parts.append("## Concepts Understood\n")
            for understanding in data["understandings"][:10]:  # Top 10
                confidence = understanding.get("confidence", 0)
                concept = understanding.get("concept_name", "Unknown")
                scope = understanding.get("context_scope", "general")
                parts.append(f"- **{concept}** (confidence: {confidence:.2f}, scope: {scope})")
        
        # Gaps
        if data.get("gaps"):
            parts.append("\n## Prerequisite Gaps\n")
            for gap in data["gaps"]:
                parts.append(f"- {gap.get('concept_name', 'Unknown')}")
        
        # Misconceptions
        if data.get("misconceptions"):
            parts.append("\n## Known Misconceptions\n")
            for mis in data["misconceptions"][:5]:
                parts.append(f"- {mis.get('description', 'Unknown')}")
        
        return "\n".join(parts)
    
    def _format_interview_profile(self, data: Dict[str, Any]) -> str:
        """Format profile for mock interview session."""
        parts = ["# Interview Profile\n"]
        
        # Focus on verbal understanding
        verbal_understandings = [
            u for u in data.get("understandings", [])
            if u.get("context_scope") == "verbal" or u.get("demonstrated_via") == "mock_interview"
        ]
        
        if verbal_understandings:
            parts.append("## Verbal Understanding History\n")
            for understanding in verbal_understandings[:5]:
                concept = understanding.get("concept_name", "Unknown")
                confidence = understanding.get("confidence", 0)
                parts.append(f"- {concept}: {confidence:.2f} confidence")
        
        return "\n".join(parts)
    
    def _format_study_profile(self, data: Dict[str, Any]) -> str:
        """Format profile for study session."""
        parts = ["# Study Session Profile\n"]
        
        # Focus on gaps and weak areas
        if data.get("gaps"):
            parts.append("## Prerequisites to Review\n")
            for gap in data["gaps"]:
                parts.append(f"- {gap.get('concept_name', 'Unknown')}")
        
        # Low-confidence understandings
        weak_understandings = [
            u for u in data.get("understandings", [])
            if u.get("confidence", 1.0) < 0.6
        ]
        
        if weak_understandings:
            parts.append("\n## Concepts Needing Reinforcement\n")
            for understanding in weak_understandings:
                concept = understanding.get("concept_name", "Unknown")
                confidence = understanding.get("confidence", 0)
                parts.append(f"- {concept} (confidence: {confidence:.2f})")
        
        return "\n".join(parts)
    
    def _format_assignment_profile(self, data: Dict[str, Any], topic: Optional[str]) -> str:
        """Format profile for assignment context."""
        parts = [f"# Assignment Profile: {topic or 'General'}\n"]
        
        # Prerequisite gaps for this assignment
        if data.get("gaps"):
            parts.append("## Missing Prerequisites\n")
            parts.append("Student may struggle with this assignment due to gaps in:")
            for gap in data["gaps"]:
                parts.append(f"- {gap.get('concept_name', 'Unknown')}")
        
        return "\n".join(parts)
