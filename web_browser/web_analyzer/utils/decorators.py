import logging
from functools import wraps
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)


T = TypeVar('T')

def error_handler(func: Callable[..., T]) -> Callable[..., Optional[T]]:
    """Decorator for standardized error handling."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Optional[T]:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            return None
    return wrapper