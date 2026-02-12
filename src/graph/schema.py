"""
Graph schema definitions and migration utilities.
Defines node types, relationship types, constraints, and indexes.
"""

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

from src.graph.connection import get_connection
from src.shared.logging import get_logger

logger = get_logger(__name__)


class NodeType(str, Enum):
    """Node type labels."""
    CONCEPT = "Concept"
    ALGORITHM = "Algorithm"
    PROTOCOL = "Protocol"
    THEOREM = "Theorem"
    PROPERTY = "Property"
    FAILURE_MODE = "FailureMode"
    SYSTEM = "System"
    DATA_STRUCTURE = "DataStructure"
    LEARNING_OBJECTIVE = "LearningObjective"
    MISCONCEPTION = "Misconception"
    SOURCE = "Source"
    STUDENT = "Student"
    PERSON = "Person"
    PAPER = "Paper"
    COMMUNITY = "Community"


class RelationshipType(str, Enum):
    """Relationship type labels."""
    PREREQUISITE_OF = "PREREQUISITE_OF"
    IMPLEMENTS = "IMPLEMENTS"
    GUARANTEES = "GUARANTEES"
    VIOLATES = "VIOLATES"
    PART_OF = "PART_OF"
    VARIANT_OF = "VARIANT_OF"
    ALTERNATIVE_TO = "ALTERNATIVE_TO"
    PROPOSED_IN = "PROPOSED_IN"
    USED_BY = "USED_BY"
    TEACHES = "TEACHES"
    INTRODUCED_IN = "INTRODUCED_IN"
    ADDRESSES = "ADDRESSES"
    UNDERSTANDS = "UNDERSTANDS"
    HAS_CANDIDATE_MISCONCEPTION = "HAS_CANDIDATE_MISCONCEPTION"
    BELONGS_TO = "BELONGS_TO"
    REQUIRES = "REQUIRES"


# Schema version tracking
SCHEMA_VERSION = "1.0.0"


def get_constraints() -> List[str]:
    """Get all Cypher constraint creation statements."""
    return [
        # Node uniqueness constraints
        f"CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:{NodeType.CONCEPT.value}) REQUIRE c.id IS UNIQUE",
        f"CREATE CONSTRAINT algorithm_id IF NOT EXISTS FOR (a:{NodeType.ALGORITHM.value}) REQUIRE a.id IS UNIQUE",
        f"CREATE CONSTRAINT protocol_id IF NOT EXISTS FOR (p:{NodeType.PROTOCOL.value}) REQUIRE p.id IS UNIQUE",
        f"CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:{NodeType.STUDENT.value}) REQUIRE s.id IS UNIQUE",
        f"CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:{NodeType.SOURCE.value}) REQUIRE s.id IS UNIQUE",
        f"CREATE CONSTRAINT misconception_id IF NOT EXISTS FOR (m:{NodeType.MISCONCEPTION.value}) REQUIRE m.id IS UNIQUE",
        f"CREATE CONSTRAINT learning_objective_id IF NOT EXISTS FOR (lo:{NodeType.LEARNING_OBJECTIVE.value}) REQUIRE lo.id IS UNIQUE",
        
        # Node property existence constraints
        f"CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:{NodeType.CONCEPT.value}) REQUIRE c.name IS NOT NULL",
        f"CREATE CONSTRAINT student_anonymized_id IF NOT EXISTS FOR (s:{NodeType.STUDENT.value}) REQUIRE s.anonymized_id IS NOT NULL",
    ]


def get_indexes() -> List[str]:
    """Get all Cypher index creation statements."""
    return [
        # Text search indexes
        f"CREATE FULLTEXT INDEX concept_name_fulltext IF NOT EXISTS FOR (c:{NodeType.CONCEPT.value}) ON EACH [c.name, c.description]",
        f"CREATE FULLTEXT INDEX algorithm_name_fulltext IF NOT EXISTS FOR (a:{NodeType.ALGORITHM.value}) ON EACH [a.name, a.description]",
        f"CREATE FULLTEXT INDEX protocol_name_fulltext IF NOT EXISTS FOR (p:{NodeType.PROTOCOL.value}) ON EACH [p.name, p.description]",
        
        # Property indexes for common queries
        f"CREATE INDEX concept_type IF NOT EXISTS FOR (c:{NodeType.CONCEPT.value}) ON (c.type)",
        f"CREATE INDEX source_type IF NOT EXISTS FOR (s:{NodeType.SOURCE.value}) ON (s.source_type)",
        f"CREATE INDEX misconception_confirmed IF NOT EXISTS FOR (m:{NodeType.MISCONCEPTION.value}) ON (m.confirmed)",
        f"CREATE INDEX misconception_frequency IF NOT EXISTS FOR (m:{NodeType.MISCONCEPTION.value}) ON (m.frequency)",
        
        # Relationship property indexes
        f"CREATE INDEX understands_confidence IF NOT EXISTS FOR ()-[r:{RelationshipType.UNDERSTANDS.value}]-() ON (r.confidence)",
        f"CREATE INDEX understands_context_scope IF NOT EXISTS FOR ()-[r:{RelationshipType.UNDERSTANDS.value}]-() ON (r.context_scope)",
    ]


async def ensure_schema():
    """
    Create all constraints and indexes idempotently.
    Uses IF NOT EXISTS to make it safe to run multiple times.
    """
    connection = get_connection()
    await connection.connect()
    
    constraints = get_constraints()
    indexes = get_indexes()
    
    async with connection.session() as session:
        # Create constraints
        for constraint in constraints:
            try:
                await session.run(constraint)
                logger.debug(f"Created constraint: {constraint[:50]}...")
            except Exception as e:
                # Constraint might already exist with different syntax
                logger.warning(f"Constraint creation skipped (may already exist): {str(e)}")
        
        # Create indexes
        for index in indexes:
            try:
                await session.run(index)
                logger.debug(f"Created index: {index[:50]}...")
            except Exception as e:
                # Index might already exist
                logger.warning(f"Index creation skipped (may already exist): {str(e)}")
        
        # Record schema version
        version_query = """
        MERGE (v:SchemaVersion {id: 'current'})
        SET v.version = $version, v.updated_at = timestamp()
        RETURN v.version as version
        """
        result = await session.run(version_query, {"version": SCHEMA_VERSION})
        record = await result.single()
        if record:
            logger.info(f"Schema version: {record['version']}")
    
    logger.info("Schema migration completed")


def ensure_schema_sync():
    """Synchronous version for CLI usage."""
    connection = get_connection()
    connection.connect_sync()
    
    constraints = get_constraints()
    indexes = get_indexes()
    
    with connection.session_sync() as session:
        # Create constraints
        for constraint in constraints:
            try:
                session.run(constraint)
            except Exception as e:
                logger.warning(f"Constraint creation skipped: {str(e)}")
        
        # Create indexes
        for index in indexes:
            try:
                session.run(index)
            except Exception as e:
                logger.warning(f"Index creation skipped: {str(e)}")
        
        # Record schema version
        version_query = """
        MERGE (v:SchemaVersion {id: 'current'})
        SET v.version = $version, v.updated_at = timestamp()
        RETURN v.version as version
        """
        result = session.run(version_query, {"version": SCHEMA_VERSION})
        record = result.single()
        if record:
            logger.info(f"Schema version: {record['version']}")
    
    logger.info("Schema migration completed (sync)")
