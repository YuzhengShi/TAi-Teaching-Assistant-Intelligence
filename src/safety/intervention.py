"""
Intervention protocol: triggers for professor notification.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from src.shared.logging import get_logger

logger = get_logger(__name__)


class InterventionSeverity(str, Enum):
    """Intervention severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMEDIATE = "immediate"


@dataclass
class Intervention:
    """Intervention record."""
    trigger: str
    severity: InterventionSeverity
    student_id: str
    context: Dict[str, Any]
    message: str
    timestamp: str


class InterventionProtocol:
    """Defines when AI should defer to human professor."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Trigger thresholds
        self.triggers = {
            "knowledge_gap": {
                "error_count_threshold": 5,
                "concept_repetitions_threshold": 3,
                "time_on_concept_seconds": 600,
                "severity": InterventionSeverity.MEDIUM
            },
            "safety_concern": {
                "keywords": [
                    "self harm",
                    "suicide",
                    "kill myself",
                    "want to die",
                    "hurt myself",
                    "bullying",
                    "harassment",
                    "threat",
                    "hurt someone",
                ],
                "severity": InterventionSeverity.IMMEDIATE
            },
            "assessment_discrepancy": {
                "score_variance_threshold": 2.0,
                "low_confidence_threshold": 0.6,
                "severity": InterventionSeverity.HIGH
            },
            "pedagogical_boundary": {
                "severity": InterventionSeverity.MEDIUM
            },
            "student_distress": {
                "severity": InterventionSeverity.HIGH
            },
            "system_uncertainty": {
                "severity": InterventionSeverity.LOW
            }
        }
    
    def check(self, context: Dict[str, Any]) -> List[Intervention]:
        """
        Check all intervention triggers.
        
        Args:
            context: Session context with student_id, messages, scores, etc.
        
        Returns:
            List of triggered interventions
        """
        interventions = []
        
        # Check each trigger
        if self._check_knowledge_gap(context):
            interventions.append(self._create_intervention(
                "knowledge_gap",
                self.triggers["knowledge_gap"]["severity"],
                context
            ))
        
        if self._check_safety_concern(context):
            interventions.append(self._create_intervention(
                "safety_concern",
                self.triggers["safety_concern"]["severity"],
                context
            ))
        
        if self._check_assessment_discrepancy(context):
            interventions.append(self._create_intervention(
                "assessment_discrepancy",
                self.triggers["assessment_discrepancy"]["severity"],
                context
            ))
        
        return interventions
    
    def _check_knowledge_gap(self, context: Dict) -> bool:
        """Check if student has fundamental knowledge gap."""
        error_count = context.get("error_count", 0)
        concept_repetitions = context.get("concept_repetitions", 0)
        time_on_concept = context.get("time_on_concept_seconds", 0)
        
        threshold = self.triggers["knowledge_gap"]
        
        if error_count > threshold["error_count_threshold"]:
            return True
        
        if concept_repetitions > threshold["concept_repetitions_threshold"]:
            return True
        
        if time_on_concept > threshold["time_on_concept_seconds"]:
            return True
        
        return False
    
    def _check_safety_concern(self, context: Dict) -> bool:
        """Check for safety or integrity concerns."""
        last_message = context.get("last_message", "").lower()
        
        keywords = self.triggers["safety_concern"]["keywords"]
        
        for keyword in keywords:
            if keyword in last_message:
                return True
        
        return False
    
    def _check_assessment_discrepancy(self, context: Dict) -> bool:
        """Check for low-confidence automated assessment."""
        evaluation_results = context.get("evaluation_results", [])
        
        if not evaluation_results:
            return False
        
        # Check variance
        scores = [r.get("score", 0) for r in evaluation_results]
        if len(scores) >= 3:
            import statistics
            if len(scores) > 1:
                variance = statistics.variance(scores)
                if variance > self.triggers["assessment_discrepancy"]["score_variance_threshold"]:
                    return True
        
        # Check confidence
        low_confidence = [
            r for r in evaluation_results 
            if r.get("confidence", 1.0) < self.triggers["assessment_discrepancy"]["low_confidence_threshold"]
        ]
        
        if len(low_confidence) >= 2:
            return True
        
        return False
    
    def _create_intervention(
        self,
        trigger: str,
        severity: InterventionSeverity,
        context: Dict
    ) -> Intervention:
        """Create intervention record."""
        from datetime import datetime
        
        messages = {
            "knowledge_gap": "Student showing persistent knowledge gaps - may need additional support",
            "safety_concern": "URGENT: Safety concern detected - immediate review required",
            "assessment_discrepancy": "Assessment confidence low - human review recommended"
        }
        
        return Intervention(
            trigger=trigger,
            severity=severity,
            student_id=context.get("student_id", "unknown"),
            context=context,
            message=messages.get(trigger, f"Intervention triggered: {trigger}"),
            timestamp=datetime.now().isoformat()
        )
