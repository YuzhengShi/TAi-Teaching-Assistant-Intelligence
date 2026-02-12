"""
Pydantic models for memory system.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class StudentRecord(BaseModel):
    """Student record model."""
    id: str
    anonymized_id: str
    consent_granted: bool = False
    consent_timestamp: Optional[str] = None
    data_retention_days: int = 365


class Memory(BaseModel):
    """Memory record model."""
    id: Optional[int] = None
    student_id: str
    content: str
    content_hash: str
    version: int = 1
    extracted_events_json: Optional[str] = None
    created_at: Optional[str] = None


class StudentFact(BaseModel):
    """Student fact model."""
    id: Optional[int] = None
    student_id: str
    fact_text: str
    fact_type: str
    confidence_score: float
    graph_synced: bool = False
    created_at: Optional[str] = None


class Understanding(BaseModel):
    """Graduated understanding schema."""
    confidence: float = Field(ge=0.0, le=1.0)
    demonstrated_via: str  # "socratic_dialogue", "code_review", "mock_interview"
    last_evidence: Optional[str] = None
    stability: float = Field(ge=0.0, le=1.0, default=0.5)
    context_scope: str  # "theoretical", "implementation", "debugging", "verbal"
    decay_factor: float = Field(ge=0.0, le=1.0, default=0.05)


class LearningEvent(BaseModel):
    """Learning event extracted from conversation."""
    student_id: str
    concept_id: Optional[str] = None
    concept_name: str
    event_type: str  # "MASTERED", "STRUGGLING", "REVIEWED"
    confidence: float
    evidence_type: str
    context_scope: str
    timestamp: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
