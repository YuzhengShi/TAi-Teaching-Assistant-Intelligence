"""
Tiered caching for student profiles.
L1: in-memory, L2: SQLite, L3: graph query.
"""

import time
from typing import Optional, Dict
from pathlib import Path
import sqlite3
import json

from src.core.profile.generator import ProfileGenerator
from src.shared.logging import get_logger

logger = get_logger(__name__)


class ProfileCache:
    """Tiered cache for student profiles."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # L1: In-memory cache
        self.l1_cache: Dict[str, tuple[str, float]] = {}  # key -> (profile, timestamp)
        self.l1_ttl = self.config.get("l1_ttl", 300)  # 5 minutes
        
        # L2: SQLite cache
        self.l2_db_path = Path(self.config.get("l2_db", "data/profile_cache.sqlite"))
        self.l2_ttl = self.config.get("l2_ttl", 1800)  # 30 minutes
        self._init_l2_cache()
        
        # L3: Profile generator (cold path)
        self.generator = ProfileGenerator()
    
    def _init_l2_cache(self):
        """Initialize L2 SQLite cache."""
        self.l2_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.l2_db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_cache (
                cache_key TEXT PRIMARY KEY,
                profile_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    async def get_profile(
        self,
        student_id: str,
        topic: Optional[str],
        session_type: str
    ) -> str:
        """Get profile with tiered cache lookup."""
        cache_key = self._generate_cache_key(student_id, topic, session_type)
        
        # L1: In-memory
        if cache_key in self.l1_cache:
            profile, timestamp = self.l1_cache[cache_key]
            if time.time() - timestamp < self.l1_ttl:
                logger.debug(f"L1 cache hit: {cache_key}")
                return profile
        
        # L2: SQLite
        l2_profile = self._get_l2(cache_key)
        if l2_profile:
            # Promote to L1
            self.l1_cache[cache_key] = (l2_profile, time.time())
            logger.debug(f"L2 cache hit: {cache_key}")
            return l2_profile
        
        # L3: Generate from graph
        logger.debug(f"L3 cache miss, generating: {cache_key}")
        profile = await self.generator.generate(student_id, topic, session_type)
        
        # Store in L2 and L1
        self._set_l2(cache_key, profile)
        self.l1_cache[cache_key] = (profile, time.time())
        
        return profile
    
    def invalidate(self, student_id: str):
        """Invalidate cache for a student (called when WAL processes new facts)."""
        # Remove from L1
        keys_to_remove = [
            key for key in self.l1_cache.keys()
            if key.startswith(f"{student_id}:")
        ]
        for key in keys_to_remove:
            del self.l1_cache[key]
        
        # Remove from L2
        conn = sqlite3.connect(str(self.l2_db_path))
        conn.execute(
            "DELETE FROM profile_cache WHERE cache_key LIKE ?",
            (f"{student_id}:%",)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"Invalidated profile cache for student {student_id}")
    
    def _generate_cache_key(
        self,
        student_id: str,
        topic: Optional[str],
        session_type: str
    ) -> str:
        """Generate cache key."""
        return f"{student_id}:{topic or 'all'}:{session_type}"
    
    def _get_l2(self, cache_key: str) -> Optional[str]:
        """Get from L2 cache."""
        conn = sqlite3.connect(str(self.l2_db_path))
        cursor = conn.execute(
            "SELECT profile_text, created_at FROM profile_cache WHERE cache_key = ?",
            (cache_key,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            profile_text, created_at = row
            # Check TTL
            created_timestamp = time.mktime(time.strptime(created_at, "%Y-%m-%d %H:%M:%S"))
            if time.time() - created_timestamp < self.l2_ttl:
                return profile_text
        
        return None
    
    def _set_l2(self, cache_key: str, profile: str):
        """Store in L2 cache."""
        conn = sqlite3.connect(str(self.l2_db_path))
        conn.execute(
            """INSERT OR REPLACE INTO profile_cache (cache_key, profile_text, created_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)""",
            (cache_key, profile)
        )
        conn.commit()
        conn.close()
