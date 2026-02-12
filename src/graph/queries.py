"""
All Cypher queries for TAi graph operations.
ALL queries use parameterized syntax ($param) - NEVER string interpolation.
"""

from typing import Dict, Any, Tuple, List, Optional
from dataclasses import dataclass

from src.graph.schema import NodeType, RelationshipType


@dataclass
class QueryResult:
    """Result of a parameterized query."""
    query: str
    params: Dict[str, Any]


class CourseQueries:
    """Queries for course content (concepts, algorithms, protocols)."""
    
    @staticmethod
    def upsert_concept(name: str, description: str, concept_type: Optional[str] = None) -> QueryResult:
        """
        Upsert a concept node.
        
        Args:
            name: Concept name
            description: Concept description
            concept_type: Optional type (e.g., "consensus", "storage")
        
        Returns:
            QueryResult with parameterized query
        """
        query = """
        MERGE (c:Concept {id: $concept_id})
        SET c.name = $name,
            c.description = $description,
            c.updated_at = timestamp()
        """
        if concept_type:
            query += ", c.type = $concept_type"
        
        query += "\nRETURN c.id as id, c.name as name"
        
        # Generate deterministic ID from name
        import hashlib
        concept_id = hashlib.sha256(name.lower().encode()).hexdigest()[:16]
        
        params = {
            "concept_id": concept_id,
            "name": name,
            "description": description
        }
        if concept_type:
            params["concept_type"] = concept_type
        
        return QueryResult(query=query, params=params)
    
    @staticmethod
    def create_prerequisite_relationship(
        prerequisite_id: str,
        dependent_id: str,
        description: Optional[str] = None
    ) -> QueryResult:
        """Create PREREQUISITE_OF relationship."""
        query = """
        MATCH (prereq:Concept {id: $prerequisite_id})
        MATCH (dependent:Concept {id: $dependent_id})
        MERGE (prereq)-[r:PREREQUISITE_OF]->(dependent)
        SET r.created_at = timestamp()
        """
        if description:
            query += ", r.description = $description"
        query += "\nRETURN r"
        
        params = {
            "prerequisite_id": prerequisite_id,
            "dependent_id": dependent_id
        }
        if description:
            params["description"] = description
        
        return QueryResult(query=query, params=params)
    
    @staticmethod
    def find_concept_by_name(name: str) -> QueryResult:
        """Find concept by name (case-insensitive)."""
        query = """
        MATCH (c:Concept)
        WHERE toLower(c.name) = toLower($name)
        RETURN c.id as id, c.name as name, c.description as description
        LIMIT 1
        """
        return QueryResult(query=query, params={"name": name})
    
    @staticmethod
    def get_concept_neighborhood(concept_id: str, hops: int = 2) -> QueryResult:
        """Get concept and its graph neighborhood."""
        # Validate hops to prevent injection — must be 1, 2, or 3
        safe_hops = max(1, min(int(hops), 3))
        # Use a pre-built query per hop level (no string interpolation)
        queries_by_hops = {
            1: """
            MATCH path = (c:Concept {id: $concept_id})-[*1..1]-(related)
            RETURN path, c, related
            LIMIT 50
            """,
            2: """
            MATCH path = (c:Concept {id: $concept_id})-[*1..2]-(related)
            RETURN path, c, related
            LIMIT 50
            """,
            3: """
            MATCH path = (c:Concept {id: $concept_id})-[*1..3]-(related)
            RETURN path, c, related
            LIMIT 50
            """,
        }
        query = queries_by_hops[safe_hops]
        return QueryResult(query=query, params={"concept_id": concept_id})


class StudentQueries:
    """Queries for student data and learning progress."""
    
    @staticmethod
    def upsert_student(student_id: str, anonymized_id: str) -> QueryResult:
        """Upsert student node."""
        query = """
        MERGE (s:Student {id: $student_id})
        SET s.anonymized_id = $anonymized_id,
            s.updated_at = timestamp()
        ON CREATE SET s.created_at = timestamp()
        RETURN s.id as id, s.anonymized_id as anonymized_id
        """
        return QueryResult(query=query, params={
            "student_id": student_id,
            "anonymized_id": anonymized_id
        })
    
    @staticmethod
    def create_understanding_relationship(
        student_id: str,
        concept_id: str,
        confidence: float,
        context_scope: str,
        demonstrated_via: str,
        stability: Optional[float] = None
    ) -> QueryResult:
        """Create UNDERSTANDS relationship with graduated understanding schema."""
        query = """
        MATCH (s:Student {id: $student_id})
        MATCH (c:Concept {id: $concept_id})
        MERGE (s)-[r:UNDERSTANDS]->(c)
        SET r.confidence = $confidence,
            r.context_scope = $context_scope,
            r.demonstrated_via = $demonstrated_via,
            r.last_evidence = timestamp(),
            r.updated_at = timestamp()
        """
        if stability is not None:
            query += ", r.stability = $stability"
        
        query += "\nON CREATE SET r.created_at = timestamp()\nRETURN r"
        
        params = {
            "student_id": student_id,
            "concept_id": concept_id,
            "confidence": confidence,
            "context_scope": context_scope,
            "demonstrated_via": demonstrated_via
        }
        if stability is not None:
            params["stability"] = stability
        
        return QueryResult(query=query, params=params)
    
    @staticmethod
    def get_student_understandings(
        student_id: str,
        min_confidence: float = 0.0,
        context_scope: Optional[str] = None
    ) -> QueryResult:
        """Get all concepts a student understands."""
        query = """
        MATCH (s:Student {id: $student_id})-[r:UNDERSTANDS]->(c:Concept)
        WHERE r.confidence >= $min_confidence
        """
        if context_scope:
            query += " AND r.context_scope = $context_scope"
        
        query += """
        RETURN c.id as concept_id, c.name as concept_name,
               r.confidence as confidence, r.context_scope as context_scope,
               r.demonstrated_via as demonstrated_via,
               r.last_evidence as last_evidence
        ORDER BY r.confidence DESC
        """
        
        params = {
            "student_id": student_id,
            "min_confidence": min_confidence
        }
        if context_scope:
            params["context_scope"] = context_scope
        
        return QueryResult(query=query, params=params)
    
    @staticmethod
    def get_prerequisite_gaps(student_id: str, target_concept_id: str) -> QueryResult:
        """Find prerequisite concepts student hasn't mastered."""
        query = """
        MATCH (target:Concept {id: $target_concept_id})
        MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*]->(target)
        WHERE NOT EXISTS {
            MATCH (s:Student {id: $student_id})-[r:UNDERSTANDS]->(prereq)
            WHERE r.confidence >= 0.6
        }
        RETURN DISTINCT prereq.id as concept_id, prereq.name as concept_name
        """
        return QueryResult(query=query, params={
            "student_id": student_id,
            "target_concept_id": target_concept_id
        })


class MisconceptionQueries:
    """Queries for misconception detection and management."""
    
    @staticmethod
    def upsert_misconception(
        description: str,
        contradicts_concept_id: str,
        confirmed: bool = False,
        frequency: int = 1
    ) -> QueryResult:
        """Upsert misconception node."""
        import hashlib
        misconception_id = hashlib.sha256(description.lower().encode()).hexdigest()[:16]
        
        query = """
        MERGE (m:Misconception {id: $misconception_id})
        SET m.description = $description,
            m.confirmed = $confirmed,
            m.frequency = $frequency,
            m.updated_at = timestamp()
        ON CREATE SET m.created_at = timestamp(),
                      m.first_seen = timestamp()
        
        WITH m
        MATCH (c:Concept {id: $contradicts_concept_id})
        MERGE (c)-[r:HAS_CANDIDATE_MISCONCEPTION]->(m)
        SET r.updated_at = timestamp()
        ON CREATE SET r.created_at = timestamp()
        
        RETURN m.id as id, m.description as description, m.confirmed as confirmed
        """
        
        return QueryResult(query=query, params={
            "misconception_id": misconception_id,
            "description": description,
            "contradicts_concept_id": contradicts_concept_id,
            "confirmed": confirmed,
            "frequency": frequency
        })
    
    @staticmethod
    def increment_misconception_frequency(misconception_id: str) -> QueryResult:
        """Increment frequency and check confirmation threshold."""
        query = """
        MATCH (m:Misconception {id: $misconception_id})
        SET m.frequency = m.frequency + 1,
            m.updated_at = timestamp()
        WITH m
        WHERE m.frequency >= 3 AND m.confirmed = false
        SET m.confirmed = true
        RETURN m.id as id, m.frequency as frequency, m.confirmed as confirmed
        """
        return QueryResult(query=query, params={"misconception_id": misconception_id})
    
    @staticmethod
    def get_confirmed_misconceptions_for_concept(concept_id: str) -> QueryResult:
        """Get confirmed misconceptions for a concept."""
        query = """
        MATCH (c:Concept {id: $concept_id})-[r:HAS_CANDIDATE_MISCONCEPTION]->(m:Misconception)
        WHERE m.confirmed = true
        RETURN m.id as id, m.description as description, m.frequency as frequency
        ORDER BY m.frequency DESC
        """
        return QueryResult(query=query, params={"concept_id": concept_id})
    
    @staticmethod
    def get_pending_review_candidates(min_frequency: int = 3) -> QueryResult:
        """Get misconception candidates pending professor review."""
        query = """
        MATCH (m:Misconception)
        WHERE m.frequency >= $min_frequency AND m.confirmed = false
        MATCH (c:Concept)-[:HAS_CANDIDATE_MISCONCEPTION]->(m)
        RETURN m.id as id, m.description as description,
               m.frequency as frequency, m.first_seen as first_seen,
               collect(DISTINCT c.name) as related_concepts
        ORDER BY m.frequency DESC
        """
        return QueryResult(query=query, params={"min_frequency": min_frequency})


class ProfileQueries:
    """Queries for generating student profiles."""
    
    @staticmethod
    def get_student_profile_data(
        student_id: str,
        topic_concept_id: Optional[str] = None
    ) -> QueryResult:
        """Get comprehensive student profile data for a topic."""
        query = """
        MATCH (s:Student {id: $student_id})
        
        // Get all understandings
        OPTIONAL MATCH (s)-[r:UNDERSTANDS]->(c:Concept)
        WITH s, collect({
            concept_id: c.id,
            concept_name: c.name,
            confidence: r.confidence,
            context_scope: r.context_scope,
            demonstrated_via: r.demonstrated_via,
            last_evidence: r.last_evidence
        }) as understandings
        
        // Get prerequisite gaps if topic specified
        """
        if topic_concept_id:
            query += """
            OPTIONAL MATCH (target:Concept {id: $topic_concept_id})
            OPTIONAL MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*]->(target)
            WHERE NOT EXISTS {
                MATCH (s)-[r:UNDERSTANDS]->(prereq)
                WHERE r.confidence >= 0.6
            }
            WITH s, understandings, collect(DISTINCT {
                concept_id: prereq.id,
                concept_name: prereq.name
            }) as gaps
            """
        else:
            query += """
            WITH s, understandings, [] as gaps
            """
        
        query += """
        // Get recent misconceptions
        OPTIONAL MATCH (s)-[:UNDERSTANDS]->(c:Concept)-[:HAS_CANDIDATE_MISCONCEPTION]->(m:Misconception)
        WHERE m.confirmed = true
        WITH s, understandings, gaps, collect(DISTINCT {
            misconception_id: m.id,
            description: m.description,
            concept_name: c.name
        }) as misconceptions
        
        RETURN s.id as student_id,
               s.anonymized_id as anonymized_id,
               understandings,
               gaps,
               misconceptions
        """
        
        params = {"student_id": student_id}
        if topic_concept_id:
            params["topic_concept_id"] = topic_concept_id
        
        return QueryResult(query=query, params=params)
    
    @staticmethod
    def get_concept_mastery_distribution() -> QueryResult:
        """Get class-wide concept mastery distribution for heatmap."""
        query = """
        MATCH (s:Student)-[r:UNDERSTANDS]->(c:Concept)
        WITH c.id as concept_id, c.name as concept_name,
             avg(r.confidence) as avg_confidence,
             count(DISTINCT s) as student_count
        RETURN concept_id, concept_name, avg_confidence, student_count
        ORDER BY avg_confidence DESC
        """
        return QueryResult(query=query, params={})
