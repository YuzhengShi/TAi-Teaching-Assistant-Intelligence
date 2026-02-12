"""
Session manager with per-student, per-context isolation.
"""

import sqlite3
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path

from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages isolated sessions per student and context."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("data/sessions.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize session database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_key TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                course TEXT,
                context TEXT,
                messages TEXT,  -- JSON array
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection with row_factory set."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def generate_session_key(
        self,
        student_id: str,
        course: str = "cs6650",
        context: str = "general"
    ) -> str:
        """Generate session key: tai:<course>:<student_id>:<context>."""
        return f"tai:{course}:{student_id}:{context}"
    
    def get_or_create(
        self,
        student_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get or create session."""
        course = context.get("course", "cs6650")
        context_name = context.get("context", "general")
        
        session_key = self.generate_session_key(student_id, course, context_name)
        
        conn = self._get_connection()
        
        try:
            # Check if session exists and is not expired
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?",
                (session_key,)
            )
            row = cursor.fetchone()
            
            if row:
                # Check idle timeout
                last_activity = datetime.fromisoformat(row["last_activity"])
                timeout_minutes = self._get_timeout_minutes(context_name)
                
                if datetime.now() - last_activity > timedelta(minutes=timeout_minutes):
                    # Session expired, create new
                    conn.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
                    conn.commit()
                else:
                    # Return existing session
                    session = dict(row)
                    session["messages"] = json.loads(session.get("messages", "[]"))
                    return session
            
            # Create new session
            session = {
                "session_key": session_key,
                "student_id": student_id,
                "course": course,
                "context": context_name,
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat()
            }
            
            conn.execute(
                """INSERT INTO sessions (session_key, student_id, course, context, messages, last_activity)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_key,
                    student_id,
                    course,
                    context_name,
                    json.dumps([]),
                    session["last_activity"]
                )
            )
            conn.commit()
            
            return session
        finally:
            conn.close()
    
    def add_message(self, session_key: str, role: str, content: str):
        """Add message to session."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute(
                "SELECT messages FROM sessions WHERE session_key = ?",
                (session_key,)
            )
            row = cursor.fetchone()
            
            if row:
                messages = json.loads(row["messages"])
                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })
                
                conn.execute(
                    """UPDATE sessions
                       SET messages = ?, last_activity = ?
                       WHERE session_key = ?""",
                    (json.dumps(messages), datetime.now().isoformat(), session_key)
                )
                conn.commit()
        finally:
            conn.close()
    
    def get_messages(self, session_key: str, limit: Optional[int] = None) -> List[Dict]:
        """Get recent messages from session."""
        conn = self._get_connection()
        
        try:
            cursor = conn.execute(
                "SELECT messages FROM sessions WHERE session_key = ?",
                (session_key,)
            )
            row = cursor.fetchone()
            
            if row:
                messages = json.loads(row["messages"])
                if limit:
                    return messages[-limit:]
                return messages
            
            return []
        finally:
            conn.close()
    
    def _get_timeout_minutes(self, context: str) -> int:
        """Get idle timeout for context type."""
        reset_config = settings.session.reset_by_type.get(context, {})
        return reset_config.get("idle_minutes", settings.session.idle_timeout_minutes)
