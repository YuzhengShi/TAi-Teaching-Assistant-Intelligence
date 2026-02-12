"""
Structured JSON logging for TAi.
Includes student_id (anonymized), action, and timestamp in every log.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from src.shared.config import settings


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add structured fields if present
        if hasattr(record, "student_id"):
            log_data["student_id"] = record.student_id
        
        if hasattr(record, "action"):
            log_data["action"] = record.action
        
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add any extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "msecs",
                          "message", "pathname", "process", "processName", "relativeCreated",
                          "thread", "threadName", "exc_info", "exc_text", "stack_info",
                          "student_id", "action", "session_id"]:
                log_data[key] = str(value)
        
        return json.dumps(log_data)


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None
):
    """
    Setup structured logging for TAi.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for file logging
    """
    log_level = log_level or settings.log_level
    log_file = log_file or settings.log_file
    
    # Create log directory if needed
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create formatter
    formatter = StructuredFormatter()
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    student_id: Optional[str] = None,
    action: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
):
    """
    Log with structured context.
    
    Args:
        logger: Logger instance
        level: Log level (logging.INFO, etc.)
        message: Log message
        student_id: Optional anonymized student ID
        action: Optional action name
        session_id: Optional session ID
        **kwargs: Additional structured fields
    """
    extra = {}
    if student_id:
        extra["student_id"] = student_id
    if action:
        extra["action"] = action
    if session_id:
        extra["session_id"] = session_id
    extra.update(kwargs)
    
    logger.log(level, message, extra=extra)


# Initialize logging on import
setup_logging()
