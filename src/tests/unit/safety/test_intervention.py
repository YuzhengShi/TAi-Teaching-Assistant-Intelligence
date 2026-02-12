"""
Tests for intervention protocol.
"""

import pytest
from src.safety.intervention import InterventionProtocol, InterventionSeverity


def test_safety_concern_triggers_immediately():
    """Test that safety concern keywords trigger IMMEDIATE severity."""
    protocol = InterventionProtocol()
    
    context = {
        "student_id": "test_student",
        "last_message": "I want to hurt myself",
        "error_count": 0
    }
    
    interventions = protocol.check(context)
    
    assert len(interventions) >= 1
    safety_interventions = [i for i in interventions if i.trigger == "safety_concern"]
    assert len(safety_interventions) == 1
    assert safety_interventions[0].severity == InterventionSeverity.IMMEDIATE


def test_knowledge_gap_triggers_after_threshold():
    """Test that knowledge gap triggers after error threshold."""
    protocol = InterventionProtocol()
    
    # Below threshold
    context_low = {
        "student_id": "test_student",
        "last_message": "I'm confused about Raft",
        "error_count": 3,
    }
    
    interventions = protocol.check(context_low)
    knowledge_gaps = [i for i in interventions if i.trigger == "knowledge_gap"]
    assert len(knowledge_gaps) == 0
    
    # Above threshold
    context_high = {
        "student_id": "test_student",
        "last_message": "I'm confused about Raft",
        "error_count": 6,
    }
    
    interventions = protocol.check(context_high)
    knowledge_gaps = [i for i in interventions if i.trigger == "knowledge_gap"]
    assert len(knowledge_gaps) == 1
    assert knowledge_gaps[0].severity == InterventionSeverity.MEDIUM


def test_assessment_discrepancy_low_confidence():
    """Test that low-confidence assessments trigger intervention."""
    protocol = InterventionProtocol()
    
    context = {
        "student_id": "test_student",
        "last_message": "Here's my submission",
        "evaluation_results": [
            {"score": 8, "confidence": 0.3},
            {"score": 9, "confidence": 0.4},
        ]
    }
    
    interventions = protocol.check(context)
    discrepancies = [i for i in interventions if i.trigger == "assessment_discrepancy"]
    assert len(discrepancies) == 1


def test_no_interventions_on_normal_context():
    """Test that normal context triggers no interventions."""
    protocol = InterventionProtocol()
    
    context = {
        "student_id": "test_student",
        "last_message": "Can you explain Raft?",
        "error_count": 1,
    }
    
    interventions = protocol.check(context)
    assert len(interventions) == 0
