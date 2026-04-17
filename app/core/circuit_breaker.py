"""
Circuit Breaker Pattern Implementation
Prevents cascading failures when external services are down
"""
import time
import logging
from typing import Callable, Any, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: int = 60  # Seconds before trying again (half-open)
    expected_exception: type = Exception  # Exception type to catch


class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing if service recovered, allow limited requests
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        
        @breaker
        async def call_external_api():
            return await httpx.get("https://api.example.com")
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        expected_exception: type = Exception,
        name: str = "default"
    ):
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            expected_exception=expected_exception
        )
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap function with circuit breaker"""
        async def wrapper(*args, **kwargs) -> Any:
            return await self.call(func, *args, **kwargs)
        return wrapper
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
        
        Returns:
            Function result
        
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        # Check if circuit should transition to half-open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Service unavailable. Retry after {self._time_until_retry()}s"
                )
        
        try:
            # Execute function
            result = await func(*args, **kwargs) if callable(func) else func
            
            # Record success
            self._on_success()
            
            return result
            
        except self.config.expected_exception as e:
            # Record failure
            self._on_failure()
            
            logger.warning(
                f"Circuit breaker '{self.name}' recorded failure: {e}. "
                f"Failure count: {self.failure_count}/{self.config.failure_threshold}"
            )
            
            raise
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.HALF_OPEN:
            # Failed during recovery test - reopen circuit
            self._transition_to_open()
        elif self.failure_count >= self.config.failure_threshold:
            self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.opened_at:
            return True
        
        elapsed = (datetime.utcnow() - self.opened_at).total_seconds()
        return elapsed >= self.config.timeout
    
    def _time_until_retry(self) -> int:
        """Calculate seconds until retry is allowed"""
        if not self.opened_at:
            return 0
        
        elapsed = (datetime.utcnow() - self.opened_at).total_seconds()
        remaining = max(0, self.config.timeout - elapsed)
        return int(remaining)
    
    def _transition_to_open(self):
        """Transition to OPEN state"""
        self.state = CircuitState.OPEN
        self.opened_at = datetime.utcnow()
        self.success_count = 0
        
        logger.error(
            f"Circuit breaker '{self.name}' OPENED after {self.failure_count} failures. "
            f"Will retry in {self.config.timeout}s"
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self.state = CircuitState.HALF_OPEN
        self.failure_count = 0
        self.success_count = 0
        
        logger.info(f"Circuit breaker '{self.name}' transitioned to HALF_OPEN. Testing service...")
    
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = None
        
        logger.info(f"Circuit breaker '{self.name}' CLOSED. Service recovered.")
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        self._transition_to_closed()
        logger.info(f"Circuit breaker '{self.name}' manually reset")
    
    def get_state(self) -> dict:
        """Get current circuit breaker state"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.config.failure_threshold,
            "success_threshold": self.config.success_threshold,
            "timeout": self.config.timeout,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "time_until_retry": self._time_until_retry() if self.state == CircuitState.OPEN else 0
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


# Global circuit breakers for common services
_circuit_breakers = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: int = 60,
    expected_exception: type = Exception
) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.
    
    Args:
        name: Circuit breaker name (e.g., "blockchain_rpc", "webhook_delivery")
        failure_threshold: Failures before opening
        success_threshold: Successes to close from half-open
        timeout: Seconds before retry
        expected_exception: Exception type to catch
    
    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            expected_exception=expected_exception,
            name=name
        )
    
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict:
    """Get state of all circuit breakers"""
    return {
        name: breaker.get_state()
        for name, breaker in _circuit_breakers.items()
    }


def reset_all_circuit_breakers():
    """Reset all circuit breakers to CLOSED state"""
    for breaker in _circuit_breakers.values():
        breaker.reset()
