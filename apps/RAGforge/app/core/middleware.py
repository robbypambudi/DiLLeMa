import asyncio
from functools import wraps

from dependency_injector.wiring import inject as di_inject
from loguru import logger

from app.services.base_service import BaseService


def inject(func):
    @di_inject
    @wraps(func)
    async def wrapper(*args, **kwargs):
        injected_services = [arg for arg in kwargs.values() if isinstance(arg, BaseService)]

        try:
            # Handle async functions
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
                return result
            # Handle regular functions
            else:
                result = func(*args, **kwargs)
                return result
        finally:
            if injected_services:
                try:
                    injected_services[-1].close_scoped_session()
                except Exception as e:
                    logger.error(e)

    return wrapper
