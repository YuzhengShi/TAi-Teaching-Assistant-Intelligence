"""
Consent system with exact match validation and session token binding.
"""

import hashlib
from typing import Optional, Dict, Any
from datetime import datetime

from src.memory.store import SafeMemoryStore
from src.shared.exceptions import ConsentRequiredError, SecurityViolationError
from src.shared.logging import get_logger

logger = get_logger(__name__)


class ConsentManager:
    """Manages student consent with exact match validation."""
    
    # Exact phrases that are accepted (case-insensitive)
    VALID_CONSENT_PHRASES = {
        "I CONSENT",
        "I AGREE",
        "YES I CONSENT"
    }
    
    def __init__(self, memory_store: SafeMemoryStore):
        self.memory_store = memory_store
        self.session_tokens = {}  # student_id -> session_token
    
    def require_consent(self, student_id: str) -> Dict[str, Any]:
        """Return consent requirement information."""
        has_consent = self.memory_store.require_consent(student_id)
        
        if has_consent:
            return {
                "required": False,
                "has_consent": True
            }
        
        return {
            "required": True,
            "has_consent": False,
            "consent_text": "I CONSENT",
            "ferpa_link": "https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html",
            "storage_duration": "365 days"
        }
    
    def grant_consent(
        self,
        student_id: str,
        consent_text: str,
        session_token: str
    ) -> Dict[str, Any]:
        """
        Grant consent with exact match validation and session token verification.
        
        Raises:
            SecurityViolationError if session token invalid
            ConsentRequiredError if consent text doesn't match exactly
        """
        # Normalize consent text
        normalized = consent_text.strip().upper()
        
        # Exact match check (NOT substring)
        if normalized not in self.VALID_CONSENT_PHRASES:
            raise ConsentRequiredError(
                f"Consent text must be exactly one of: {', '.join(self.VALID_CONSENT_PHRASES)}"
            )
        
        # Verify session token
        if not self._verify_session_token(student_id, session_token):
            raise SecurityViolationError("Invalid session token for consent grant")
        
        # Record consent
        with self.memory_store._get_connection() as conn:
            # Upsert student
            conn.execute(
                """INSERT OR IGNORE INTO students (id, anonymized_id)
                   VALUES (?, ?)""",
                (student_id, self._anonymize_id(student_id))
            )
            
            # Update consent
            conn.execute(
                """UPDATE students
                   SET consent_granted = 1,
                       consent_timestamp = ?,
                       consent_text = ?,
                       consent_session_token = ?
                   WHERE id = ?""",
                (
                    datetime.now().isoformat(),
                    consent_text[:100],  # Truncate
                    session_token,
                    student_id
                )
            )
        
        logger.info(f"Consent granted for student {student_id}", extra={
            "student_id": self._anonymize_id(student_id),
            "action": "consent_granted"
        })
        
        return {
            "success": True,
            "student_id": student_id,
            "granted_at": datetime.now().isoformat()
        }
    
    def has_consent(self, student_id: str) -> bool:
        """Check if student has granted consent."""
        return self.memory_store.require_consent(student_id)
    
    def _verify_session_token(self, student_id: str, session_token: str) -> bool:
        """Verify session token to prevent replay attacks."""
        # If consent already recorded in the database, only allow when this
        # session has an active token that matches the stored token.
        with self.memory_store._get_connection() as conn:
            row = conn.execute(
                "SELECT consent_granted, consent_session_token FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()

        if row and row["consent_granted"]:
            stored_token = row["consent_session_token"]
            # For an existing consent record, require that the in-memory session
            # mapping already knows about this token. Clearing session_tokens()
            # simulates a new session; reusing the old token then counts as replay.
            expected_token = self.session_tokens.get(student_id)
            if expected_token is None:
                return False
            return expected_token == session_token == stored_token

        # First-time consent: bind token to this session
        self.session_tokens[student_id] = session_token
        return True
    
    def _anonymize_id(self, student_id: str) -> str:
        """Anonymize student ID for logging."""
        return hashlib.sha256(student_id.encode()).hexdigest()[:16]
