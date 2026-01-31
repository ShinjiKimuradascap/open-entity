#!/usr/bin/env python3
"""
Standardized Error Handler for Peer Service

Provides consistent error handling patterns across the peer service.
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Tuple
from aiohttp import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PeerServiceError(Exception):
    """Base exception for peer service errors"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
    
    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details
        }


class ConnectionError(PeerServiceError):
    """Connection-related errors"""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "CONNECTION_ERROR", details)


class TimeoutError(PeerServiceError):
    """Timeout errors"""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "TIMEOUT_ERROR", details)


class ValidationError(PeerServiceError):
    """Message validation errors"""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "VALIDATION_ERROR", details)


class PeerNotFoundError(PeerServiceError):
    """Peer not found errors"""
    def __init__(self, peer_id: str):
        super().__init__(f"Peer not found: {peer_id}", "PEER_NOT_FOUND", {"peer_id": peer_id})


class ErrorHandler:
    """Standardized error handler for async operations"""
    
    @staticmethod
    async def handle_async_operation(
        operation: Callable,
        *args,
        operation_name: str = "operation",
        max_retries: int = 0,
        retry_delay: float = 1.0,
        **kwargs
    ) -> Tuple[bool, Any]:
        """
        Execute async operation with standardized error handling.
        
        Args:
            operation: Async function to execute
            operation_name: Name for logging
            max_retries: Number of retries on failure
            retry_delay: Delay between retries
            
        Returns:
            Tuple of (success, result_or_error)
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await operation(*args, **kwargs)
                return True, result
                
            except asyncio.TimeoutError as e:
                last_error = TimeoutError(f"{operation_name} timed out", {"attempt": attempt})
                logger.warning(f"{operation_name} timeout (attempt {attempt + 1})")
                
            except ClientError as e:
                last_error = ConnectionError(f"{operation_name} failed: {e}", {"attempt": attempt})
                logger.warning(f"{operation_name} connection error: {e} (attempt {attempt + 1})")
                
            except asyncio.CancelledError:
                logger.info(f"{operation_name} cancelled")
                raise
                
            except Exception as e:
                last_error = PeerServiceError(f"{operation_name} failed: {e}", details={"attempt": attempt})
                logger.error(f"{operation_name} unexpected error: {e} (attempt {attempt + 1})")
            
            # Retry logic
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2 ** attempt))
        
        return False, last_error
    
    @staticmethod
    def log_error(error: Exception, context: str = "", level: str = "error") -> None:
        """Log error with consistent format"""
        log_func = getattr(logger, level, logger.error)
        
        if isinstance(error, PeerServiceError):
            log_func(f"[{context}] {error.error_code}: {error.message}")
        else:
            log_func(f"[{context}] {type(error).__name__}: {error}")
    
    @staticmethod
    def format_error_response(error: Exception) -> dict:
        """Format error for API response"""
        if isinstance(error, PeerServiceError):
            return error.to_dict()
        return {
            "error": "INTERNAL_ERROR",
            "message": str(error),
            "details": {}
        }
