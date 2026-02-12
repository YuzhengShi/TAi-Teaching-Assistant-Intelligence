"""
Panic button: emergency shutdown and data purge.
Cross-platform compatible (Windows + Unix).
"""

import signal
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any

from src.shared.logging import get_logger

logger = get_logger(__name__)

# Platform-specific imports
_IS_WINDOWS = sys.platform == "win32"

if not _IS_WINDOWS:
    import fcntl  # Unix only


class PanicButton:
    """Emergency shutdown and data purge system."""
    
    def __init__(self, data_path: Path, lock_file: Optional[Path] = None):
        self.data_path = data_path
        self.lock_file = lock_file or data_path / ".panic_lock"
        self.lock_fd = None
        
        # Register signal handlers (SIGUSR1/2 only on Unix)
        if not _IS_WINDOWS:
            signal.signal(signal.SIGUSR1, self._handle_soft_shutdown)
            signal.signal(signal.SIGUSR2, self._handle_hard_purge)
    
    def _handle_soft_shutdown(self, signum, frame):
        """SIGUSR1: Soft shutdown - complete current sessions."""
        logger.critical("SOFT SHUTDOWN triggered via SIGUSR1")
        sys.exit(0)
    
    def _handle_hard_purge(self, signum, frame):
        """SIGUSR2: Hard purge - emergency data deletion."""
        logger.critical("HARD PURGE triggered via SIGUSR2 - DELETING ALL STUDENT DATA")
        
        if not self._acquire_lock():
            logger.error("Could not acquire lock - purge may be in progress")
            return
        
        try:
            self._purge_student_data()
            logger.critical("Student data purged")
        finally:
            self._release_lock()
        
        sys.exit(0)
    
    def trigger(self, professor_id: str, purge: bool = False) -> Dict[str, Any]:
        """
        Trigger panic button (manual).
        
        Args:
            professor_id: Professor identifier for verification
            purge: If True, purge data; if False, soft shutdown
        
        Returns:
            Result dict
        """
        if not self._verify_professor(professor_id):
            return {
                "success": False,
                "error": "Unauthorized - professor verification failed"
            }
        
        if purge:
            return self._purge_student_data()
        else:
            logger.critical(f"Soft shutdown triggered by professor {professor_id}")
            return {"success": True, "action": "soft_shutdown"}
    
    def _purge_student_data(self) -> Dict[str, Any]:
        """Purge all student data."""
        if not self._acquire_lock():
            return {
                "success": False,
                "error": "Lock file exists - purge may already be in progress"
            }
        
        try:
            db_files = [
                self.data_path / "wal.sqlite",
                self.data_path / "sessions.sqlite",
            ]
            
            deleted = []
            for db_file in db_files:
                if db_file.exists():
                    db_file.unlink()
                    deleted.append(str(db_file))
            
            students_dir = self.data_path / "students"
            if students_dir.exists():
                import shutil
                shutil.rmtree(students_dir)
                deleted.append(str(students_dir))
            
            logger.critical(f"Purged student data: {deleted}")
            
            return {
                "success": True,
                "action": "hard_purge",
                "deleted": deleted
            }
        finally:
            self._release_lock()
    
    def _acquire_lock(self) -> bool:
        """Acquire lock file to prevent concurrent purges."""
        if _IS_WINDOWS:
            # Windows: use simple file existence check
            try:
                if self.lock_file.exists():
                    return False
                self.lock_file.touch()
                return True
            except OSError:
                return False
        else:
            # Unix: use fcntl file locking
            try:
                self.lock_fd = os.open(
                    str(self.lock_file), os.O_CREAT | os.O_WRONLY | os.O_EXCL
                )
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (OSError, IOError):
                if self.lock_fd:
                    os.close(self.lock_fd)
                    self.lock_fd = None
                return False
    
    def _release_lock(self):
        """Release lock file."""
        if _IS_WINDOWS:
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception as e:
                logger.warning(f"Error releasing lock: {str(e)}")
        else:
            if self.lock_fd:
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                    os.close(self.lock_fd)
                    self.lock_fd = None
                    if self.lock_file.exists():
                        self.lock_file.unlink()
                except Exception as e:
                    logger.warning(f"Error releasing lock: {str(e)}")
    
    def _verify_professor(self, professor_id: str) -> bool:
        """Verify professor identity (simplified - in production, use auth system)."""
        return professor_id.startswith("professor_") or professor_id == "coady"
